"""Bounded synthesis look-ahead and one continuous PCM output stream per answer."""
from array import array
from concurrent.futures import Future,TimeoutError as FutureTimeout
import queue,threading,time,uuid,wave
from jarvis.domain.errors import ServiceError
from jarvis.infrastructure.system.paths import ROOT

def trim_padding(pcm,rate,channels):
    # Only remove extended near-silence. Retain small lead/tail to protect consonants.
    values=array("h",pcm);frames=len(values)//channels
    if not frames:return pcm
    leading=0;trailing=frames
    while leading<frames and all(abs(values[leading*channels+c])<32 for c in range(channels)):leading+=1
    while trailing>leading and all(abs(values[(trailing-1)*channels+c])<32 for c in range(channels)):trailing-=1
    start=max(0,leading-int(rate*.025)) if leading>rate*.14 else 0
    end=min(frames,trailing+int(rate*.10)) if frames-trailing>rate*.18 else frames
    return values[start*channels:end*channels].tobytes()

def speak_sequence(audio,chunks,settings,on_line,sd,device_id,synthesize):
    ready=queue.Queue(maxsize=3);slots=threading.BoundedSemaphore(2);cancel=threading.Event();files=[];files_lock=threading.Lock();timing={"first_audio_ms":None,"clips":0,"device_opens":0};started=time.monotonic()
    def stopped():return cancel.is_set() or audio.stop_event.is_set() or audio.closed.is_set()
    def put(item):
        while not stopped():
            try:ready.put(item,timeout=.05);return True
            except queue.Full:pass
        return False
    def produce():
        try:
            used=0
            for line in chunks:
                if stopped():break
                line=str(line).strip()
                if not line:continue
                # No growing queue: at most two syntheses and three completed handles.
                while not slots.acquire(timeout=.05):
                    if stopped():return
                if stopped():slots.release();return
                future=Future();path=ROOT/"cache"/("voice_"+uuid.uuid4().hex+".wav")
                with files_lock:files.append(path)
                def generate(future=future,path=path,line=line):
                    try:
                        if stopped():future.cancel();return
                        synthesize(line,path,cancel);future.set_result(path)
                    except Exception as exc:future.set_exception(exc)
                    finally:
                        slots.release()
                        if stopped():path.unlink(missing_ok=True)
                threading.Thread(target=generate,daemon=True,name="jarvis-voice-prefetch").start()
                if not put((line,future)):return
                used+=len(line)
                if used>=8000:break
            put(None)
        except Exception as exc:put(exc)
    producer=threading.Thread(target=produce,daemon=True,name="jarvis-voice-lines");producer.start()
    def clips():
        while not stopped():
            try:item=ready.get(timeout=.05)
            except queue.Empty:continue
            if item is None:return
            if isinstance(item,Exception):raise item
            line,future=item
            while not stopped():
                try:path=future.result(timeout=.05);break
                except FutureTimeout:continue
            else:return
            with wave.open(str(path),"rb") as wav:
                if wav.getsampwidth()!=2 or wav.getcomptype()!="NONE":raise ServiceError("语音服务应返回 16 位 PCM WAV，不能混用采样格式。")
                fmt=(wav.getframerate(),wav.getnchannels());pcm=wav.readframes(wav.getnframes())
            path.unlink(missing_ok=True)
            yield line,fmt,trim_padding(pcm,*fmt)
    stream=None;locked=False;cues=[];subtitle=-1;submitted=0;fmt=None
    def progress(seconds):
        nonlocal subtitle
        while subtitle+1<len(cues) and seconds+.015>=cues[subtitle+1][0]:
            subtitle+=1
            if on_line:on_line(cues[subtitle][1])
    try:
        for line,current,pcm in clips():
            if stopped():break
            if stream is None:
                if not audio.lock.acquire(False):raise ServiceError("音频设备正在使用。")
                locked=True;fmt=current;stream=sd.RawOutputStream(samplerate=fmt[0],channels=fmt[1],dtype="int16",device=device_id(settings.OUTPUT_DEVICE));stream.__enter__();timing["device_opens"]+=1;timing["first_audio_ms"]=round((time.monotonic()-started)*1000)
            if current!=fmt:raise ServiceError("连续语音的采样率或声道发生变化，请检查服务配置。")
            cues.append((submitted/fmt[0],line));progress(max(0,(submitted-getattr(stream,"pending_frames",0))/fmt[0]));timing["clips"]+=1
            blocksize=2048*fmt[1]*2
            for offset in range(0,len(pcm),blocksize):
                if stopped():break
                block=pcm[offset:offset+blocksize];audio.measure(block);stream.write(block);submitted+=len(block)//(fmt[1]*2)
                progress(max(0,(submitted-getattr(stream,"pending_frames",0))/fmt[0]))
        if stream:
            if stopped() and hasattr(stream,"abort"):stream.abort()
            elif hasattr(stream,"drain"):stream.drain(progress)
            else:progress(submitted/fmt[0])
        return timing
    finally:
        cancel.set()
        if stream:
            try:stream.__exit__(None,None,None)
            except Exception:pass
        if locked:audio.lock.release()
        audio.level=0;producer.join(.5)
        with files_lock:
            for path in files:path.unlink(missing_ok=True)
