"""Native Windows shell for Duo Hub using pywebview and Edge WebView2."""

from __future__ import annotations

import json
import os
import threading
import time
import urllib.request

os.environ.setdefault("DUO_NO_BROWSER", "1")
os.environ.setdefault("DUO_QUIET", "1")

import webview

import duo_hub


def _state_available(url: str) -> bool:
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
    try:
        with opener.open(f"{url}/api/state", timeout=1.5) as response:
            payload = json.loads(response.read().decode("utf-8"))
        return bool(payload.get("version") and isinstance(payload.get("agents"), list))
    except Exception:
        return False


class LocalDuoHubServer:
    def __init__(self) -> None:
        self.url = f"http://{duo_hub.HOST}:{duo_hub.PORT}"
        self.server = None
        self.thread = None
        self.owned = False

    def start(self) -> None:
        if _state_available(self.url):
            return
        self.server = duo_hub.http.server.ThreadingHTTPServer(
            (duo_hub.HOST, duo_hub.PORT),
            duo_hub.DuoHubHandler,
        )
        self.server.daemon_threads = True
        self.thread = threading.Thread(
            target=self.server.serve_forever,
            name="duo-hub-http",
            daemon=True,
        )
        self.thread.start()
        self.owned = True
        deadline = time.time() + 10
        while time.time() < deadline:
            if _state_available(self.url):
                return
            time.sleep(0.1)
        self.stop()
        raise RuntimeError("Duo Hub local service did not become ready within 10 seconds")

    def stop(self) -> None:
        if not self.owned or self.server is None:
            return
        duo_hub.hub.shutdown_active_runs()
        self.server.shutdown()
        self.server.server_close()
        if self.thread is not None:
            self.thread.join(timeout=5)
        self.owned = False


def main() -> int:
    local_server = LocalDuoHubServer()
    try:
        local_server.start()
        webview.create_window(
            "Duo Hub",
            local_server.url,
            width=1320,
            height=880,
            min_size=(960, 640),
            background_color="#0f1117",
            text_select=True,
        )
        webview.start(gui="edgechromium", debug=False, private_mode=True)
        return 0
    finally:
        local_server.stop()

