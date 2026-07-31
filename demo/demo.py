"""
One-command demo runner for the comprehensive TaskFlow app.

    python demo.py [--headed] [--dashboard] [--break MODE]

Starts the target app, runs the test suite against the clean version to learn
fingerprints, then runs against the broken version to demonstrate healing.

Flags:
  --headed      Run Chrome visibly
  --dashboard   Launch Streamlit dashboard alongside
  --break MODE  Fault to inject: refactor (default), css, id, attr, all
"""

import os
import sys
import time
import subprocess
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, BASE_DIR)

import config
import selfheal
import automation_wrapper
import learning_mode
from fingerprint_manager import FingerprintManager

PORT = int(os.environ.get("TARGET_APP_PORT", "8000"))
FINGERPRINT_PATH = os.path.join(config.DATA_DIR, "fingerprints", "web_demo_fingerprints.json")
TEST_SCRIPT = os.path.join(BASE_DIR, "test_comprehensive.py")


def find_chromedriver():
    import glob
    paths = glob.glob(os.path.expanduser(
        "~/.wdm/drivers/chromedriver/*/*/chromedriver-win64/chromedriver.exe"
    ))
    if paths:
        return paths[-1]
    from webdriver_manager.chrome import ChromeDriverManager
    return ChromeDriverManager().install()


def start_target_app():
    app_script = os.path.join(BASE_DIR, "demo_target_app.py")
    proc = subprocess.Popen(
        [sys.executable, app_script, str(PORT)],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    # Wait for app to be ready
    for _ in range(20):
        time.sleep(0.5)
        try:
            import urllib.request
            req = urllib.request.urlopen(f"http://127.0.0.1:{PORT}/", timeout=2)
            if req.status == 200:
                return proc
        except Exception:
            pass
    print("Warning: Target app may not be ready yet")
    return proc


def start_dashboard():
    dash_script = os.path.join(BASE_DIR, "dashboard.py")
    proc = subprocess.Popen(
        [sys.executable, "-m", "streamlit", "run", dash_script,
         "--server.port", "8501", "--server.headless", "true"],
        cwd=BASE_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    time.sleep(3)
    print("Dashboard running at http://localhost:8501")
    return proc


def make_driver(headless=True):
    from selenium import webdriver
    from selenium.webdriver.chrome.service import Service
    options = webdriver.ChromeOptions()
    if headless:
        options.add_argument("--headless=new")
    options.add_argument("--no-sandbox")
    options.add_argument("--disable-dev-shm-usage")
    driver_path = find_chromedriver()
    return webdriver.Chrome(service=Service(driver_path), options=options)


def main():
    headed = "--headed" in sys.argv
    with_dashboard = "--dashboard" in sys.argv
    headless = not headed

    # Configure system
    config.ACTIVE_FINGERPRINT_PATH = FINGERPRINT_PATH
    config.POMODORO_FINGERPRINTS_PATH = FINGERPRINT_PATH
    config.SOURCE_HEAL_ENABLED = True
    config.SOURCE_HEAL_TARGETS = [TEST_SCRIPT]

    print("=" * 60)
    print("SELF-HEALING SYSTEM DEMO")
    print("=" * 60)

    # Start target app
    print("\n[1/5] Starting target application...")
    app_proc = start_target_app()
    print(f"  Target app running on port {PORT}")

    dash_proc = None
    if with_dashboard:
        print("\n[2/5] Starting dashboard...")
        dash_proc = start_dashboard()

    driver = make_driver(headless=headless)

    try:
        # Phase 1: Learn from clean version
        print(f"\n[{('2' if with_dashboard else '1')}/5] Learning fingerprints from clean app...")
        clean_url = f"http://127.0.0.1:{PORT}/"
        driver.get(clean_url)
        time.sleep(2)

        with automation_wrapper.suppressed():
            manager = FingerprintManager(driver, fingerprint_path=FINGERPRINT_PATH)
            count = manager.scan_interactive()
        print(f"  Captured {count} golden fingerprints")

        # Phase 2: Run baseline test (should pass)
        print(f"\n[{('3' if with_dashboard else '2')}/5] Running baseline test (clean app)...")
        from test_comprehensive import run_tests
        passed1, failed1, total1 = run_tests(driver, url=clean_url)
        print(f"  Baseline: {passed1}/{total1} passed")

        # Phase 3: Run against broken version WITHOUT healing
        print(f"\n[{('4' if with_dashboard else '3')}/5] Running test against BROKEN app (no healing)...")
        selfheal.uninstall()
        broken_url = f"http://127.0.0.1:{PORT}/?break=refactor"
        passed2, failed2, total2 = run_tests(driver, url=broken_url)
        print(f"  Without healing: {passed2}/{total2} passed ({failed2} failures)")

        # Phase 4: Run against broken version WITH healing
        print(f"\n[{('5' if with_dashboard else '4')}/5] Running test against BROKEN app (with self-healing)...")
        selfheal.install(fingerprints=FINGERPRINT_PATH)
        passed3, failed3, total3 = run_tests(driver, url=broken_url)
        print(f"  With self-healing: {passed3}/{total3} passed")

        # Summary
        stats = selfheal.session_stats()
        heals = selfheal.session_heals()

        print(f"\n{'='*60}")
        print("DEMO SUMMARY")
        print(f"{'='*60}")
        print(f"  Baseline (clean app) ......... {passed1}/{total1} passed")
        print(f"  Without self-healing (broken)  {passed2}/{total2} passed")
        print(f"  With self-healing (broken) .... {passed3}/{total3} passed")
        print(f"  Tests recovered ............... {passed3 - passed2}")
        print(f"  Locator heals performed ....... {stats['heals']}")

        if heals:
            print(f"\n  Healed locators:")
            for h in heals:
                print(f"    {h['locator']} -> {h['resolved_to']} ({h['confidence']:.1f}%)")

        print(f"\n  Dashboard: http://localhost:8501")
        print(f"{'='*60}")

        if with_dashboard:
            print("\nDashboard is running. Press Ctrl+C to stop everything.")
            try:
                while True:
                    time.sleep(1)
            except KeyboardInterrupt:
                pass

    finally:
        selfheal.uninstall()
        driver.quit()
        app_proc.terminate()
        app_proc.wait()
        if dash_proc:
            dash_proc.terminate()
            dash_proc.wait()


if __name__ == "__main__":
    main()
