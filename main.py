"""
Aurora Better Asset Manager - Main Application Launcher
Boots the FastAPI engine backend and opens the UI in a browser-first mode.
Native desktop PyWebView support can be enabled explicitly when the host GUI stack is available.
"""

import os
import sys
import subprocess
import threading
import time
import webbrowser
import argparse
import uvicorn
from fastapi.staticfiles import StaticFiles

def parse_args():
    parser = argparse.ArgumentParser(
        description="Aurora Better Asset Manager launcher."
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Run in demo mode: serve fake game library data and placeholder "
             "artwork so the UI can be tested without an Xbox console/FTP connection.",
    )
    # Ignore unknown args so this stays friendly when launched by other tooling.
    args, _ = parser.parse_known_args()
    return args

# Enable demo mode *before* importing the engine so the server picks it up.
_ARGS = parse_args()
if _ARGS.debug:
    os.environ["AURORA_DEMO_MODE"] = "1"
else:
    os.environ.pop("AURORA_DEMO_MODE", None)

if sys.platform.startswith("linux") and "DISPLAY" in os.environ and os.environ.get("GDK_BACKEND") is None:
    if os.environ.get("WAYLAND_DISPLAY"):
        os.environ["GDK_BACKEND"] = "wayland"
    else:
        os.environ["GDK_BACKEND"] = "x11"

from aurora_engine.server import app

ui_dir = os.path.join(os.path.dirname(__file__), "aurora_ui")
if os.path.exists(ui_dir):
    from fastapi.responses import FileResponse
    _index_path = os.path.join(ui_dir, "index.html")

    # SPA deep-link routes: serve index.html so client-side routing can resolve
    # URLs like /editor/123 on a hard refresh (registered before the static mount).
    @app.get("/library")
    @app.get("/coverage")
    @app.get("/search")
    @app.get("/console")
    @app.get("/editor")
    def _spa_page():
        return FileResponse(_index_path)

    @app.get("/editor/{title_id}")
    def _spa_editor(title_id: str):
        return FileResponse(_index_path)

    app.mount("/", StaticFiles(directory=ui_dir, html=True), name="ui")

def start_server():
    """Runs Uvicorn ASGI server on 127.0.0.1:8000."""
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

def main():
    print("=" * 60)
    print("      AURORA BETTER ASSET MANAGER - NEXT-GEN CROSS PLATFORM      ")
    print("=" * 60)
    if _ARGS.debug:
        print("  >> DEBUG / DEMO MODE: serving FAKE data (no Xbox connection) <<")
        print("=" * 60)

    server_thread = threading.Thread(target=start_server, daemon=True)
    server_thread.start()

    print("Booting Aurora Engine backend server at http://127.0.0.1:8000 ...")
    time.sleep(1.5)

    use_native_ui = os.environ.get("AURORA_USE_NATIVE_UI", "1").lower() in {"1", "true", "yes", "on"}
    app_url = "http://127.0.0.1:8000/"

    if not use_native_ui:
        print("Using browser-first launch mode. Set AURORA_USE_NATIVE_UI=1 to attempt the desktop window.")
        webbrowser.open(app_url)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down Aurora Better Asset Manager...")
        return

    try:
        import webview
        print("Launching PyWebView Desktop Interface...")

        launcher_code = """
import os
import sys
import webview

webview.create_window(
    title='Aurora Better Asset Manager',
    url='http://127.0.0.1:8000/',
    width=1280,
    height=850,
    min_size=(960, 640),
    background_color='#0b0f17'
)
webview.start(gui='gtk' if sys.platform.startswith('linux') else None)
"""

        native_env = os.environ.copy()
        native_env.setdefault("GDK_BACKEND", "wayland" if native_env.get("WAYLAND_DISPLAY") else "x11")
        native_proc = subprocess.Popen(
            [sys.executable, "-c", launcher_code],
            env=native_env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )

        time.sleep(1.5)
        if native_proc.poll() is not None:
            print("Native desktop launch failed. Falling back to browser mode.")
            webbrowser.open(app_url)
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                print("\nShutting down Aurora Better Asset Manager...")
            return

        print("Desktop window is running in a separate process.")
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down Aurora Better Asset Manager...")
            native_proc.terminate()
            try:
                native_proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                native_proc.kill()
    except BaseException as e:
        print(f"PyWebView not available or native window closed: {e}")
        print("Opening default browser interface at http://127.0.0.1:8000/ ...")
        webbrowser.open(app_url)

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            print("\nShutting down Aurora Better Asset Manager...")

if __name__ == "__main__":
    main()

