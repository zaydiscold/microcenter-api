"""Anonymous browser transport; does not attach to user pages or copy login state."""

import re
from urllib.parse import urlsplit
from .errors import BlockedError, MicroCenterError, RateLimitedError


class BrowserTransport:
    def __init__(self, *, cdp_url=None, headed=False):
        self.cdp_url = cdp_url
        self.headed = headed
        self.pw = None
        self.browser = None
        self.context = None
        self.page = None
        self.before_request = lambda: None

    def _start(self):
        if self.page:
            return
        from playwright.sync_api import sync_playwright

        self.pw = sync_playwright().start()
        try:
            self.browser = (
                self.pw.chromium.connect_over_cdp(self.cdp_url)
                if self.cdp_url
                else self.pw.chromium.launch(headless=not self.headed)
            )
            self.context = self.browser.new_context()
            self.context.route(
                "**/*",
                lambda route: (
                    route.abort()
                    if route.request.resource_type in {"image", "font", "media"}
                    else route.continue_()
                ),
            )
            self.page = self.context.new_page()
            self.before_request()
            self.page.goto(
                "https://www.microcenter.com/search/search_results.aspx?Ntt=filament&storeid=195&rpp=24",
                wait_until="domcontentloaded",
                timeout=45000,
            )
            # Do not automate challenge solving or rotate identities.
            self.page.wait_for_function(
                "! /Just a moment|Access Denied/i.test(document.title)", timeout=15000
            )
        except Exception as e:
            self.close()
            raise BlockedError(
                "Anonymous browser could not open the storefront. Try --headed for a normal visible session; no scan was started."
            ) from e

    def fetch(self, url, form=None):
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.netloc != "www.microcenter.com":
            raise ValueError("Only the public Micro Center origin is allowed")
        self._start()
        self.before_request()
        try:
            result = self.page.evaluate(
                """async ({url,form})=>{const r=await fetch(url,{method:form?'POST':'GET',headers:{'X-Requested-With':'XMLHttpRequest',...(form?{'Content-Type':'application/x-www-form-urlencoded'}:{})},...(form?{body:new URLSearchParams(form).toString()}:{}),redirect:'error',signal:AbortSignal.timeout(30000)});return {status:r.status,html:await r.text(),retry_after:r.headers.get('Retry-After')}}""",
                {"url": url, "form": form},
            )
        except Exception as e:
            raise MicroCenterError(
                "Public storefront request failed; checkpoint retained"
            ) from e
        if result["status"] in {401, 403} or re.search(
            r"<title>\s*(?:Just a moment|Access Denied)", result["html"], re.I
        ):
            raise BlockedError(
                "Storefront blocked/challenged the request. Stopping without retries or identity rotation."
            )
        if result["status"] == 429:
            raise RateLimitedError(result["retry_after"])
        if result["status"] != 200:
            raise MicroCenterError(f"Storefront returned HTTP {result['status']}")
        return result["html"]

    def close(self):
        try:
            if self.context:
                self.context.close()
            if self.browser and not self.cdp_url:
                self.browser.close()
        finally:
            if self.pw:
                self.pw.stop()
            self.pw = self.browser = self.context = self.page = None


class CDPTransport(BrowserTransport):
    """Minimal CDP connection: only our new context; never enumerate/attach user tabs."""

    def __init__(self, *, cdp_url):
        super().__init__(cdp_url=cdp_url)
        self.socket = None
        self.seq = 0
        self.session = None
        self.context_id = None

    def _send(self, method, params=None, session=True):
        import json, time

        self.seq += 1
        request = {"id": self.seq, "method": method, "params": params or {}}
        if session and self.session:
            request["sessionId"] = self.session
        try:
            self.socket.send(json.dumps(request))
        except Exception as e:
            raise MicroCenterError(
                "Chromium connection failed while sending a command"
            ) from e
        deadline = time.monotonic() + 35
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise MicroCenterError("Chromium operation exceeded its deadline")
            try:
                self.socket.settimeout(remaining)
            except Exception as e:
                raise MicroCenterError("Chromium connection is unavailable") from e
            try:
                message = json.loads(self.socket.recv())
            except Exception as e:
                raise MicroCenterError("Chromium connection failed or timed out") from e
            if message.get("id") == self.seq:
                if "error" in message:
                    raise MicroCenterError(
                        "Chromium rejected the catalog operation: "
                        + message["error"].get("message", "protocol error")
                    )
                return message.get("result", {})

    def _start(self):
        if self.page:
            return
        import json, time, urllib.request
        from websocket import create_connection

        # Debug endpoints are privileged; only loopback addresses are accepted.
        u = urlsplit(self.cdp_url)
        if u.scheme != "http" or u.hostname not in {"127.0.0.1", "localhost", "::1"}:
            raise ValueError("CDP endpoint must be loopback HTTP")
        try:
            with urllib.request.urlopen(
                self.cdp_url.rstrip("/") + "/json/version", timeout=5
            ) as r:
                info = json.load(r)
            ws = info["webSocketDebuggerUrl"]
            target = urlsplit(ws)
            if target.hostname not in {"127.0.0.1", "localhost", "::1"}:
                raise ValueError("Debug websocket must be loopback")
            self.socket = create_connection(ws, timeout=35, suppress_origin=True)
            self.context_id = self._send(
                "Target.createBrowserContext", {"disposeOnDetach": True}, False
            )["browserContextId"]
            tid = self._send(
                "Target.createTarget",
                {"url": "about:blank", "browserContextId": self.context_id},
                False,
            )["targetId"]
            self.session = self._send(
                "Target.attachToTarget", {"targetId": tid, "flatten": True}, False
            )["sessionId"]
            self._send("Page.enable")
            self._send("Network.enable")
            self._send(
                "Network.setBlockedURLs",
                {
                    "urls": [
                        "*.jpg",
                        "*.jpeg",
                        "*.png",
                        "*.webp",
                        "*.gif",
                        "*.woff",
                        "*.woff2",
                        "*.mp4",
                    ]
                },
            )
            self.before_request()
            self._send(
                "Page.navigate",
                {
                    "url": "https://www.microcenter.com/search/search_results.aspx?Ntt=filament&storeid=195&rpp=24"
                },
            )
            for _ in range(30):
                r = self._send(
                    "Runtime.evaluate",
                    {
                        "expression": 'location.hostname === "www.microcenter.com" && document.readyState === "complete" && !/Just a moment|Access Denied/i.test(document.title)',
                        "returnByValue": True,
                    },
                )
                if r.get("result", {}).get("value"):
                    self.page = True
                    return
                time.sleep(1)
            raise BlockedError("Anonymous debug browser did not become ready")
        except Exception:
            self.close()
            raise

    def fetch(self, url, form=None):
        import json

        u = urlsplit(url)
        if u.scheme != "https" or u.netloc != "www.microcenter.com":
            raise ValueError("Only the public Micro Center origin is allowed")
        self._start()
        self.before_request()
        script = (
            """(async ({url,form})=>{const r=await fetch(url,{method:form?'POST':'GET',headers:{'X-Requested-With':'XMLHttpRequest',...(form?{'Content-Type':'application/x-www-form-urlencoded'}:{})},...(form?{body:new URLSearchParams(form).toString()}:{}),redirect:'error',signal:AbortSignal.timeout(30000)});return {status:r.status,html:await r.text(),retry_after:r.headers.get('Retry-After')}})("""
            + json.dumps({"url": url, "form": form})
            + ")"
        )
        result = self._send(
            "Runtime.evaluate",
            {"expression": script, "awaitPromise": True, "returnByValue": True},
        )
        if result.get("exceptionDetails"):
            raise MicroCenterError(
                "Public storefront request failed; checkpoint retained"
            )
        response = result.get("result", {}).get("value")
        if not isinstance(response, dict):
            raise MicroCenterError("Invalid browser response")
        if response["status"] in {401, 403} or re.search(
            r"<title>\s*(?:Just a moment|Access Denied)", response["html"], re.I
        ):
            raise BlockedError("Storefront blocked/challenged this request; stopping")
        if response["status"] == 429:
            raise RateLimitedError(response["retry_after"])
        if response["status"] != 200:
            raise MicroCenterError(f"Storefront returned HTTP {response['status']}")
        return response["html"]

    def close(self):
        try:
            if self.socket and self.context_id:
                self._send(
                    "Target.disposeBrowserContext",
                    {"browserContextId": self.context_id},
                    False,
                )
        finally:
            if self.socket:
                self.socket.close()
            self.socket = self.page = self.session = self.context_id = None
