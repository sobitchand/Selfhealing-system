import sys
import os
from http.server import HTTPServer, BaseHTTPRequestHandler
import random

# Ensure local selfhealing package is available on the import path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
from selfhealing.metrics_monitor import monitor

class InstrumentedTargetAppHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass # Suppress standard console logs to keep terminal clear

    def do_GET(self):
        # Route 1: Normal working path
        if self.path == "/" or self.path == "":
            with monitor.track_request(path="/", method="GET") as status:
                self.send_response(200)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                
                status["status_code"] = 200
                html = """
                <html>
                    <head>
                        <title>Pomodoro 3D Focus Timer</title>
                        <style>
                          * { box-sizing: border-box; }
                          body { margin: 0; font-family: 'Segoe UI', system-ui, sans-serif;
                                 background: radial-gradient(circle at 30% 10%, #1f2937, #0b1020 70%);
                                 color: #e5e7eb; min-height: 100vh; }
                          .app { max-width: 760px; margin: 0 auto; padding: 28px 20px 60px;
                                 display: grid; grid-template-columns: 1fr 250px; gap: 24px; }
                          header { grid-column: 1 / -1; text-align: center; }
                          h1 { font-weight: 700; letter-spacing: .5px; margin: 4px 0 16px; }
                          .modes { display: flex; gap: 10px; justify-content: center; }
                          .modes button { background: #1e293b; color: #cbd5e1; border: 1px solid #334155;
                                 padding: 8px 16px; border-radius: 999px; cursor: pointer; font-size: 14px; }
                          .modes button.active { background: #6366f1; color: #fff; border-color: #6366f1; }
                          .timer { text-align: center; }
                          .time-big { font-size: 96px; font-weight: 800; font-variant-numeric: tabular-nums;
                                 margin: 10px 0 18px; text-shadow: 0 0 30px rgba(99,102,241,.5); }
                          .controls { display: flex; gap: 12px; justify-content: center; }
                          .controls button { padding: 12px 22px; border-radius: 12px; border: 1px solid #334155;
                                 background: #1e293b; color: #e5e7eb; cursor: pointer; font-size: 15px; }
                          .btn-main { background: #22c55e !important; color: #06210f !important;
                                 border-color: #22c55e !important; font-weight: 700; min-width: 120px; }
                          aside { background: rgba(255,255,255,.03); border: 1px solid #1f2937;
                                 border-radius: 16px; padding: 16px; height: fit-content; }
                          .dur-row { display: flex; align-items: center; gap: 8px; margin: 8px 0; }
                          .dur-btn { width: 28px; height: 28px; border-radius: 8px; border: 1px solid #334155;
                                 background: #1e293b; color: #e5e7eb; cursor: pointer; font-size: 16px; line-height: 1; }
                          .duration-val { min-width: 28px; text-align: center; font-weight: 700; }
                          .dur-label { color: #94a3b8; font-size: 13px; }
                          .stats { margin-top: 16px; text-align: center; }
                          .stat-val { font-size: 40px; font-weight: 800; }
                          .accent { color: #f59e0b; }
                          .log { margin-top: 16px; font-size: 13px; }
                          .session-log { margin-top: 6px; color: #94a3b8; max-height: 140px; overflow-y: auto; }
                          img { display: block; margin: 18px auto 0; opacity: .9; }
                          a { color: #f87171; }
                        </style>
                        <script>
                          // Browser self-healing agent configuration
                          window.SELF_HEALING_CONFIG = {
                            appName: "Pomodoro 3D Focus Timer",
                            collectorUrl: "http://127.0.0.1:8766/selfhealing/events",
                            fallbackImage: "https://placehold.co/600x400?text=Asset+Unavailable",
                            watchSelectors: [
                              {
                                name: "Start",
                                selector: "#old-start",              // deliberately broken locator
                                fallbackSelector: "button",
                                fingerprint: { text: "START", className: "btn btn-main" }
                              }
                            ]
                          };
                        </script>
                    </head>
                    <body>
                        <div class="app">
                            <header>
                                <h1>Pomodoro 3D Focus Timer</h1>
                                <div class="modes">
                                    <button id="btn-focus" class="active">Focus</button>
                                    <button id="btn-short">Short Break</button>
                                    <button id="btn-long">Long Break</button>
                                </div>
                            </header>

                            <div class="timer">
                                <div id="time-display" class="time-big">25:00</div>
                                <div class="controls">
                                    <button id="start-btn" class="btn btn-main">START</button>
                                    <button id="reset-btn">Reset</button>
                                    <button id="skip-btn">Skip</button>
                                </div>
                                <!-- Intentionally broken image to demo resource_failure healing -->
                                <img src="/missing-asset.png" alt="badge" width="120">
                                <p><a href="/error">Force System Error Trace (500)</a></p>
                            </div>

                            <aside>
                                <div class="durations">
                                    <div class="dur-row"><button class="dur-btn" data-d="focus" data-s="-1">-</button>
                                        <span id="dur-focus" class="duration-val">25</span>
                                        <button class="dur-btn" data-d="focus" data-s="1">+</button>
                                        <span class="dur-label">Focus min</span></div>
                                    <div class="dur-row"><button class="dur-btn" data-d="short" data-s="-1">-</button>
                                        <span id="dur-short" class="duration-val">5</span>
                                        <button class="dur-btn" data-d="short" data-s="1">+</button>
                                        <span class="dur-label">Short min</span></div>
                                    <div class="dur-row"><button class="dur-btn" data-d="long" data-s="-1">-</button>
                                        <span id="dur-long" class="duration-val">20</span>
                                        <button class="dur-btn" data-d="long" data-s="1">+</button>
                                        <span class="dur-label">Long min</span></div>
                                </div>
                                <div class="stats">
                                    <div>Pomodoros</div>
                                    <div id="stat-pomodoros" class="stat-val accent">0</div>
                                </div>
                                <div class="log">
                                    <div>Session Log</div>
                                    <div id="session-log" class="session-log">No sessions yet - start focusing!</div>
                                </div>
                            </aside>
                        </div>

                        <script>
                          // Real ticking Pomodoro timer (vanilla JS, no deps)
                          (function () {
                            const $ = function (id) { return document.getElementById(id); };
                            const durEls = { focus: $('dur-focus'), short: $('dur-short'), long: $('dur-long') };
                            const modeBtns = { focus: $('btn-focus'), short: $('btn-short'), long: $('btn-long') };
                            const labels = { focus: 'Focus', short: 'Short Break', long: 'Long Break' };
                            let mode = 'focus';
                            let remaining = parseInt(durEls.focus.textContent, 10) * 60;
                            let timer = null;
                            let pomodoros = 0;

                            function dur(m) { return parseInt(durEls[m].textContent, 10) * 60; }
                            function fmt(s) {
                              const m = Math.floor(s / 60), ss = s % 60;
                              return String(m).padStart(2, '0') + ':' + String(ss).padStart(2, '0');
                            }
                            function render() { $('time-display').textContent = fmt(remaining); }
                            function stop() { if (timer) { clearInterval(timer); timer = null; } $('start-btn').textContent = 'START'; }
                            function setMode(m) {
                              stop(); mode = m; remaining = dur(m);
                              Object.values(modeBtns).forEach(function (b) { b.classList.remove('active'); });
                              modeBtns[m].classList.add('active'); render();
                            }
                            function log(msg) {
                              const el = $('session-log');
                              if (el.textContent.indexOf('No sessions') === 0) el.textContent = '';
                              const line = document.createElement('div');
                              const t = new Date().toLocaleTimeString();
                              line.textContent = '• ' + t + ' — ' + msg;
                              el.appendChild(line); el.scrollTop = el.scrollHeight;
                            }
                            function complete() {
                              stop();
                              if (mode === 'focus') {
                                pomodoros++; $('stat-pomodoros').textContent = String(pomodoros);
                                log('Focus session complete (' + durEls.focus.textContent + 'm)');
                                setMode('short');
                              } else { log(labels[mode] + ' complete'); setMode('focus'); }
                            }
                            function tick() { remaining--; render(); if (remaining <= 0) complete(); }
                            function start() {
                              if (timer) { stop(); return; }            // toggle -> pause
                              if (remaining <= 0) remaining = dur(mode);
                              $('start-btn').textContent = 'PAUSE';
                              timer = setInterval(tick, 1000);
                            }

                            $('start-btn').addEventListener('click', start);
                            $('reset-btn').addEventListener('click', function () { stop(); remaining = dur(mode); render(); log('Reset ' + labels[mode]); });
                            $('skip-btn').addEventListener('click', function () {
                              if (mode === 'focus') { pomodoros++; $('stat-pomodoros').textContent = String(pomodoros); }
                              log('Skipped ' + labels[mode]); setMode(mode === 'focus' ? 'short' : 'focus');
                            });
                            modeBtns.focus.addEventListener('click', function () { setMode('focus'); });
                            modeBtns.short.addEventListener('click', function () { setMode('short'); });
                            modeBtns.long.addEventListener('click', function () { setMode('long'); });

                            document.querySelectorAll('.dur-btn').forEach(function (btn) {
                              btn.addEventListener('click', function () {
                                const m = btn.dataset.d, step = parseInt(btn.dataset.s, 10);
                                let v = parseInt(durEls[m].textContent, 10) + step;
                                if (v < 1) v = 1; if (v > 90) v = 90;
                                durEls[m].textContent = String(v);
                                if (m === mode && !timer) { remaining = v * 60; render(); }
                              });
                            });

                            render();
                          })();
                        </script>
                        <script src="/selfhealing_agent.js"></script>
                    </body>
                </html>
                """
                self.wfile.write(bytes(html, "utf-8"))

        # Route: serve the browser self-healing agent verbatim from disk
        elif self.path == "/selfhealing_agent.js":
            agent_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "selfhealing_agent.js")
            try:
                with open(agent_path, "r", encoding="utf-8") as f:
                    agent_js = f.read()
                self.send_response(200)
                self.send_header("Content-type", "application/javascript")
                self.end_headers()
                self.wfile.write(bytes(agent_js, "utf-8"))
            except FileNotFoundError:
                self.send_response(404)
                self.end_headers()
                
        # Route 2: Fault injection route (generates error metrics)
        elif self.path == "/error":
            with monitor.track_request(path="/error", method="GET") as status:
                self.send_response(500)
                self.send_header("Content-type", "text/html")
                self.end_headers()
                
                status["status_code"] = 500
                html = "<html><body><h1>HTTP 500: Internal Server Stress Anomaly</h1></body></html>"
                self.wfile.write(bytes(html, "utf-8"))
                
        else:
            self.send_response(404)
            self.end_headers()

def run_server():
    server_address = ("127.0.0.1", 8000)
    httpd = HTTPServer(server_address, InstrumentedTargetAppHandler)
    print("🌍 Mock Target Web Application live at http://127.0.0.1:8000")
    print("👉 Visit http://127.0.0.1:8000/error a few times to simulate server stress.")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping Target Server Application...")
        httpd.server_close()

if __name__ == "__main__":
    run_server()