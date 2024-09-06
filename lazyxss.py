import logging
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import time
import urllib.parse
import os

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# ANSI escape codes for color
GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[0m'

def print_banner():
    banner = f"""
{GREEN}
 /$$                                     /$$   /$$                   
| $$                                    | $$  / $$                   
| $$        /$$$$$$  /$$$$$$$$ /$$   /$$|  $$/ $$/  /$$$$$$$ /$$$$$$$
| $$       |____  $$|____ /$$/| $$  | $$ \  $$$$/  /$$_____//$$_____/
| $$        /$$$$$$$   /$$$$/ | $$  | $$  >$$  $$ |  $$$$$$|  $$$$$$ 
| $$       /$$__  $$  /$$__/  | $$  | $$ /$$/\  $$ \____  $$\____  $$
| $$$$$$$$|  $$$$$$$ /$$$$$$$$|  $$$$$$$| $$  \ $$ /$$$$$$$//$$$$$$$/
|________/ \_______/|________/ \____  $$|__/  |__/|_______/|_______/ 
                               /$$  | $$                             
                              |  $$$$$$/                             
                               \______/  v1.0
           XSS VULNERABILITY CHECKER BY IAMUNIXTZ                             
{RESET}
"""
    print(banner)

def load_payloads(file_path='payloads.txt'):
    """Load XSS payloads from a file."""
    if not os.path.isfile(file_path):
        logging.error(f"Payloads file '{file_path}' not found.")
        exit(1)
    with open(file_path, 'r') as file:
        return [line.strip() for line in file]

def encode_payload(payload, encode_times):
    """Encode payload with URL encoding up to the specified number of times."""
    encoded_payload = payload
    for _ in range(encode_times):
        encoded_payload = urllib.parse.quote(encoded_payload)
    return encoded_payload

def check_xss_with_selenium(url, payload, timeout=10):
    """Check for XSS vulnerability using Selenium."""
    chrome_options = Options()
    chrome_options.binary_location = "/usr/bin/google-chrome"  # Path to Chrome binary
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    # chrome_options.add_argument("--headless")  # Uncomment if you need headless mode

    service = Service('./chromedriver')  # Path to ChromeDriver
    driver = webdriver.Chrome(service=service, options=chrome_options)

    full_url = f"{url}{payload}"
    try:
        driver.get(full_url)
        driver.implicitly_wait(timeout)
        # Check for JavaScript alerts or prompts
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            alert.accept()  # Accept the alert
            return True, alert_text
        except Exception as e:
            return False, None
    finally:
        driver.quit()

def test_xss(url, payloads, use_proxies, proxies=None, delay=0, encode_times=0):
    """Test a list of XSS payloads against a URL."""
    total_payloads = len(payloads)
    xss_found = 0
    failed_requests = 0

    for payload in payloads:
        encoded_payload = encode_payload(payload, encode_times)
        payloads_to_test = [payload, encoded_payload]

        for test_payload in payloads_to_test:
            full_url = f"{url}?search={test_payload}"
            try:
                proxies_dict = {"http": proxies, "https": proxies} if use_proxies else None
                response = requests.get(full_url, proxies=proxies_dict)
                status_code = response.status_code

                # Check for XSS prompt or alert
                is_vuln, alert_text = check_xss_with_selenium(url, f"?search={test_payload}")
                if is_vuln:
                    print(f"{GREEN}[info] URL: {full_url} [payload: {test_payload}] [status: VULN]{RESET}")
                    xss_found += 1
                else:
                    print(f"{RED}[info] URL: {full_url} [payload: {test_payload}] [status: NOT VULN]{RESET}")

            except requests.RequestException as e:
                logging.error(f"Request failed: {e}")
                failed_requests += 1
            
            if delay > 0:
                time.sleep(delay)

    # Print summary report
    print(f"\n[info] Total payloads tested: {total_payloads}")
    print(f"{GREEN}[info] XSS found: {xss_found}{RESET}")
    print(f"[info] Failed requests: {failed_requests}")

def main():
    print_banner()
    
    url = input("Enter the URL to test (e.g., http://example.com/page): ").strip()
    encode_times = int(input("Enter the number of times to encode the payloads: ").strip())
    use_proxies = input("Do you want to use a proxy list? (y/n): ").strip().lower() == 'y'
    proxies = None
    if use_proxies:
        proxies = input("Enter proxy list (comma-separated, e.g., http://proxy1:port,http://proxy2:port): ").strip()
    delay = int(input("Enter delay between requests in seconds (0 for no delay): ").strip())

    print(f"[info] Target URL: {url}")

    payloads = load_payloads()
    test_xss(url, payloads, use_proxies, proxies, delay, encode_times)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{RESET}[info] Interrupted by user. Exiting...")
    except SystemExit:
        print(f"\n{RESET}[info] Exiting...")
    except Exception as e:
        print(f"\n{RED}[error] Unexpected error: {e}{RESET}")
