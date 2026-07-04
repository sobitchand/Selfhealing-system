import time
import json
import os
import threading
from contextlib import contextmanager
from datetime import datetime
import config
from healing_engine import DynamicInfrastructureHealer

# Global thread lock to prevent file-access collisions between scripts
file_write_lock = threading.Lock()

class MetricsMonitor:
    def __init__(self, history_path=config.METRICS_HISTORY_PATH):
        self.history_path = history_path
        self.app_name = "Default Application"
        self.traffic_rate = 0
        self.active_requests = 0
        self.error_count = 0
        self.total_requests = 0
        self.healer = DynamicInfrastructureHealer()
        
        # Start background health monitoring thread
        threading.Thread(target=self._analytics_loop, daemon=True).start()

    @contextmanager
    def track_request(self, path, method):
        """Context manager to intercept web traffic profiles dynamically."""
        self.active_requests += 1
        self.traffic_rate += 1
        self.total_requests += 1
        
        state = {"status_code": 200}
        try:
            yield state
        except Exception as e:
            state["status_code"] = 500
            raise e
        finally:
            self.active_requests = max(0, self.active_requests - 1)
            if state["status_code"] >= 500:
                self.error_count += 1

    def _analytics_loop(self):
        """Appends active telemetry intervals into historical logs."""
        while True:
            time.sleep(2)  # Update metrics slice every 2 seconds
            
            # Mock disk utilization percentage simulation 
            simulated_disk = round(50.0 + (time.time() % 45), 2)
            
            error_rate = 0.0
            if self.total_requests > 0:
                error_rate = round((self.error_count / self.total_requests) * 100, 2)
                
            service_health = "Up" if error_rate < 60.0 else "Down"
            http_status = 200 if service_health == "Up" else 500
            
            snapshot = {
                "timestamp": datetime.utcnow().isoformat() + "+00:00",
                "traffic_rate": self.traffic_rate,
                "active_requests": self.active_requests,
                "disk_usage_percent": simulated_disk,
                "service_health": service_health,
                "http_status": http_status,
                "error_rate_percent": error_rate
            }
            
            # Reset sliding-window counters so the next snapshot reflects only the
            # last interval. Without resetting error_count/total_requests they grow
            # monotonically: one burst of /error keeps error_rate pinned high
            # forever, so the infra healer would log a "fix" every 2s indefinitely
            # (dashboard spam). Sliding window => errors decay once traffic is clean.
            self.traffic_rate = 0
            self.error_count = 0
            self.total_requests = 0
            
            # Commit entry to telemetry file store
            self._write_snapshot(snapshot)
            
            # Run dynamic healing verification loop without hardcoded dependencies
            self.healer.analyze_and_heal_system()

    def _write_snapshot(self, snapshot):
        """Thread-safe atomic handler to write history metrics securely."""
        with file_write_lock:
            try:
                data = []
                
                # Check if file exists and contains parseable data
                if os.path.exists(self.history_path) and os.path.getsize(self.history_path) > 0:
                    try:
                        with open(self.history_path, "r") as f:
                            data = json.load(f)
                    except json.JSONDecodeError:
                        print("⚠️ Corrupted JSON found in metrics history. Re-initializing tracking array.")
                        data = []

                # Append the newly generated snapshot entry
                data.append(snapshot)
                
                # Keep historical logging clean (limit to last 100 entries)
                if len(data) > 100:
                    data = data[-100:]
                
                # Write to a temporary file first to avoid corruption if interrupted
                # mid-write. Tag the tmp name with the PID: multiple processes
                # (target app + collector) each run a monitor thread, and a shared
                # ".tmp" name would let them clobber each other's partial writes.
                temp_path = "{}.{}.tmp".format(self.history_path, os.getpid())
                os.makedirs(os.path.dirname(self.history_path), exist_ok=True)
                with open(temp_path, "w") as f:
                    json.dump(data, f, indent=2)

                # Atomically replace the old historical data file with the new one.
                # threading.Lock only guards threads in THIS process; other processes
                # writing the same file race us. On Windows os.replace raises
                # PermissionError (WinError 5) when the destination is briefly held
                # open by another process — retry with backoff instead of crashing.
                for attempt in range(5):
                    try:
                        os.replace(temp_path, self.history_path)
                        break
                    except PermissionError:
                        if attempt == 4:
                            raise
                        time.sleep(0.1)

            except Exception as e:
                print(f"❌ Critical error inside metrics snapshot writer: {str(e)}")
                # Don't leak the per-PID tmp file if the replace ultimately failed.
                try:
                    if os.path.exists(temp_path):
                        os.remove(temp_path)
                except Exception:
                    pass

# Instantiate the library global monitor object
monitor = MetricsMonitor()