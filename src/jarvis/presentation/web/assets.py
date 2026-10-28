"""Bounded static resource lookup and compatibility URLs for existing diagnostics."""
from pathlib import Path
from urllib.parse import unquote

ASSET_ROOT=Path(__file__).parent/"assets"
MODULE_ALIASES={
    "/visual.js":"rendering/energy.js", "/city.js":"rendering/city.js",
    "/navigation.js":"features/navigation/controller.js",
    "/map_controls.js":"features/map/controls.js", "/places.js":"features/navigation/places.js",
}
MIMES={".js":"text/javascript; charset=utf-8", ".css":"text/css; charset=utf-8", ".txt":"text/plain; charset=utf-8"}

def read_asset(path):
    if path in MODULE_ALIASES:
        return 'export * from "/'+MODULE_ALIASES[path]+'";',MIMES[".js"],False
    if path=="/scene.js":
        return 'import("/app.js");',MIMES[".js"],False
    if path=="/style.css":
        return '@import url("/styles/main.css");',MIMES[".css"],False
    decoded=unquote(path)
    if not decoded.startswith("/") or "\\" in decoded or any(p in (".","..") for p in decoded.split("/")):
        return None
    resource=(ASSET_ROOT/("index.html" if decoded=="/" else decoded.lstrip("/"))).resolve()
    if not resource.is_relative_to(ASSET_ROOT.resolve()) or not resource.is_file():
        return None
    if decoded=="/":
        return resource.read_text(encoding="utf-8"),"text/html; charset=utf-8",True
    if resource.suffix not in MIMES:return None
    return resource.read_bytes(),MIMES[resource.suffix],False
