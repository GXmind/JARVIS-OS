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
