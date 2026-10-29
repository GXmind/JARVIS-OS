"""Local wake matching and automatic command endpoint rules; no devices or network."""
from array import array
import math
import re

class WakeMatcher:
    def __init__(self):self.last=-100.;self.partial=None;self.since=0.
    def accept(self,result,now,final=False):
        text=re.sub(r"[^a-z ]"," ",str(result.get("text" if final else "partial","")).lower())
        text=" ".join(text.split());words=result.get("result" if final else "partial_result",[])
        matched=bool(re.search(r"\b(?:hi|hey|high) jarvis\b",text))
        scores={item.get("word"):float(item.get("conf",0)) for item in words}
        greeting=max((scores.get(word,0) for word in ("hi","hey","high")),default=0)
        jarvis=scores.get("jarvis",0);confidence=(greeting+jarvis)/2
        if not matched or jarvis<(.82 if final else .90) or greeting<.35 or confidence<(.70 if final else .82):self.partial=None;return False
        if now-self.last<3:return False
        if final:self.last=now;self.partial=None;return True
        if text!=self.partial:self.partial=text;self.since=now;return False
        if now-self.since>=.14:self.last=now;self.partial=None;return True
        return False

class VoiceEndpoint:
    def __init__(self,rate,timeout=8,silence=1.,maximum=25):
        self.rate=rate;self.timeout=timeout;self.silence=silence;self.maximum=maximum
        self.started=False;self.noise=65.;self.voiced=0.;self.last_voice=0.;self.begin=0.
    def feed(self,block,elapsed):
        samples=array("h",block[:len(block)//2*2]);duration=len(samples)/self.rate
        rms=math.sqrt(sum(value*value for value in samples)/max(1,len(samples)))
        voice=rms>max(180,self.noise*2.6)
        if voice:
            self.voiced+=duration;self.last_voice=elapsed
        else:
            self.voiced=max(0,self.voiced-duration)
            if not self.started:self.noise=min(450,self.noise*.95+min(rms,450)*.05)
        if not self.started and self.voiced>=.10:
            self.started=True;self.begin=elapsed;return "start"
        if not self.started:return "timeout" if elapsed>=self.timeout else "waiting"
        if elapsed-self.begin>=self.maximum:return "end"
        if elapsed-self.begin>.35 and elapsed-self.last_voice>=self.silence:return "end"
        return "speech"
