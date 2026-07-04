    """
Capture real PNG screenshots (headless Chrome) of the running stack:
  - the Pomodoro target app page (the Application-Under-Test)
  - each of the 4 dashboard tabs (UI Heuristic / Locator Self-Correction /
    Infrastructure / Alerts)

Prereqs: target app on :8000 and dashboard on :8501 already running.
Run the dashboard with DASH_NO_REFRESH=1 so tabs don't auto-reset mid-capture.
"""
import os
import sys
import time

for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8")
    except Exception:
        pass

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By
from webdriver_manager.chrome import ChromeDriverManager

SHOTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshots")
os.makedirs(SHOTS, exist_ok=True)

TARGET_URL = os.environ.get("QA_TARGET_URL", "http://127.0.0.1:8000")
DASH_URL = os.environ.get("QA_DASH_URL", "http://localhost:8501")


def driver():
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless=new")
    opts.add_argument("--no-sandbox")
    opts.add_argument("--disable-dev-shm-usage")
    opts.add_argument("--window-size=1600,1500")
    return webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=opts)


def shot(d, name):
    path = os.path.join(SHOTS, name)
    d.save_screenshot(path)
    print(f"📸 {name}  ({os.path.getsize(path)} bytes)")


def main():
    d = driver()
    try:
        # 1. Target app page first (the website the system protects)
        d.get(TARGET_URL)
        time.sleep(1.5)
        shot(d, "01_target_app_pomodoro.png")

        # 2. Dashboard tabs (run dashboard with DASH_NO_REFRESH=1 so tabs hold)
        d.get(DASH_URL)
        time.sleep(11)  # let streamlit + plotly chart render fully
        shot(d, "02_dashboard_ui_healing.png")

        tabs = d.find_elements(By.CSS_SELECTOR, 'button[role="tab"]')
        names = [
            None,  # tab 0 already captured above
            "03_dashboard_locator_self_correction.png",
            "04_dashboard_infrastructure.png",
            "05_dashboard_alerts.png",
        ]
        for idx in (1, 2, 3):
            if idx < len(tabs):
                tabs[idx].click()
                time.sleep(1.5)
                shot(d, names[idx])
            else:
                print(f"⚠️ tab index {idx} not found (only {len(tabs)} tabs)")
    finally:
        d.quit()


if __name__ == "__main__":
    main()
