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
from http.server import HTTPServer, SimpleHTTPRequestHandler
import argparse
import time

# Color settings
GREEN = '\033[92m'
PINK = '\033[95m'
RESET = '\033[0m'
CYRILLIC = '\033[96m'
RED = '\033[91m'

# Configure logging
logging.basicConfig(level=logging.INFO, format=' %(message)s')

def print_banner():
    """Print the ASCII banner."""
    print(f"""
{GREEN}
$$\\                                    $$\\   $$\\                     
$$ |                                   $$ |  $$ |                    
$$ |      {PINK}$$$$$$$\\  $$$$$$$$\\ $$\\   $$\\ \\$$\\ $$  | $$$$$$$\\  $$$$$$$\\ {RESET}
$$ |      \\____$$\\ \\____$$  |$$ |  $$ | \\$$$$  / $$  _____|$$  _____|
$$ |      {PINK}$$$$$$$$ |  $$$$ _/ $$ |  $$ | $$  $$<  \\$$$$$$\\  \\$$$$$$\\ {RESET}
$$ |     $$  __$$ | $$  _/   $$ |  $$ |$$  /\\$$\\  \\____$$\\  \\____$$\\ 
$$$$$$$$\\ {PINK}$$$$$$$ |$$$$$$$$\\ \\$$$$$$$ |$$ /  $$ |$$$$$$$  |$$$$$$$  |{RESET}
\\________|\\_______|\\________| \\____$$ |\\__|  \\__|\\_______/ \\_______/ 
                             $$\\   $$ |                              
                             \\$$$$$$  |                              
                              \\______/                               
{RESET}
""")

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

def log_vulnerability(url, payload, is_vuln):
    """Log the URL and payload with appropriate color based on vulnerability status."""
    if is_vuln:
        logging.info(f"{GREEN}[info] URL: {url} [payload: {payload}] [VULN]{RESET}")
    else:
        logging.info(f"{RED}[info] URL: {url} [payload: {payload}] [NOT VULN]{RESET}")

def test_url_payload(url, payload, proxies=None, encode_times=0, timeout=10):
    """Test a single URL with a single payload."""
    session = create_session()  # Use the session with retry
    encoded_payload = encode_payload(payload, encode_times)
    
    for test_payload in [payload, encoded_payload]:
        try:
            # Check if the URL is valid
            parsed_url = urllib.parse.urlparse(url)
            if not all([parsed_url.scheme, parsed_url.netloc]):
                logging.error(f"{RED}[error] Invalid URL: {url}{RESET}")
                continue
            
            # Construct the test URL with payload
            if '?' in parsed_url.query:
                test_url = f"{url}{test_payload}"
            else:
                test_url = f"{url}{test_payload}"

            # Ensure that the URL is valid
            parsed_test_url = urllib.parse.urlparse(test_url)
            if not all([parsed_test_url.scheme, parsed_test_url.netloc]):
                logging.error(f"{RED}[error] Invalid URL with payload: {test_url}{RESET}")
                continue

            proxies_dict = {"http": proxies, "https": proxies} if proxies else None
            response = session.get(test_url, proxies=proxies_dict, timeout=timeout)  # Added timeout
            status_code = response.status_code

            # Check for XSS prompt or alert
            is_vuln, alert_text = check_xss_with_selenium(url, f"?payload={test_payload}", timeout)
            log_vulnerability(test_url, test_payload, is_vuln)

        except requests.RequestException as e:
            logging.error(f"{RED}[error] Request failed: {e}{RESET}")

def worker(url, payloads, proxies=None, encode_times=0, timeout=10):
    """Thread worker function to test multiple payloads against a URL."""
    for i, payload in enumerate(payloads):
        test_url_payload(url, payload, proxies, encode_times, timeout)
        logging.info(f"{CYRILLIC}[info] Payload {i + 1}/{len(payloads)} tested for URL {url}.{RESET}")
        time.sleep(1)  # Add a delay to avoid overwhelming the server

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
    parser.add_argument('-t', '--threads', type=int, default=5, help="Specify the number of threads to use (default: 5).")
    parser.add_argument('-e', '--encoding', type=int, default=0, help="Specify the number of times to encode payloads (default: 0).")
    parser.add_argument('-o', '--output', type=str, default='result.txt', help="Specify a custom file name for output results (default: result.txt).")
    parser.add_argument('-T', '--time-sec', type=int, default=10, help="Specify connection timeout in seconds (default: 10).")
    
    args = parser.parse_args()

    # Validate input
    if not args.url and not args.file:
        logging.error(f"{RED}You must specify either a single URL with -u or a file with URLs using -f.{RESET}")
        sys.exit(1)
    
    urls = []
    if args.url:
        urls.append(args.url)
    if args.file:
        urls = load_file(args.file)
        if urls is None:
            sys.exit(1)

    if not urls:
        logging.error(f"{RED}No URLs loaded. Exiting.{RESET}")
        sys.exit(1)

    payloads_file = 'payloads.txt'
    payloads = load_file(payloads_file)
    if payloads is None:
        sys.exit(1)

    print_banner()
    logging.info(f"{CYRILLIC}[info] Loaded {len(urls)} URLs and {len(payloads)} payloads.{RESET}")
    
    port = find_free_port()
    
    # Start the server in a separate thread
    server_thread = concurrent.futures.ThreadPoolExecutor(max_workers=1).submit(start_server, port)

    logging.info(f"{CYRILLIC}[info] Server started on port {port}.{RESET}")

    try:
        test_xss(urls, payloads, encode_times=args.encoding, num_threads=args.threads, timeout=args.time_sec)
    finally:
        server_thread.shutdown(wait=False)
        logging.info(f"{CYRILLIC}[info] Server shutting down.{RESET}")

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print(f"\n{RESET}{CYRILLIC}[info] Interrupted by user. Exiting...{RESET}")
        sys.exit(0)
