"""Minimal read-only MVT 2.1 decoder for OpenFreeMap building and transportation layers."""
import gzip,math,struct
from .vendor.eviltransform import wgs2gcj

def varint(data,pos):
    value=0
    for shift in range(0,70,7):
        if pos>=len(data):raise ValueError("Truncated varint")
        byte=data[pos];pos+=1;value|=(byte&127)<<shift
        if byte<128:return value,pos
    raise ValueError("Oversized varint")

def fields(data):
    pos=0
    while pos<len(data):
        tag,pos=varint(data,pos);wire=tag&7;number=tag>>3
        if wire==0:value,pos=varint(data,pos)
        elif wire in (1,5):
            size=8 if wire==1 else 4;value=data[pos:pos+size];pos+=size
            if len(value)!=size:raise ValueError("Truncated field")
        elif wire==2:
            size,pos=varint(data,pos)
            if size>len(data)-pos:raise ValueError("Invalid field length")
            value=data[pos:pos+size];pos+=size
        else:raise ValueError("Unsupported PBF wire type")
        yield number,wire,value

def packed(data):
    result=[];pos=0
    while pos<len(data):
        value,pos=varint(data,pos);result.append(value)
    return result

def value_of(data):
    for number,wire,value in fields(data):
        if number==1:return value.decode("utf-8")
        if number==2:return struct.unpack("<f",value)[0]
        if number==3:return struct.unpack("<d",value)[0]
        if number in (4,5):return value
        if number==6:return (value>>1)^-(value&1)
        if number==7:return bool(value)
    return None

def rings_of(data):
    values=packed(data);pos=0;x=y=0;ring=[];rings=[]
    while pos<len(values):
        command=values[pos];pos+=1;kind=command&7;count=command>>3
        if not 0<count<=100000:raise ValueError("Invalid geometry command")
        if kind in (1,2):
            for _ in range(count):
                if pos+1>=len(values):raise ValueError("Invalid geometry")
                dx,dy=values[pos:pos+2];pos+=2;x+=(dx>>1)^-(dx&1);y+=(dy>>1)^-(dy&1)
                if kind==1 and ring:rings.append(ring);ring=[]
                ring.append([x,y])
        elif kind==7:
            if ring and ring[0]!=ring[-1]:ring.append(ring[0])
        else:raise ValueError("Unknown geometry command")
    if ring:rings.append(ring)
    return rings

def decode_tile(data,x,y,z):
    if data[:2]==b"\x1f\x8b":data=gzip.decompress(data)
    if len(data)>8_000_000:raise ValueError("Tile too large")
    buildings=[];roads=[]
    for field,wire,layer in fields(data):
        if field!=3:continue
        name="";keys=[];values=[];features=[];extent=4096
        for number,_,value in fields(layer):
            if number==1:name=value.decode()
            elif number==2:features.append(value)
            elif number==3:keys.append(value.decode())
            elif number==4:values.append(value_of(value))
            elif number==5:extent=value
        if name not in ("building","transportation") or not 1<=extent<=65536:continue
        def position(point):
            lng=(x+point[0]/extent)/2**z*360-180
            lat=math.degrees(math.atan(math.sinh(math.pi*(1-2*(y+point[1]/extent)/2**z))))
            lat,lng=wgs2gcj(lat,lng);return [lng,lat]
        for index,feature in enumerate(features):
            props={};geometry=None;kind=0;identifier=index
            for number,_,value in fields(feature):
                if number==1:identifier=value
                elif number==2:
                    tags=packed(value)
                    for i in range(0,len(tags)-1,2):
                        if tags[i]<len(keys) and tags[i+1]<len(values):props[keys[tags[i]]]=values[tags[i+1]]
                elif number==3:kind=value
                elif number==4:geometry=value
            if geometry is None:continue
            for ring in rings_of(geometry):
                points=[position(p) for p in ring]
                if name=="building" and kind==3 and len(points)>=4:
                    height=float(props.get("render_height") or props.get("height") or 12)
                    buildings.append({"id":str(identifier),"footprint":points,"height":min(350,max(3,height)),"height_source":"provider_or_estimated"})
                elif name=="transportation" and kind==2 and len(points)>1:
                    roads.append({"id":str(identifier),"path":points,"kind":props.get("class","road"),"name":props.get("name","")})
    return {"buildings":buildings,"roads":roads}