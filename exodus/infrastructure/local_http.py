"""HTTP transport for the local Ollama and Qdrant services.

Proxy environment variables must not route source excerpts and documentation elsewhere.
Local APIs do not use redirects, so a redirect is an error rather than another request.
"""

from urllib.request import HTTPRedirectHandler, ProxyHandler, build_opener


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args: object, **kwargs: object) -> None:
        return None


DIRECT_OPENER = build_opener(ProxyHandler({}), _NoRedirect())
