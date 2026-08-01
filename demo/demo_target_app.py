"""
Demo target application — serves the NovaBank example app.

    python demo_target_app.py [port]

Serves examples/bank/index_v1.html (the ORIGINAL page) at /, and
examples/bank/index.html (the REFACTORED page, where the front-end team renamed
ids, classes and link text) when ?break=refactor is present.

The healing system learns golden fingerprints from the original version; the
refactored version then breaks every locator the test depends on, which is the
failure the framework exists to absorb.
"""

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
APP_DIR = os.path.join(BASE_DIR, "examples", "bank")
DEFAULT_PORT = int(os.environ.get("TARGET_APP_PORT", "8000"))

CLEAN_PAGE = "index_v1.html"
BROKEN_PAGE = "index.html"


class DemoHandler(SimpleHTTPRequestHandler):
    """Serve the original or refactored NovaBank page based on ?break=refactor."""

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            break_mode = "refactor" in self.path
            filename = BROKEN_PAGE if break_mode else CLEAN_PAGE
            filepath = os.path.join(APP_DIR, filename)
            if os.path.exists(filepath):
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                with open(filepath, "rb") as f:
                    self.wfile.write(f.read())
            else:
                self.send_error(404, f"{filename} not found")
        else:
            super().do_GET()

    def log_message(self, format, *args):
        pass  # suppress request logging


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    os.chdir(APP_DIR)
    server = HTTPServer(("127.0.0.1", port), DemoHandler)
    print(f"Demo target app (NovaBank) running on http://127.0.0.1:{port}")
    print(f"  Original:   http://127.0.0.1:{port}/")
    print(f"  Refactored: http://127.0.0.1:{port}/?break=refactor")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
