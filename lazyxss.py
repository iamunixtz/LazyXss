import logging
import socket
import os
import sys
import urllib.parse
import concurrent.futures
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
import argparse
import time

# Color settings
GREEN = '\033[92m'   # Green color
RED = '\033[91m'     # Red color
YELLOW = '\033[93m'  # Yellow color
CYAN = '\033[96m'    # Cyan color
GREY = '\033[90m'    # Grey color
PURPLE = '\033[95m'  # Purple color
RESET = '\033[0m'    # Reset color (back to default)

# Configure logging format
logging.basicConfig(level=logging.INFO, format='%(message)s')

def print_banner():
    """Print the ASCII banner."""
    print(f"""
{GREEN}.____       _____  _______________.___. ____  ___  _________ _________
|    |     /  _  \\ \\____    /\\__  |   | \\   \\/  / /   _____//   _____/
|    |    /  /_\\  \\  /     /  /   |   |  \\     /  \\_____  \\ \\_____  \\ 
|    |___/    |    \\/     /_  \\____   |  /     \\  /        \\/        \\
|_______ \\____|__  /_______ \\ / ______| /___/\\  \\/_______  /_______  /
        \\/       \\/        \\/ \\/              \\_/        \\/        \\/ 1.2{RESET}
                                 {CYAN}https://github.com/iamunixtz/LazyXss{RESET}
                                 {YELLOW}An advanced Cross Site Scripting exploitation tool.{RESET}
""")

def find_free_port():
    """Find a free port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(('localhost', 0))
        port = s.getsockname()[1]
    return port

def load_file(file_path):
    """Load a file into a list."""
    if not os.path.isfile(file_path):
        logging.error(f"{RED}File '{file_path}' does not exist.{RESET}")
        return None
    with open(file_path, 'r') as file:
        return [line.strip() for line in file if line.strip()]

def encode_payload(payload, encode_times):
    """Encode payload with URL encoding up to the specified number of times."""
    encoded_payload = payload
    for _ in range(encode_times):
        encoded_payload = urllib.parse.quote(encoded_payload)
    return encoded_payload

def create_session():
    """Create a requests session with retry strategy."""
    session = requests.Session()
    retry = Retry(
        total=5,  # Total number of retries
        backoff_factor=1,  # Time to wait between retries
        status_forcelist=[500, 502, 503, 504]  # Retry on these status codes
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

def check_xss_with_selenium(url, payload, timeout=10):
    """Check for XSS vulnerability using Selenium."""
    chrome_options = Options()
    chrome_options.binary_location = "/usr/bin/google-chrome"  # Path to Chrome binary
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--headless")

    service = Service()  # Use default port 9515
    driver = webdriver.Chrome(service=service, options=chrome_options)
    try:
        full_url = f"{url}{payload}"
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

def log_vulnerability(url, payload, is_vuln, payload_number):
    """Log the URL and payload with appropriate color based on vulnerability status."""
    current_time = time.strftime("%H:%M:%S", time.localtime())  # Get current time
    time_str = f"[{CYAN}{current_time}{RESET}] "  # Cyan color for time

    # Create the full log message
    full_log = f"[payload {payload_number}] {url}"

    # If the URL is vulnerable, print in red
    if is_vuln:
        logging.info(f"{time_str}[{RED}VULN{RESET}] {RED}{full_log}{RESET}")  # Whole log in red
    else:
        logging.info(f"{time_str}[{GREEN}NOT VULN{RESET}] {GREEN}{full_log}{RESET}")  # Whole log in green

def test_url_payload(url, payload, payload_number, proxies=None, encode_times=0, timeout=10):
    """Test a single URL with a single payload."""
    session = create_session()  # Use the session with retry
    encoded_payload = encode_payload(payload, encode_times)
    
    # Avoid testing the same payload multiple times
    try:
        # Check if the URL is valid
        parsed_url = urllib.parse.urlparse(url)
        if not all([parsed_url.scheme, parsed_url.netloc]):
            logging.error(f"{RED}[error] Invalid URL: {url}{RESET}")
            return
        
        # Construct the test URL with payload
        if '?' in parsed_url.query:
            test_url = f"{url}{payload}"
        else:
            test_url = f"{url}{payload}"

        # Ensure that the URL is valid
        parsed_test_url = urllib.parse.urlparse(test_url)
        if not all([parsed_test_url.scheme, parsed_test_url.netloc]):
            logging.error(f"{RED}[error] Invalid URL with payload: {test_url}{RESET}")
            return

        proxies_dict = {"http": proxies, "https": proxies} if proxies else None
        response = session.get(test_url, proxies=proxies_dict, timeout=timeout)  # Added timeout

        # Check for XSS prompt or alert
        is_vuln, alert_text = check_xss_with_selenium(url, f"?payload={payload}", timeout)
        log_vulnerability(test_url, payload, is_vuln, payload_number)

    except requests.RequestException as e:
        logging.error(f"{RED}[error] Request failed: {e}{RESET}")

def worker(url, payloads, proxies=None, encode_times=0, timeout=10):
    """Thread worker function to test multiple payloads against a URL."""
    for i, payload in enumerate(payloads, start=1):
        test_url_payload(url, payload, i, proxies, encode_times, timeout)

def test_xss(urls, payloads, proxies=None, encode_times=0, num_threads=5, timeout=10):
    """Test XSS payloads against a list of URLs using multiple threads."""
    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [executor.submit(worker, url, payloads, proxies, encode_times, timeout) for url in urls]
        for future in concurrent.futures.as_completed(futures):
            future.result()  # to raise exceptions if any

def main():
    # Argument parser
    parser = argparse.ArgumentParser(
        description="XSS Vulnerability Checker Tool",
        formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument('-u', '--url', type=str, help="Specify a single URL to test for XSS vulnerabilities.")
    parser.add_argument('-f', '--file', type=str, help="Specify a file containing a list of URLs to test.")
    parser.add_argument('-p', '--payloads', type=str, default="payloads.txt", help="Specify a file with payloads to use (default: payloads.txt).")
    parser.add_argument('-t', '--threads', type=int, default=5, help="Specify the number of threads to use (default: 5).")
    parser.add_argument('-e', '--encoding', type=int, default=0, help="Specify the number of times to encode payloads (default: 0).")
    parser.add_argument('-o', '--output', type=str, default='result.txt', help="Specify a custom file name for output results (default: result.txt).")
    parser.add_argument('-T', '--time-sec', type=int, default=10, help="Specify connection timeout in seconds (default: 10).")
    
    args = parser.parse_args()

    # Load URL list
    if args.url:
        urls = [args.url]
    elif args.file:
        urls = load_file(args.file)
    else:
        print("You must provide either a URL or a file containing URLs.")
        sys.exit(1)

    # Load payloads from the specified file
    payloads = load_file(args.payloads)
    if not payloads:
        print(f"Error loading payloads from file: {args.payloads}")
        sys.exit(1)

    # Start testing for XSS vulnerabilities
    test_xss(urls, payloads, proxies=None, encode_times=args.encoding, num_threads=args.threads, timeout=args.time_sec)

if __name__ == "__main__":
    print_banner()
    main()
