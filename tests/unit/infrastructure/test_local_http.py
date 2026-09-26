from urllib.request import HTTPRedirectHandler, ProxyHandler, Request

from exodus.infrastructure.local_http import DIRECT_OPENER


def test_local_transport_ignores_environment_proxies_and_redirects() -> None:
    proxies = [h for h in DIRECT_OPENER.handlers if isinstance(h, ProxyHandler)]
    assert all(handler.proxies == {} for handler in proxies)

    redirects = [h for h in DIRECT_OPENER.handlers if isinstance(h, HTTPRedirectHandler)]
    assert len(redirects) == 1
    assert (
        redirects[0].redirect_request(
            Request("http://localhost:11434"), None, 302, "Found", {}, "https://example.com"
        )
        is None
    )
