"""Loopback map-cookie authentication policy."""
from http.cookies import SimpleCookie
from urllib import parse

def proxy_authorized(headers,token,origin,port):
    if headers.get("Host")!=f"127.0.0.1:{port}":return False
    if headers.get("Origin") not in (None,origin):return False
    if headers.get("Sec-Fetch-Site")=="cross-site":return False
    try:
        cookie=SimpleCookie()
        cookie.load(headers.get("Cookie",""))
        return "jarvis_map_gate" in cookie and cookie["jarvis_map_gate"].value==token
    except Exception:
        return False
