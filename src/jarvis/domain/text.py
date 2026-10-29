"""Subtitle units follow speech clauses; they are never an arbitrary full answer dump."""
import re

def lines_for_speech(text,width=34):
    clean=re.sub(r"[#*`]","",str(text)).strip()
    units=re.findall(r"[^。！？!?；;\n]+[。！？!?；;]?|\n",clean)
    result=[]
    for unit in units:
        unit=unit.strip()
        while len(unit)>width:
            cut=max(unit.rfind(mark,0,width+1) for mark in ("，",",","、"," "))
            cut=cut+1 if cut>=width//2 else width
            result.append(unit[:cut].strip());unit=unit[cut:].strip()
        if unit:result.append(unit)
    return result or [clean or "暂无回复。"]


class SpeechChunks:
    """Release natural clauses early; bound a long punctuation-free model response."""
    def __init__(self):self.pending=""
    def feed(self,text,final=False):
        self.pending+=str(text);result=[]
        while self.pending:
            match=re.search(r"[。！？!?；;\n]",self.pending)
            cut=match.end() if match else 0
            if not cut and len(self.pending)>=48:
                cut=max(self.pending.rfind(mark,12,49) for mark in ("，",","," "))
                cut=cut+1 if cut>=12 else 48
            if not cut:
                if final:cut=len(self.pending)
                else:break
            line=re.sub(r"[#*`]","",self.pending[:cut]).strip();self.pending=self.pending[cut:]
            if line:result.append(line)
        return result
