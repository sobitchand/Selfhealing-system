"""
Demo target application — serves web_demo.html or web_demo_broken.html.

    python demo_target_app.py [port]

Query parameter ?break=refactor serves the broken version (renamed IDs/classes).
Without it, serves the clean version. The healing system learns from the clean
version, then the broken version causes all locators to fail.
"""

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = int(os.environ.get("TARGET_APP_PORT", "8000"))


class DemoHandler(SimpleHTTPRequestHandler):
    """Serve web_demo.html or web_demo_broken.html based on ?break=refactor."""

    def do_GET(self):
        if self.path == "/" or self.path.startswith("/?"):
            break_mode = "refactor" in self.path
            filename = "web_demo_broken.html" if break_mode else "web_demo.html"
            filepath = os.path.join(BASE_DIR, filename)
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
    os.chdir(BASE_DIR)
    server = HTTPServer(("127.0.0.1", port), DemoHandler)
    print(f"Demo target app running on http://127.0.0.1:{port}")
    print(f"  Clean:  http://127.0.0.1:{port}/")
    print(f"  Broken: http://127.0.0.1:{port}/?break=refactor")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
