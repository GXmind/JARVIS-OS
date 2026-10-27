"""Projected 3D energy ribbons, particles and instruments rendered with tkinter."""
from collections import deque
import math
import random
import time
import tkinter as tk

BG = "#030a0d"
PANEL = "#071217"
CYAN = "#63f7df"

def blend(a, b, amount):
    amount = max(0.0, min(1.0, amount))
    first = tuple(int(a[i:i+2], 16) for i in (1,3,5))
    second = tuple(int(b[i:i+2], 16) for i in (1,3,5))
    return "#" + "".join(f"{round(x+(y-x)*amount):02x}" for x,y in zip(first,second))

def project(x, y, z, angle=0.0, tilt=.36):
    ca,sa = math.cos(angle),math.sin(angle)
    xx,zz = x*ca+z*sa,z*ca-x*sa
    ct,st = math.cos(tilt),math.sin(tilt)
    yy,zz = y*ct-zz*st,y*st+zz*ct
    perspective = 3.8/(3.8-zz)
    return xx*perspective,yy*perspective,zz

def ribbon_points(phase, strand, samples=84, breathe=1.0, offset=0.0):
    """Closed torus-knot ribbons. All geometry is generated locally."""
    points=[]
    for j in range(samples+1):
        t=j/samples*math.tau
        twist=3*t+strand*math.tau/3
        ring=.71+.22*math.cos(twist+phase*.35)+offset
        x=ring*math.cos(2*t+phase*.12)
        y=ring*math.sin(2*t+phase*.12)
        z=.37*math.sin(twist+phase*.35)+offset*.5
        points.append((x*breathe,y*breathe,z*breathe))
    return points

class ReactorHUD(tk.Canvas):
    def __init__(self, parent, snapshot, **kwargs):
        super().__init__(parent,bg=BG,highlightthickness=0,bd=0,**kwargs)
        self.snapshot=snapshot
        self.quality="high"
        self.running=True
        self.frame_count=0
        self.frame_times=deque(maxlen=90)
        self.frame_ms=0.0
        self.started=time.perf_counter()
        self.resize_id=None
        self.after_id=None
        self.scene=False
        self.width,self.height=1,1
        self.level=0.0
        self._last_status=None
        self.bind("<Configure>",self._resize)
        self.after_id=self.after(80,self._tick)

    def set_quality(self,value):
        if value not in ("high","low","off"):
            raise ValueError("Unknown animation quality")
        self.quality=value
        self._last_status=None

    def _resize(self,event):
        if self.resize_id:
            self.after_cancel(self.resize_id)
        self.resize_id=self.after(100,self._build_scene)

    def _build_scene(self):
        self.resize_id=None
        if not self.running:
            return
        w,h=self.winfo_width(),self.winfo_height()
        if w<20 or h<20:
            return
        self.delete("all")
        self.width,self.height=w,h
        self.cx,self.cy=w*.5,h*.45
        self.radius=min(w*.335,h*.345)
        cx,cy,r=self.cx,self.cy,self.radius
        for x in range(18,w,42):
            self.create_line(x,48,x,h-70,fill="#091b1c")
        for y in range(48,h-44,42):
            self.create_line(14,y,w-14,y,fill="#091b1c")
        # Soft atmosphere: these strokes are allocated once on resize.
        for k in range(15,0,-1):
            scale=k/15
            color=blend(BG,"#0f3c30",(1-scale)*.25)
            self.create_oval(cx-r*scale*1.4,cy-r*scale*1.3,cx+r*scale*1.4,cy+r*scale*1.3,
                             outline=color,width=max(2,r/13))
        rng=random.Random(2201)
        self.stars=[]
        for j in range(55):
            x,y=rng.uniform(18,w-18),rng.uniform(50,max(52,h-110))
            size=1.0 if j%9 else 1.6
            item=self.create_oval(x-size,y-size,x+size,y+size,fill="#2b7469",outline="")
            self.stars.append((item,rng.random()*math.tau))
        for n in range(120):
            a=math.radians(n*3)
            outer,inner=r*1.19,r*(1.15 if n%5==0 else 1.177)
            self.create_line(cx+inner*math.cos(a),cy+inner*math.sin(a),
                             cx+outer*math.cos(a),cy+outer*math.sin(a),
                             fill="#457d70" if n%5==0 else "#173d33")
        for radius in (r*1.07,r*1.22):
            self.create_oval(cx-radius,cy-radius,cx+radius,cy+radius,outline="#214a3b")
        for angle,label in ((-90,"000"),(0,"090"),(90,"180"),(180,"270")):
            a=math.radians(angle)
            self.create_text(cx+r*1.31*math.cos(a),cy+r*1.31*math.sin(a),
                             text=label,fill="#3c7163",font=("Consolas",7))
        for sign in (-1,1):
            y=cy+sign*r*.56
            self.create_line(20,y,cx-r*.9,y,cx-r*.65,y-sign*18,fill="#214b41",dash=(2,5))
            self.create_line(cx+r*.65,y-sign*18,cx+r*.9,y,w-20,y,fill="#214b41",dash=(2,5))
        self.rings=[]
        for index,(scale,extent,width) in enumerate(((1.14,59,2),(1.04,118,1),(1.25,26,2))):
            for offset in (0,180):
                item=self.create_arc(cx-r*scale,cy-r*scale,cx+r*scale,cy+r*scale,
                                     start=index*29+offset,extent=extent,style="arc",
                                     outline="#73dbaa",width=width)
                self.rings.append((item,index,offset))
        self.orbit_paths=[]
        for orbit in range(3):
            self.orbit_paths.append(self.create_line(0,0,1,1,fill=("#25483c","#3b6c50","#1d3939")[orbit],
                                                     width=1,smooth=True))
        self.mesh=[]
        for i in range(9):
            self.mesh.append(self.create_line(0,0,1,1,fill="#174234",width=1,smooth=True))
        self.ribbon_mesh=[]
        for strand in range(3):
            lines=[]
            for band in range(9):
                color=blend("#154338","#7fefb5",.22+(band/8)*.4)
                lines.append(self.create_line(0,0,1,1,fill=color,width=1,smooth=True))
            self.ribbon_mesh.append(lines)
        self.segments=[]
        # Pre-create and re-use every item, keeping animation allocation bounded.
        for strand in range(3):
            lines=[]
            for j in range(84):
                halo=self.create_line(0,0,1,1,fill="#0b2923",width=9,capstyle="round")
                glow=self.create_line(0,0,1,1,fill="#1b7258",width=3.7,capstyle="round")
                light=self.create_line(0,0,1,1,fill=CYAN,width=1.2,capstyle="round")
                lines.append((halo,glow,light))
            self.segments.append(lines)
        self.dust=[]
        for i in range(90):
            size=.75 if i%7 else 1.3
            item=self.create_oval(0,0,size*2,size*2,fill="#5aa887",outline="")
            self.dust.append((item,rng.uniform(0,math.tau),rng.uniform(.7,1.3),size,rng.uniform(-.8,.8)))
        self.satellites=[]
        for i in range(3):
            halo=self.create_oval(0,0,1,1,fill="#10362e",outline="")
            glow=self.create_oval(0,0,1,1,fill="#2f8976",outline="")
            dot=self.create_oval(0,0,1,1,fill="#c4ffdc",outline="")
            self.satellites.append((halo,glow,dot))
        self.create_line(cx-8,cy,cx+8,cy,fill="#70a58f")
        self.create_line(cx,cy-8,cx,cy+8,fill="#70a58f")
        self.create_oval(cx-2,cy-2,cx+2,cy+2,outline="#c5ffcf")
        label_y=min(h-133,cy+r*1.43)
        self.core_label=self.create_text(cx,label_y,text="S T A N D B Y",
                                          fill="#b6fbd6",font=("Consolas",13,"bold"))
        self.core_sub=self.create_text(cx,label_y+24,text="等待指令 · 麦克风未启用",
                                        fill="#669f87",font=("Microsoft YaHei UI",8))
        self.create_text(20,20,anchor="w",text="HOLOGRAPHIC INTERFACE  /  01",fill="#8bd6bb",font=("Consolas",9))
        self.create_text(w-20,20,anchor="e",text="ENERGY FIELD",fill="#4c8c77",font=("Consolas",8))
        self.create_line(20,38,w-20,38,fill="#235144")
        self.mode_text=self.create_text(23,58,anchor="w",text="SIMULATION",fill="#568b75",font=("Consolas",8))
        self.mic_text=self.create_text(w-23,58,anchor="e",text="MIC / OFF",fill="#568b75",font=("Consolas",8))
        self.create_text(20,h-82,anchor="w",text="AUDIO SPECTRUM",fill="#85bfa6",font=("Consolas",8))
        self.wave_caption=self.create_text(w-20,h-82,anchor="e",text="待机动效",fill="#4d8170",font=("Microsoft YaHei UI",8))
        self.bars=[]
        for n in range(60):
            x=22+n*(w-44)/60
            self.bars.append(self.create_rectangle(x,h-47,x+max(2,(w-44)/60-3),h-44,fill="#57b98c",outline=""))
        self.create_line(20,h-25,w-20,h-25,fill="#214538")
        self.stats_text=self.create_text(20,h-11,anchor="w",text="",fill="#588d74",font=("Consolas",7))
        self.frame_text=self.create_text(w-20,h-11,anchor="e",text="",fill="#588d74",font=("Consolas",7))
        self.scan=self.create_line(18,70,w-18,70,fill="#15372c")
        for x,y,dx,dy in ((8,7,1,1),(w-8,7,-1,1),(8,h-7,1,-1),(w-8,h-7,-1,-1)):
            self.create_line(x,y+dy*15,x,y,x+dx*28,y,fill="#5cb594",width=2)
        self.scene=True
        self._draw(time.perf_counter()-self.started,self.snapshot())

    def _draw(self,elapsed,state):
        cx,cy,r=self.cx,self.cy,self.radius
        status=state.get("state","STANDBY")
        self.level+=(state.get("level",0.0)-self.level)*.36
        activity=status in ("LISTENING","SPEAKING")
        pulse=1+.017*math.sin(elapsed*1.8)+(self.level*.11 if activity else 0)
        spin,phase=elapsed*.14,elapsed*.32
        for item,index,offset in self.rings:
            direction=1 if index%2 else -1
            self.itemconfigure(item,start=(offset+index*29+elapsed*(9+index*4)*direction)%360)
        for orbit,item in enumerate(self.orbit_paths):
            coords=[]
            for j in range(65):
                t=j/64*math.tau
                x,y,_=project(1.2*math.cos(t),.48*math.sin(t),.18*math.sin(t+orbit),orbit*1.05+.2)
                coords.extend((cx+x*r,cy+y*r))
            self.coords(item,*coords)
        for i,item in enumerate(self.mesh):
            latitude=(i-4)*.17
            coords=[]
            for j in range(49):
                t=j/48*math.tau
                rr=math.sqrt(max(0,1-latitude*latitude))*.91
                x,y,_=project(rr*math.cos(t),latitude,rr*math.sin(t),spin*.3,.3)
                coords.extend((cx+x*r,cy+y*r))
            self.coords(item,*coords)
        for strand,lines in enumerate(self.ribbon_mesh):
            for band,item in enumerate(lines):
                coords=[]
                for x,y,z in ribbon_points(phase,strand,64,pulse,(band-4)*.014):
                    xx,yy,_=project(x,y,z,spin,.65)
                    coords.extend((cx+xx*r,cy+yy*r))
                self.coords(item,*coords)
        recolor=self.frame_count%3==0 or status!=self._last_status
        for strand,lines in enumerate(self.segments):
            projected=[project(x,y,z,spin,.65) for x,y,z in ribbon_points(phase,strand,84,pulse)]
            for j,(halo,glow,light) in enumerate(lines):
                x,y,depth=projected[j]
                nx,ny,nd=projected[j+1]
                coords=(cx+x*r,cy+y*r,cx+nx*r,cy+ny*r)
                for item in (halo,glow,light):
                    self.coords(item,*coords)
                if recolor:
                    luminance=.27+.73*((depth+nd)*.5+.58)/1.16
                    hue=blend("#49efcf","#d1ff8f",(math.sin(j*.075+strand*1.7)+1)*.5)
                    self.itemconfigure(halo,fill=blend(BG,hue,luminance*.10))
                    self.itemconfigure(glow,fill=blend(BG,hue,luminance*.28))
                    self.itemconfigure(light,fill=blend(BG,hue,min(1,luminance*.95)))
        for i,(item,angle,distance,size,vertical) in enumerate(self.dust):
            a=angle+elapsed*(.045+(i%5)*.006)
            x,y,z=project(distance*math.cos(a),vertical,distance*math.sin(a),spin*.2,.48)
            px,py=cx+x*r,cy+y*r
            self.coords(item,px-size,py-size,px+size,py+size)
            if recolor:
                self.itemconfigure(item,fill=blend(BG,"#bbffd5",.25+.5*(z+1.3)/2.6))
        for i,(halo,glow,dot) in enumerate(self.satellites):
            a=elapsed*(.18+i*.025)+i*2.1
            x,y,_=project(1.21*math.cos(a),.43*math.sin(a),.2*math.sin(a+i),i*1.05+.2)
            px,py=cx+x*r,cy+y*r
            for item,size in ((halo,9),(glow,4),(dot,1.7)):
                self.coords(item,px-size,py-size,px+size,py+size)
        if recolor:
            for item,seed in self.stars:
                self.itemconfigure(item,fill=blend(BG,"#b2ffe0",.18+.22*(math.sin(elapsed*.8+seed)+1)*.5))
        h=self.height
        for i,item in enumerate(self.bars):
            shape=math.sin(i*.68+elapsed*5)**2*.6+math.sin(i*.23-elapsed*3)**2*.4
            height=2+shape*(4 if not activity else 3+self.level*110)
            coords=self.coords(item)
            self.coords(item,coords[0],h-44-min(26,height),coords[2],h-44)
        if self.frame_count%6==0 or status!=self._last_status:
            labels={
                "STANDBY":("S T A N D B Y","等待指令 · 麦克风未启用"),
                "LISTENING":("L I S T E N I N G","正在录音 · 再按 F8 结束"),
                "THINKING":("P R O C E S S I N G","正在处理您的指令"),
                "SPEAKING":("V O I C E   O U T","正在生成或播放语音"),
                "ERROR":("A T T E N T I O N","请查看右侧操作提示"),
            }
            title,subtitle=labels.get(status,labels["STANDBY"])
            self.itemconfigure(self.core_label,text=title,fill="#ffd49c" if status=="ERROR" else "#c3ffdb")
            self.itemconfigure(self.core_sub,text=subtitle)
            self.itemconfigure(self.mode_text,text="SIMULATION / LOCAL" if state.get("mock",True) else "CLOUD / API MODE")
            self.itemconfigure(self.mic_text,text="MIC / REC" if state.get("capturing",False) else "MIC / OFF")
            self.itemconfigure(self.wave_caption,text="实际音量 · INPUT" if state.get("capturing",False) else
                               ("实际音量 · OUTPUT" if status=="SPEAKING" else "待机动效 · 未监听"))
            self.itemconfigure(self.stats_text,text=f"MEMORY {state.get('memories',0):03d}  /  SESSIONS {state.get('sessions',0):03d}  /  AUDIO {state.get('devices',0):02d}")
            fps=24 if self.quality=="high" else 12 if self.quality=="low" else 0
            self.itemconfigure(self.frame_text,text=f"FX {fps:02d}  /  {self.frame_ms:04.1f} ms")
            self._last_status=status
        scan_y=65+(elapsed*16)%max(1,h-170)
        self.coords(self.scan,18,scan_y,self.width-18,scan_y)

    def _tick(self):
        self.after_id=None
        if not self.running:
            return
        active=self.winfo_viewable() and self.winfo_toplevel().state()!="iconic"
        interval=42 if self.quality=="high" else 84 if self.quality=="low" else 300
        if self.scene and active:
            begin=time.perf_counter()
            elapsed=begin-self.started if self.quality!="off" else 0
            self._draw(elapsed,self.snapshot())
            self.frame_ms=(time.perf_counter()-begin)*1000
            self.frame_times.append(self.frame_ms)
            self.frame_count+=1
            if self.quality=="high" and self.frame_ms>35:
                interval=max(interval,84)
        self.after_id=self.after(interval if active else 350,self._tick)

    def stop(self):
        self.running=False
        for task in (self.after_id,self.resize_id):
            if task:
                try:
                    self.after_cancel(task)
                except tk.TclError:
                    pass
        self.after_id=self.resize_id=None