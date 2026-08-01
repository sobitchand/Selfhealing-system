"""
Demo target application — serves demo_page.html.

    python demo_target_app.py [port]

A simple HTTP server for the target application under test.
The healing system learns fingerprints from this page, then broken
locators trigger the self-healing engine.
"""

import os
import sys
from http.server import HTTPServer, SimpleHTTPRequestHandler

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_PORT = int(os.environ.get("TARGET_APP_PORT", "8000"))


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_PORT
    os.chdir(BASE_DIR)
    server = HTTPServer(("127.0.0.1", port), SimpleHTTPRequestHandler)
    print(f"Target application running on http://127.0.0.1:{port}")
    print(f"  Page: http://127.0.0.1:{port}/demo_page.html")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nShutting down.")
        server.server_close()


if __name__ == "__main__":
    main()
