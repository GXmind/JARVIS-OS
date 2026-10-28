"""Bounded real OSM building/road geometry, aligned to AMap GCJ-02 route coordinates."""
import hashlib,json,math,re,threading,time,subprocess,os
from concurrent.futures import ThreadPoolExecutor
from .vector_city import decode_tile
from urllib import request,parse
from .paths import ROOT
from .api import ServiceError,NoRedirect
from .vendor.eviltransform import gcj2wgs_exact,wgs2gcj

_lock=threading.Lock()
_last_request=0.0
_download_guard=threading.Lock()
_download_locks={}

def number(value,default):
    match=re.search(r"-?\d+(?:\.\d+)?",str(value))
    return float(match.group()) if match else default

def validated_path(points):
    if not isinstance(points,list) or not 1<=len(points)<=2000:raise ServiceError("城市范围坐标无效。")
    result=[]
    for point in points:
        if not isinstance(point,(list,tuple)) or len(point)!=2:raise ServiceError("城市范围坐标无效。")
        lng,lat=map(float,point)
        if not all(map(math.isfinite,(lng,lat))) or not 73<=lng<=136 or not 18<=lat<=54:
            raise ServiceError("城市范围超出当前支持区域。")
        result.append((lng,lat))
    return result

def parse_elements(raw):
    buildings=[];roads=[]
    for item in raw.get("elements",[]):
        tags=item.get("tags",{});geometry=item.get("geometry",[])
        if item.get("type")!="way" or len(geometry)<2:continue
        points=[]
        for point in geometry[:160]:
            if "lat" not in point or "lon" not in point:continue
            lat,lng=wgs2gcj(float(point["lat"]),float(point["lon"]))
            points.append([lng,lat])
        if len(points)<2:continue
        if tags.get("building") and len(points)>=4 and len(buildings)<1800:
            measured=bool(tags.get("height") or tags.get("building:levels"))
            height=number(tags.get("height"),number(tags.get("building:levels"),4)*3)
            buildings.append({"id":item["id"],"footprint":points,"height":min(350,max(3,height)),
                              "height_source":"tagged" if measured else "estimated"})
        elif tags.get("highway") and len(roads)<1500:
            roads.append({"id":item["id"],"path":points,"kind":tags["highway"],"name":tags.get("name","")[:60]})
    return {"buildings":buildings,"roads":roads,
            "source":"OpenStreetMap contributors","license":"ODbL",
            "height_note":"未标注楼高按示意高度显示；高度有视觉夸张，非测绘建筑模型。",
            "timestamp":raw.get("osm3s",{}).get("timestamp_osm_base")}

def download_public(url,path,ttl=604800):
    with _download_guard:lock=_download_locks.setdefault(str(path),threading.Lock())
    with lock:return _download_public(url,path,ttl)

def _download_public(url,path,ttl=604800):
    if path.exists() and time.time()-path.stat().st_mtime<ttl:return path.read_bytes()
    temporary=path.with_suffix(path.suffix+".download")
    try:
        process=subprocess.run(["curl.exe","--silent","--show-error","--fail","--location","--compressed",
            "--max-time","16","--max-filesize","2500000","--ssl-revoke-best-effort","--noproxy","*",
            "--user-agent","JARVIS-Private-Particle-City/0.3","--output",str(temporary),url],
            cwd=ROOT,stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL,timeout=19,
            creationflags=getattr(subprocess,"CREATE_NO_WINDOW",0))
        if process.returncode:raise OSError("City tile unavailable")
        temporary.replace(path);return path.read_bytes()
    finally:temporary.unlink(missing_ok=True)

def tile_zoom_for_bounds(bbox,overview=False):
    if not overview:return 14
    south,west,north,east=bbox
    for zoom in range(14,2,-1):
        n=2**zoom
        def tile(lng,lat):
            return int((lng+180)/360*n),int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)
        x0,y0=tile(west,north);x1,y1=tile(east,south)
        if x1-x0<3 and y1-y0<3:return zoom
    return 3


def vector_context(bbox,center,cache_dir,overview=False):
    manifest=json.loads(download_public("https://tiles.openfreemap.org/planet",cache_dir/"tilejson.json",86400))
    pattern=manifest["tiles"][0]
    if not pattern.startswith("https://tiles.openfreemap.org/planet/"):raise ValueError("Unexpected tile host")
    z=tile_zoom_for_bounds(bbox,overview);n=2**z
    def tile(lng,lat):
        return int((lng+180)/360*n),int((1-math.asinh(math.tan(math.radians(lat)))/math.pi)/2*n)
    south,west,north,east=bbox
    x0,y0=tile(west,north);x1,y1=tile(east,south)
    cx,cy=tile((west+east)/2,(south+north)/2)
    coords=[(x,y) for x in range(max(x0,cx-1),min(x1,cx+1)+1) for y in range(max(y0,cy-1),min(y1,cy+1)+1)]
    tiles_dir=cache_dir/"tiles";tiles_dir.mkdir(exist_ok=True)
    def fetch(coord):
        x,y=coord
        try:
            url=pattern.replace("{z}",str(z)).replace("{x}",str(x)).replace("{y}",str(y))
            version=pattern.split("/planet/")[1].split("/")[0]
            path=tiles_dir/(version+"_"+str(z)+"_"+str(x)+"_"+str(y)+".pbf")
            return decode_tile(download_public(url,path),x,y,z)
        except Exception:return None
    with ThreadPoolExecutor(max_workers=4) as pool:results=list(pool.map(fetch,coords))
    results=[row for row in results if row]
    if not results:raise ValueError("No vector tiles downloaded")
    buildings=[];roads=[];labels=[];seen_buildings=set();seen_roads=set();seen_labels=set()
    def intersects(points):
        return bool(points) and max(p[0] for p in points)>=west and min(p[0] for p in points)<=east and max(p[1] for p in points)>=south and min(p[1] for p in points)<=north
    def geometry_key(item,key):
        points=item[key]
        # Preserve distinct tile-clipped fragments and separate building parts.
        return (item.get("id"),tuple(sorted((round(p[0],7),round(p[1],7)) for p in points)))
    for row in results:
        for building in row["buildings"]:
            if not intersects(building["footprint"]):continue
            key=(geometry_key(building,"footprint"),building["height"],building.get("min_height",0))
            if key not in seen_buildings:seen_buildings.add(key);buildings.append(building)
        for road in row["roads"]:
            if not intersects(road["path"]):continue
            key=geometry_key(road,"path")
            if key not in seen_roads:seen_roads.add(key);roads.append(road)
        for label in row.get("labels",[]):
            lng,lat=label["location"];key=(label["name"],round(lng,5),round(lat,5))
            if west<=lng<=east and south<=lat<=north and key not in seen_labels:seen_labels.add(key);labels.append(label)
    def near(item):
        points=item.get("footprint") or item.get("path") or [[0,0]]
        return min((p[0]-center[0])**2+(p[1]-center[1])**2 for p in points)
    buildings.sort(key=near);roads.sort(key=near)
    labels.sort(key=lambda p:(p["location"][0]-center[0])**2+(p["location"][1]-center[1])**2)
    return {"buildings":buildings[:3600],"roads":roads[:4000],"labels":labels[:80],"status":"live",
            "source":"OpenFreeMap / OpenMapTiles / OpenStreetMap contributors","license":"ODbL",
            "height_note":"真实建筑轮廓；数据源高度可能为近似值，显示倍率单独控制，非测绘模型。",
            "center_gcj02":list(center),"tiles_loaded":len(results),"tiles_expected":len(coords),
            "geometry_version":3,"tile_zoom":z,"coordinate_system":"GCJ-02",
            "coverage":"complete" if len(results)==len(coords) and len(coords)==(x1-x0+1)*(y1-y0+1) else "partial",
            "limits":{"buildings":3600,"roads":4000},
            "precision_note":"使用数据源最高 z14 矢量；保留内院与建筑底高，不宣称超出数据源的测绘精度。"}


def city_context(points,overview=False):
    global _last_request
    points=validated_path(points)
    west,east=min(p[0] for p in points),max(p[0] for p in points)
    south,north=min(p[1] for p in points),max(p[1] for p in points)
    center=((west+east)/2,(south+north)/2)
    lat,lng=gcj2wgs_exact(center[1],center[0])
    # Context is bounded to a local 5 km district; long routes remain fully rendered.
    if overview:
        dx=max(.009,(east-west)/2+.004);dy=max(.008,(north-south)/2+.004)
    else:
        dx=min(.027,max(.009,(east-west)/2+.004));dy=min(.024,max(.008,(north-south)/2+.004))
    bbox=[round(lat-dy,5),round(lng-dx,5),round(lat+dy,5),round(lng+dx,5)]
    cache_dir=ROOT/"cache/city";cache_dir.mkdir(exist_ok=True)
    cache=cache_dir/(hashlib.sha256(json.dumps(["v4-view",bbox,overview]).encode()).hexdigest()[:20]+".json")
    try:
        data=json.loads(cache.read_text(encoding="utf-8"))
        if time.time()-cache.stat().st_mtime<7*86400:return {**data,"status":"cached"}
    except (OSError,ValueError):data=None
    try:
        result=vector_context(bbox,center,cache_dir,overview=overview)
        result["bbox_wgs84"]=bbox
        temporary=cache.with_name(cache.name+"."+str(threading.get_ident())+".tmp")
        temporary.write_text(json.dumps(result,ensure_ascii=False),encoding="utf-8");temporary.replace(cache)
        return result
    except Exception:pass
    if overview:
        if data:return {**data,"status":"stale"}
        return {"buildings":[],"roads":[],"labels":[],"status":"unavailable","coverage":"unavailable",
                "source":"OpenFreeMap / OpenMapTiles / OpenStreetMap contributors","license":"ODbL",
                "center_gcj02":list(center)}
    query="[out:json][timeout:14];(way[building]("+",".join(map(str,bbox))+");way[highway]("+",".join(map(str,bbox))+"););out tags geom;"
    payload=parse.urlencode({"data":query}).encode()
    with _lock:
        # Cache repeated requests inside the lock as well.
        try:
            if cache.exists() and time.time()-cache.stat().st_mtime<7*86400:
                return {**json.loads(cache.read_text(encoding="utf-8")),"status":"cached"}
        except (OSError,ValueError):pass
        pause=max(0,1.1-(time.monotonic()-_last_request))
        if pause:time.sleep(pause)
        _last_request=time.monotonic()
        for direct in (True,):
            opener=request.build_opener(*( [request.ProxyHandler({}),NoRedirect()] if direct else [NoRedirect()] ))
            try:
                req=request.Request("https://overpass-api.de/api/interpreter",data=payload,
                    headers={"User-Agent":"JARVIS-Desktop-Private-MVP/0.3","Content-Type":"application/x-www-form-urlencoded"})
                with opener.open(req,timeout=8) as response:body=response.read(6_000_001)
                if len(body)>6_000_000:raise ValueError("City data too large")
                parsed=parse_elements(json.loads(body))
                result={**parsed,"bbox_wgs84":bbox,"center_gcj02":list(center),"status":"live"}
                temporary=cache.with_name(cache.name+"."+str(threading.get_ident())+".tmp")
                temporary.write_text(json.dumps(result,ensure_ascii=False),encoding="utf-8");temporary.replace(cache)
                return result
            except Exception:continue
    if data:return {**data,"status":"stale"}
    return {"buildings":[],"roads":[],"status":"unavailable","center_gcj02":list(center),
            "source":"OpenStreetMap contributors","license":"ODbL",
            "height_note":"周边楼宇数据暂不可用；仅显示高德真实路线，未生成虚构楼宇。"}