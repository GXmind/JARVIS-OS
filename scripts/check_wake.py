import argparse,json,wave,sys,time,subprocess
parser=argparse.ArgumentParser(description="Local synthesized wake check; no cloud calls")
parser.add_argument("--microphone",action="store_true");args=parser.parse_args()
from pathlib import Path
r=Path(r'F:\Javis_os');sys.path.insert(0,str(r/'src'))
from jarvis.domain.voice import WakeMatcher
from jarvis.infrastructure.audio.wake import WakeListener
from jarvis.infrastructure.audio.service import Audio
from jarvis.domain.settings import Settings
from jarvis.infrastructure.config.env_file import load_settings
# Synthesize fixtures, never play them into the room or record ambient audio.
ps=r/"tmp/wake_fixture.ps1"
ps.write_text(r"""Add-Type -AssemblyName System.Speech
$synth=New-Object System.Speech.Synthesis.SpeechSynthesizer
$synth.SelectVoiceByHints([System.Speech.Synthesis.VoiceGender]::NotSet,[System.Speech.Synthesis.VoiceAge]::NotSet,0,[System.Globalization.CultureInfo]::GetCultureInfo('en-US'))
$format=New-Object System.Speech.AudioFormat.SpeechAudioFormatInfo(16000,[System.Speech.AudioFormat.AudioBitsPerSample]::Sixteen,[System.Speech.AudioFormat.AudioChannel]::Mono)
$synth.SetOutputToWaveFile('F:\Javis_os\tmp\wake_positive.wav',$format)
$synth.Speak('Hi Jarvis')
$synth.SetOutputToWaveFile('F:\Javis_os\tmp\wake_negative.wav',$format)
$synth.Speak('The weather is nice today. Please open the map.')
$synth.Dispose()
""",encoding="utf-8-sig")
subprocess.run(["powershell.exe","-NoProfile","-File",str(ps)],check=True,cwd=r)
import vosk
vosk.SetLogLevel(-1);model=vosk.Model(str(r/'cache/wake/vosk-model-small-en-us-0.15'))
report={}
for kind in ('positive','negative'):
 d=vosk.KaldiRecognizer(model,16000,json.dumps(['hi jarvis','hey jarvis','high jarvis','[unk]']));d.SetWords(True);d.SetPartialWords(True);matcher=WakeMatcher();hits=0;texts=[]
 with wave.open(str(r/f'tmp/wake_{kind}.wav'),'rb') as wav:pcm=wav.readframes(wav.getnframes())+bytes(16000*3)
 for offset in range(0,len(pcm),3200):
  final=d.AcceptWaveform(pcm[offset:offset+3200]);result=json.loads(d.Result() if final else d.PartialResult());hits+=matcher.accept(result,offset/32000,bool(final))
  if final:texts.append(result.get('text',''))
 report[kind]={'wake_hits':hits,'decoded':texts}
assert report['positive']['wake_hits']>=1,report
assert report['negative']['wake_hits']==0,report
if args.microphone:
 settings=load_settings();audio=Audio();w=WakeListener(audio=audio,settings_provider=lambda:settings,on_wake=lambda:None,can_listen=lambda:True);w.start()
 deadline=time.monotonic()+12
 while time.monotonic()<deadline and w.snapshot()['state'] not in ('waiting','error'):time.sleep(.1)
 report['microphone']=w.snapshot();w.pause();report['released_for_command']=w.released.is_set() and audio.lock.acquire(False)
 if report['released_for_command']:audio.lock.release()
 w.close();audio.close();report['listener_closed']=not w.thread.is_alive()
 assert report["microphone"]["state"]=="waiting" and report["released_for_command"] and report["listener_closed"],report
(r/'logs/wake_runtime_check.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=True))
