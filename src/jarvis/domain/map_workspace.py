"""Independent transferred map seed and bounded primary-camera input mailbox."""
import json
import math
import threading
import time
from jarvis.domain.errors import ServiceError

VIEW_LIMITS={"cityYaw":(-1000000,1000000),"cityPitch":(.08,1.45),"cityZoom":(.45,4),"cityPanX":(-10000,10000),"cityPanY":(-10000,10000)}
MAX_SNAPSHOT_BYTES=4_000_000

def finite(value,low,high):
    return not isinstance(value,bool) and isinstance(value,(int,float)) and math.isfinite(value) and low<=value<=high

class MapWorkspace:
    def __init__(self,clock=time.monotonic):
        self.lock=threading.RLock();self.clock=clock
        self.revision=0;self.snapshot=None;self.transfer_snapshot=None;self.transfer_revision=0;self.epoch=0
        self.requested=False;self.detached=False;self.last_seen=0
        self.commands=[];self.sequence=0;self.direction={"x":1,"y":0}

    def publish(self,snapshot):
        if not isinstance(snapshot,dict) or not isinstance(snapshot.get("state"),dict):raise ServiceError("地图状态格式无效。")
        try:encoded=json.dumps(snapshot,ensure_ascii=False,allow_nan=False)
        except (ValueError,TypeError):raise ServiceError("地图状态包含无效数值。") from None
        if len(encoded.encode("utf-8"))>MAX_SNAPSHOT_BYTES:raise ServiceError("地图同步数据超过预算。")
        with self.lock:
            current=snapshot.get("command",{}).get("id",0)
            if not isinstance(current,int) or isinstance(current,bool) or current<0:raise ServiceError("地图请求标识无效。")
            if "base_revision" in snapshot and snapshot["base_revision"]!=self.revision:raise ServiceError("地图发布已过期，请重试。")
            self.snapshot=json.loads(encoded);self.revision+=1
            # Never mutate the transferred copy when the primary talks, closes navigation or plans another trip.
            return self.metadata()

    def metadata(self):
        with self.lock:
            return {"revision":self.revision,"transfer_revision":self.transfer_revision,"epoch":self.epoch,
                "requested":self.requested,"detached":self.detached,"connected":self.requested and self.clock()-self.last_seen<12,
                "direction":dict(self.direction)}

    def request_detach(self,direction=None):
        with self.lock:
            if self.requested:raise ServiceError("副屏已有独立地图，请先在副屏关闭后再传送。")
            if not self.snapshot or not self.snapshot["state"].get("mapReady"):raise ServiceError("请先完成地图加载，再传送到另一屏。")
            self.epoch+=1;self.transfer_revision+=1;self.requested=True;self.detached=False;self.last_seen=self.clock();self.commands=[]
            self.transfer_snapshot=json.loads(json.dumps(self.snapshot))
            self.direction={"x":0 if direction in ("up","down") else -1 if direction=="left" else 1,"y":1 if direction=="up" else -1 if direction=="down" else 0}
            return self.metadata()

    def set_direction(self,value):
        if isinstance(value,dict) and finite(value.get("x"),-1,1) and finite(value.get("y"),-1,1):
            with self.lock:self.direction={"x":value["x"],"y":value["y"]}

    def replica_poll(self,since=-1,after=0):
        with self.lock:
            self.last_seen=self.clock();self.commands=[c for c in self.commands if c["sequence"]>after]
            meta=self.metadata();meta["commands"]=list(self.commands)
            if since!=self.transfer_revision:meta["snapshot"]=self.transfer_snapshot
            return meta

    def replica_ready(self,epoch,revision):
        with self.lock:
            if not self.requested or epoch!=self.epoch or revision!=self.transfer_revision:raise ServiceError("地图窗口已过期，请重新传送。")
            self.last_seen=self.clock();self.detached=True
            return self.metadata()

    def patch_view(self,values):
        view=values.get("view",{})
        for key,(low,high) in {**VIEW_LIMITS,"cityHeightScale":(1,32)}.items():
            if not finite(view.get(key),low,high):raise ServiceError("地图视角数值无效。")
        with self.lock:
            if self.snapshot is None:raise ServiceError("地图尚未准备。")
            self.snapshot["state"].update({key:view[key] for key in (*VIEW_LIMITS,"cityHeightScale")})
            return self.metadata()

    def enqueue(self,values):
        action=values.get("action",{});kind=action.get("type")
        if kind in ("pan","orbit"):
            if not finite(action.get("dx"),-.08,.08) or not finite(action.get("dy"),-.08,.08):raise ServiceError("手势移动数值无效。")
            payload={"type":kind,"dx":action["dx"],"dy":action["dy"]}
        elif kind=="zoom":
            if not finite(action.get("factor"),.8,1.25):raise ServiceError("手势缩放数值无效。")
            payload={"type":kind,"factor":action["factor"]}
        elif kind=="end":payload={"type":"end","commit":True}
        else:raise ServiceError("手势操作无效。")
        with self.lock:
            if not self.detached or values.get("epoch")!=self.epoch:raise ServiceError("副屏地图尚未连接或手势已过期。")
            self.sequence+=1;payload["sequence"]=self.sequence;self.commands.append(payload);self.commands=self.commands[-32:]
            return {"ok":True,"sequence":self.sequence}

    def primary_poll(self,after=0):return self.metadata()

    def close_map(self):
        """Close only the independent map; primary content remains untouched."""
        with self.lock:
            if self.requested or self.detached:self.epoch+=1
            self.requested=False;self.detached=False;self.commands=[];self.transfer_snapshot=None
            return self.metadata()
