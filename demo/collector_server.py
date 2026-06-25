import json
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import sys

# Ensure local modules are resolvable when run as a script
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import config  # noqa: F401  (imported for UTF-8 stdout side effect + path setup)
from handlers import handle_passive_event

class CollectorBackendHandler(BaseHTTPRequestHandler):
    def _set_headers(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        # Enable Cross-Origin Resource Sharing (CORS) for front-end script connections
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.end_headers()

    def do_OPTIONS(self):
        """Handle CORS pre-flight handshake requests safely."""
        self._set_headers()

    def do_POST(self):
        if self.path == "/selfhealing/events":
            content_length = int(self.headers["Content-Length"])
            post_data = self.rfile.read(content_length)
            event_payload = json.loads(post_data.decode("utf-8"))

            print(f"📥 Received event from Browser Agent: {event_payload.get('type')}")
            handle_passive_event(event_payload)

            self._set_headers()
            self.wfile.write(bytes(json.dumps({"status": "acknowledged"}), "utf-8"))
        else:
            self.send_response(404)
            self.end_headers()

def run_collector():
    server_address = ("127.0.0.1", 8766)
    httpd = HTTPServer(server_address, CollectorBackendHandler)
    print("🛰️ Static Website Runtime Agent Collector running on http://127.0.0.1:8766")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Collector Server Instance...")
        httpd.server_close()

if __name__ == "__main__":
    run_collector()