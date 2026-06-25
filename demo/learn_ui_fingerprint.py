import argparse
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.common.by import By
from fingerprint_manager import FingerprintManager
import config

def main():
    parser = argparse.ArgumentParser(description="Capture Golden Element Fingerprints from a working web state.")
    parser.add_argument("--url", required=True, help="Target application URL to scan.")
    parser.add_argument("--by", required=True, choices=["id", "css", "xpath", "link_text"], help="Selenium Locator Strategy")
    parser.add_argument("--value", required=True, help="Locator string value matching the target element")
    args = parser.parse_args()

    # Map strategies to standard Selenium By objects
    strategy_map = {
        "id": By.ID,
        "css": By.CSS_SELECTOR,
        "xpath": By.XPATH,
        "link_text": By.LINK_TEXT
    }
    selected_by = strategy_map[args.by]
    
    # Assign target data path
    f_path = config.POMODORO_FINGERPRINTS_PATH

    print(f"🌐 Launching browser runner context to scan: {args.url}")
    options = webdriver.ChromeOptions()
    options.add_argument("--headless")
    driver = webdriver.Chrome(service=Service(ChromeDriverManager().install()), options=options)

    try:
        driver.get(args.url)
        manager = FingerprintManager(driver, fingerprint_path=f_path)
        
        print(f"🔍 Locating target element using [{args.by}='{args.value}']...")
        manager.scan_elements([(selected_by, args.value)])
        print("💾 Golden Fingerprint successfully synchronized to configuration data store.")
    except Exception as e:
        print(f"❌ Operation Failed: {str(e)}")
    finally:
        driver.quit()

if __name__ == "__main__":
    main()