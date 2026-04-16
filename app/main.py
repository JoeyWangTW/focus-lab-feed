"""Entry point: starts uvicorn server with optional PyWebView native window."""

import argparse
import os
import socket
import sys
import time
from threading import Thread

import uvicorn

# Initialize paths and environment before anything else
from app.paths import DATA_DIR, IS_BUNDLED, STATIC_DIR, initialize

initialize()
# Workspace is created on explicit user setup (see app/api/workspace.py), not here.

DEFAULT_PORT = 8741


def find_open_port(start: int = DEFAULT_PORT) -> int:
    """Find an available port, starting from the given port."""
    for port in range(start, start + 100):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) != 0:
                return port
    raise RuntimeError("No available port found")


def wait_for_server(port: int, timeout: float = 10.0):
    """Wait until the server is accepting connections."""
    start = time.time()
    while time.time() - start < timeout:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(("127.0.0.1", port)) == 0:
                return
        time.sleep(0.1)
    raise TimeoutError(f"Server did not start within {timeout}s")


def run_uvicorn(port: int):
    # When bundled, we can't use string import path — import directly
    from app.server import create_app
    app = create_app()
    uvicorn.run(app, host="0.0.0.0", port=port, log_level="warning")


def main():
    parser = argparse.ArgumentParser(description="Focus Lab Feed Collector App")
    parser.add_argument("--port", type=int, default=DEFAULT_PORT, help="Server port")
    parser.add_argument("--no-gui", action="store_true", help="Run without PyWebView window")
    args = parser.parse_args()

    # In bundled mode, set working directory to DATA_DIR
    # so existing collectors' relative paths (feed_data/, session/) resolve correctly
    if IS_BUNDLED:
        os.chdir(str(DATA_DIR))

    port = find_open_port(args.port)
    url = f"http://localhost:{port}"

    # When bundled, always try GUI unless explicitly --no-gui
    use_gui = not args.no_gui

    if not use_gui:
        print(f"[app] Starting server at {url}")
        print(f"[app] Open {url} in your browser")
        run_uvicorn(port)
    else:
        server_thread = Thread(target=run_uvicorn, args=(port,), daemon=True)
        server_thread.start()
        wait_for_server(port)

        try:
            import webview

            class JsApi:
                """Exposed to the web frontend as `window.pywebview.api.*`.

                Adds capabilities that require native OS integration — e.g.,
                showing the macOS folder picker for the workspace setup flow.
                """

                def pick_folder(self, initial: str = "") -> str | None:
                    windows = webview.windows
                    if not windows:
                        return None
                    result = windows[0].create_file_dialog(
                        webview.FOLDER_DIALOG,
                        directory=initial or "",
                        allow_multiple=False,
                    )
                    if not result:
                        return None
                    # result is a tuple of paths; take the first
                    return result[0] if isinstance(result, (list, tuple)) else str(result)

            print(f"[app] Opening native window (server at {url})")
            webview.create_window("Focus Lab Feed", url, width=1200, height=800, js_api=JsApi())
            webview.start()
        except ImportError:
            print(f"[app] Starting server at {url}")
            if not IS_BUNDLED:
                print("[app] Install pywebview for native window: pip install pywebview")
            print(f"[app] Open {url} in your browser")
            try:
                server_thread.join()
            except KeyboardInterrupt:
                print("\n[app] Shutting down.")


if __name__ == "__main__":
    main()
