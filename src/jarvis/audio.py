"""Blocking operations run only on workers. Raw streams avoid a numpy dependency."""
import json
import base64
from array import array
from datetime import datetime
import logging
from pathlib import Path
import queue
import subprocess
import threading
import time
import uuid
import wave

from .api import CloudAPI, ServiceError
from .paths import ROOT, local_path

LOG = logging.getLogger("jarvis")

def sounddevice():
    try:
        import sounddevice as sd
        return sd
    except (ImportError, OSError):
        try:
            from .native_audio import WinMM
            return WinMM()
        except Exception:
            raise ServiceError("Windows 音频组件不可用，请检查设备与驱动；仍可使用文字对话。") from None

def devices():
    sd = sounddevice()
    try:
        result = []
        apis = sd.query_hostapis()
        default_in, default_out = sd.default.device
        for index, item in enumerate(sd.query_devices()):
            result.append({
                "index": index, "name": item["name"],
                "hostapi": apis[item["hostapi"]]["name"],
                "inputs": item["max_input_channels"], "outputs": item["max_output_channels"],
                "rate": int(item["default_samplerate"]),
                "default_in": index == default_in, "default_out": index == default_out,
            })
        return result
    except Exception:
        raise ServiceError("无法枚举音频设备，请检查 Windows 声音设置与设备驱动。") from None

def device_id(value):
    return int(value) if value else None

class Audio:
    def __init__(self):
        self.stop_event = threading.Event()
        self.closed = threading.Event()
        self.lock = threading.Lock()
        self.level = 0.0
        self.capture_active = False

    def prepare(self):
        self.level = 0.0
        self.stop_event.clear()

    def stop(self):
        self.level = 0.0
        self.stop_event.set()

    def close(self):
        self.closed.set()
        self.stop()

    def measure(self, data):
        samples = array("h", data[:len(data) // 2 * 2])
        if samples:
            peak = max(abs(value) for value in samples)
            # A display gain helps normal speech remain visible; zero stays zero.
            self.level = min(1.0, (peak / 32768.0) ** 0.6 * 1.4)
        else:
            self.level = 0.0

    def recording(self, settings):
        if self.closed.is_set():
            raise ServiceError("音频服务已关闭。")
        if not self.lock.acquire(blocking=False):
            raise ServiceError("音频设备正在使用，请稍后再试。")
        output = ROOT / "recordings" / (datetime.now().strftime("%Y%m%d_%H%M%S_") + uuid.uuid4().hex[:8] + ".wav")
        try:
            sd = sounddevice()
            rate = int(settings.SAMPLE_RATE)
            audio_queue = queue.Queue(maxsize=100)
            trouble = threading.Event()
            def callback(indata, frames, time_info, status):
                if status:
                    trouble.set()
                try:
                    audio_queue.put_nowait(bytes(indata))
                except queue.Full:
                    trouble.set()

            with wave.open(str(output), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(rate)
                with sd.RawInputStream(samplerate=rate, blocksize=1024, channels=1,
                                       dtype="int16", device=device_id(settings.INPUT_DEVICE),
                                       callback=callback):
                    self.capture_active = True
                    start = time.monotonic()
                    while not self.stop_event.is_set() and not self.closed.is_set():
                        if time.monotonic() - start >= int(settings.MAX_RECORD_SECONDS):
                            break
                        try:
                            block = audio_queue.get(timeout=0.08)
                            self.measure(block)
                            wav.writeframesraw(block)
                        except queue.Empty:
                            pass
                while not audio_queue.empty():
                    wav.writeframesraw(audio_queue.get_nowait())
            if trouble.is_set():
                LOG.warning("recording_overflow")
                raise ServiceError(f"录音出现丢帧，文件已保留：{output.name}。请更换设备或采样率。")
            with wave.open(str(output), "rb") as wav:
                if wav.getnframes() < rate // 5:
                    raise ServiceError("录音不足 0.2 秒，请重新录音。")
            LOG.info("recording_saved")
            return output
        except ServiceError:
            raise
        except Exception:
            LOG.warning("recording_failed")
            raise ServiceError("录音失败。请允许 Windows 桌面应用访问麦克风，检查输入设备及采样率。") from None
        finally:
            self.capture_active = False
            self.level = 0.0
            self.lock.release()

    def play(self, path, settings, on_position=None):
        sd = sounddevice()
        path = local_path(path)
        if not self.lock.acquire(blocking=False):
            raise ServiceError("音频设备正在使用。")
        try:
            with wave.open(str(path), "rb") as wav:
                if wav.getsampwidth() != 2 or wav.getcomptype() != "NONE":
                    raise ServiceError("仅支持 PCM 16 位 WAV 播放。")
                with sd.RawOutputStream(samplerate=wav.getframerate(), channels=wav.getnchannels(),
                                        dtype="int16", device=device_id(settings.OUTPUT_DEVICE)) as stream:
                    submitted=0
                    while not self.stop_event.is_set() and not self.closed.is_set():
                        block = wav.readframes(2048)
                        if not block:
                            break
                        self.measure(block)
                        stream.write(block)
                        submitted+=len(block)//(wav.getnchannels()*2)
                        if on_position:
                            pending=getattr(stream,"pending_frames",0)
                            on_position(max(0,(submitted-pending)/wav.getframerate()))
                    if self.stop_event.is_set() or self.closed.is_set():
                        if hasattr(stream,"abort"):stream.abort()
                    elif hasattr(stream,"drain"):
                        stream.drain(on_position)
        except ServiceError:
            raise
        except Exception:
            LOG.warning("playback_failed")
            raise ServiceError("播放失败，请检查输出设备和 WAV 采样率；文字回复已保留。") from None
        finally:
            self.capture_active = False
            self.level = 0.0
            self.lock.release()

    def windows_speech(self, text, output):
        if self.closed.is_set():
            return
        source = ROOT / "tmp" / (uuid.uuid4().hex + ".txt")
        source.write_text(text[:2000], encoding="utf-8")
        # User text is read from a file, never inserted into executable code.
        source_literal = str(source).replace("'", "''")
        output_literal = str(output).replace("'", "''")
        script = (
            "$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Speech; "
            "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer; "
            "try { $s.SetOutputToWaveFile('" + output_literal + "'); "
            "$s.Speak([IO.File]::ReadAllText('" + source_literal + "',[Text.Encoding]::UTF8)) "
            "} finally { $s.Dispose() }"
        )
        encoded = base64.b64encode(script.encode("utf-16-le")).decode()
        process = None
        try:
            process = subprocess.Popen(
                ["powershell.exe", "-NoLogo", "-NoProfile", "-NonInteractive", "-EncodedCommand", encoded],
                cwd=ROOT, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                env=None,
            )
            deadline = time.monotonic() + 45
            while process.poll() is None:
                if self.closed.is_set() or self.stop_event.is_set() or time.monotonic() > deadline:
                    process.kill()
                    process.wait(timeout=5)
                    raise ServiceError("Windows 语音生成已停止或超时；可切换到关闭播报。")
                time.sleep(0.1)
            if process.returncode != 0 or not output.exists():
                raise ServiceError("Windows 语音不可用；请安装系统语音包或切换到云端/关闭播报。")
        finally:
            if process is not None and process.poll() is None:
                process.kill()
                process.wait(timeout=5)
            source.unlink(missing_ok=True)

    def windows_speech_lines(self,lines,output):
        """One synthesizer, one PCM stream. Cue times come from actual generated samples."""
        source=ROOT/"tmp"/(uuid.uuid4().hex+".json")
        pcm=output.with_suffix(".pcm");cues=output.with_suffix(".cues.json")
        source.write_text(json.dumps(lines,ensure_ascii=False),encoding="utf-8")
        literal=lambda path:str(path).replace("'","''")
        script=(
          "$ErrorActionPreference='Stop'; Add-Type -AssemblyName System.Speech;"
          "$s=New-Object System.Speech.Synthesis.SpeechSynthesizer;"
          "$stream=New-Object IO.MemoryStream;"
          "$format=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(24000,"
          "[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,"
          "[System.Speech.AudioFormat.AudioChannel]::Mono);"
          "try {$voices=@($s.GetInstalledVoices() | Where-Object {$_.Enabled -and $_.VoiceInfo.Culture.Name -eq 'zh-CN'});"
          "if($voices.Count -gt 0){$s.SelectVoice($voices[0].VoiceInfo.Name)};"
          "$s.SetOutputToAudioStream($stream,$format);"
          "$lines=ConvertFrom-Json ([IO.File]::ReadAllText('"+literal(source)+"',[Text.Encoding]::UTF8));"
          "$marks=@(); foreach($line in $lines){$marks+=($stream.Position/48000.0);$s.Speak([string]$line)};"
          "[IO.File]::WriteAllBytes('"+literal(pcm)+"',$stream.ToArray());"
          "[IO.File]::WriteAllText('"+literal(cues)+"',(ConvertTo-Json -InputObject $marks),[Text.Encoding]::UTF8)"
          "}finally{$s.Dispose();$stream.Dispose()}"
        )
        encoded=base64.b64encode(script.encode("utf-16-le")).decode()
        process=None
        try:
            process=subprocess.Popen(["powershell.exe","-NoLogo","-NoProfile","-NonInteractive","-EncodedCommand",encoded],
              cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,
              creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
            deadline=time.monotonic()+max(45,min(120,sum(map(len,lines))*.12))
            while process.poll() is None:
                if self.closed.is_set() or self.stop_event.is_set() or time.monotonic()>deadline:
                    process.kill();process.wait(timeout=5);raise ServiceError("语音生成已停止或超时。")
                time.sleep(.05)
            if process.returncode or not pcm.exists():raise ServiceError("Windows 语音生成失败，请检查中文语音包。")
            marks=json.loads(cues.read_text(encoding="utf-8-sig"))
            if not isinstance(marks,list):marks=[marks]
            if len(marks)!=len(lines):raise ServiceError("语音字幕时间点数量不匹配，请重新播报。")
            with wave.open(str(output),"wb") as wav:
                wav.setnchannels(1);wav.setsampwidth(2);wav.setframerate(24000);wav.writeframes(pcm.read_bytes())
            return marks
        finally:
            if process and process.poll() is None:process.kill();process.wait(timeout=5)
            source.unlink(missing_ok=True);pcm.unlink(missing_ok=True);cues.unlink(missing_ok=True)

    def speak(self,text,settings,on_line=None):
        from .presentation import lines_for_speech
        if settings.TTS_MODE=="off":return "播报已关闭。"
        lines=lines_for_speech(text[:2000])
        output=ROOT/"cache"/("tts_"+uuid.uuid4().hex+".wav")
        if settings.TTS_MODE=="windows":
            marks=self.windows_speech_lines(lines,output)
            index=-1
            def progress(seconds):
                nonlocal index
                while index+1<len(lines) and seconds+.015>=marks[index+1]:
                    index+=1
                    if on_line:on_line(lines[index])
            progress(0)
            if not self.closed.is_set() and not self.stop_event.is_set():self.play(output,settings,progress)
        else:
            # Remote synthesis is generated ahead of playback to avoid network gaps.
            from concurrent.futures import ThreadPoolExecutor
            def generate(item):
                i,line=item;path=output.with_name(output.stem+"_"+str(i)+".wav")
                CloudAPI(settings).synthesize(line,path);return path
            with ThreadPoolExecutor(max_workers=2) as pool:
                futures=[pool.submit(generate,item) for item in enumerate(lines)]
                for i,future in enumerate(futures):
                    path=future.result()
                    if self.closed.is_set() or self.stop_event.is_set():break
                    if on_line:on_line(lines[i])
                    self.play(path,settings)
        return "播报结束。"
