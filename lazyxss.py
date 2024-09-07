import logging
import socket
from threading import Thread
from http.server import HTTPServer, SimpleHTTPRequestHandler
import requests
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import urllib.parse
import os
import sys
import time

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
GREEN = '\033[92m'
RED = '\033[91m'
RESET = '\033[0m'
CYRILLIC = '\033[96m'

def find_free_port():
    """Find a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('localhost', 0))
        port = s.getsockname()[1]
    return port

def start_server(port):
    """Start a simple HTTP server."""
    handler = SimpleHTTPRequestHandler
    httpd = HTTPServer(('localhost', port), handler)
    logging.info(f"{CYRILLIC}[info] Server started on port {port}.{RESET}")

    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()
        logging.info(f"{CYRILLIC}[info] Server shutting down.{RESET}")

def load_file(file_path):
    """Load a file into a list."""
    if not os.path.isfile(file_path):
        logging.error(f"{RED}File '{file_path}' does not exist.{RESET}")
        return None
    with open(file_path, 'r') as file:
        return [line.strip() for line in file]

def get_file_path(prompt):
    """Prompt user for a file path."""
    return input(f"{GREEN}{prompt}{RESET}").strip()

def get_proxies():
    """Prompt user for proxies."""
    proxies_input = input(f"{GREEN}Do you want to use a proxy? (y/n): {RESET}").strip().lower()
    if proxies_input == 'y':
        proxy_file = get_file_path(f"{GREEN}Enter proxy file path (default: proxy.txt): {RESET}") or 'proxy.txt'
        if not os.path.isfile(proxy_file):
            logging.error(f"{RED}Proxy file '{proxy_file}' does not exist.{RESET}")
            return None
        with open(proxy_file, 'r') as file:
            return [line.strip() for line in file]
    return None

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
    chrome_options.add_argument("--headless")

    service = Service()  # Use default port 9515
    driver = webdriver.Chrome(service=service, options=chrome_options)

    full_url = f"{url}{payload}"
    try:
        driver.get(full_url)
        driver.implicitly_wait(timeout)
        try:
            alert = driver.switch_to.alert
            alert_text = alert.text
            alert.accept()  # Accept the alert
            return True, alert_text
        except Exception:
            return False, None
    finally:
        driver.quit()

def test_xss(urls, payloads, proxies=None, encode_times=0, delay=0):
    """Test XSS payloads against a list of URLs."""
    total_payloads = len(payloads)
    for url in urls:
        logging.info(f"{CYRILLIC}[info] Testing URL: {url}{RESET}")
        for i, payload in enumerate(payloads):
            encoded_payload = encode_payload(payload, encode_times)
            for test_payload in [payload, encoded_payload]:
                full_url = f"{url}?search={test_payload}"
                try:
                    proxies_dict = {"http": proxies, "https": proxies} if proxies else None
                    response = requests.get(full_url, proxies=proxies_dict)
                    status_code = response.status_code

                    # Check for XSS prompt or alert
                    is_vuln, alert_text = check_xss_with_selenium(url, f"?search={test_payload}")
                    if is_vuln:
                        logging.info(f"{CYRILLIC}[info] URL: {full_url} [payload: {test_payload}] [status: VULN]{RESET}")
                    else:
                        logging.info(f"{CYRILLIC}[info] URL: {full_url} [payload: {test_payload}] [status: NOT VULN]{RESET}")

                except requests.RequestException as e:
                    logging.error(f"{RED}[error] Request failed: {e}{RESET}")

                if delay > 0:
                    time.sleep(delay)
                
                logging.info(f"{CYRILLIC}[info] Payload {i + 1}/{total_payloads} tested.{RESET}")

def main():
    print(f"""
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
""")
    
    urls_input = input(f"{GREEN}Do you want to test a single URL or a file of URLs? (single/file): {RESET}").strip().lower()
    if urls_input == 'single':
        urls = [input(f"{GREEN}Enter the single URL to test: {RESET}").strip()]
    elif urls_input == 'file':
        urls_file = get_file_path(f"{GREEN}Enter the file path for URLs: {RESET}")
        urls = load_file(urls_file)
        if urls is None:
            exit(1)
    else:
        logging.error(f"{RED}Invalid choice for URLs input.{RESET}")
        exit(1)
    
    payloads_file = get_file_path(f"{GREEN}Enter the file path for payloads (default: payloads.txt): {RESET}") or 'payloads.txt'
    payloads = load_file(payloads_file)
    if payloads is None:
        exit(1)
    
    encode_times = input(f"{GREEN}Enter the number of times to encode the payloads (or press Enter to skip encoding): {RESET}").strip()
    encode_times = int(encode_times) if encode_times.isdigit() else 0
    
    proxies = get_proxies()
    
    delay = input(f"{GREEN}Enter delay between requests in seconds (0 for no delay): {RESET}").strip()
    delay = int(delay) if delay.isdigit() else 0

    logging.info(f"{CYRILLIC}[info] Loaded {len(urls)} URLs and {len(payloads)} payloads.{RESET}")
    
    port = find_free_port()
    
    # Start the server in a separate thread
    server_thread = Thread(target=start_server, args=(port,), daemon=True)
    server_thread.start()

    logging.info(f"{CYRILLIC}[info] Server started on port {port}.{RESET}")

    test_xss(urls, payloads, proxies, encode_times, delay)

    # Wait for the server thread to finish
    server_thread.join()

    logging.info(f"{CYRILLIC}[info] Server shutting down.{RESET}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{RESET}{CYRILLIC}[info] Interrupted by user. Exiting...{RESET}")
        sys.exit(0)
                       
