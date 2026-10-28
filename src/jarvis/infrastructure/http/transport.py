"""HTTP transport policy shared by provider adapters."""
from urllib import request

class NoRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None  # Never forward a bearer token to a redirected host.
