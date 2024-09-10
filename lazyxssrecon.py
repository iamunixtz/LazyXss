import requests
from bs4 import BeautifulSoup
import re
import os
from colorama import Fore, Style, init

# Initialize colorama
init(autoreset=True)

# Define the banner
banner = """
.____                          ____  ___              __________                            
|    |   _____  ___________.__.\   \/  /  ______ _____\______   \ ____   ____  ____   ____  
|    |   \__  \ \___   <   |  | \     /  /  ___//  ___/|       _// __ \_/ ___\/  _ \ /    \ 
|    |___ / __ \_/    / \___  | /     \  \___ \ \___ \ |    |   \  ___/\  \__(  <_> )   |  \
|_______ (____  /_____ \/ ____|/___/\  \/____  >____  >|____|_  /\___  >\___  >____/|___|  /
        \/    \/      \/\/           \_/     \/     \/        \/     \/     \/           \/ 
"""

def print_banner():
    print(Fore.GREEN + banner)

def test_url(url):
    try:
        response = requests.get(url)
        response.raise_for_status()
        return response.text
    except requests.RequestException as e:
        print(f"{Fore.RED}[error] {url}: {str(e)}")
        return None

def test_param_reflection(url, param):
    modified_url = re.sub(r'(\?|&){}=.*?(&|$)'.format(re.escape(param)), r'\1{}=lazyxss&\2'.format(param), url)
    if '?' not in modified_url:
        modified_url += '?' + param + '=lazyxss'
    else:
        modified_url += '&' + param + '=lazyxss'
    
    original_content = test_url(url)
    if not original_content:
        return False
    
    modified_content = test_url(modified_url)
    if not modified_content:
        return False
    
    return param in modified_content

def check_url(url):
    reflecting_params = []
    non_reflecting_params = []

    print(f"{Fore.GREEN}[info] Testing URL: {url}")

    try:
        response = requests.get(url)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, 'html.parser')

        # Extract parameters from the URL
        params = re.findall(r'[?&]([^=]+)=', url)
        if not params:
            print(f"{Fore.YELLOW}[info] Skipping URL with no parameters: {url}")
            return []

        for param in params:
            if test_param_reflection(url, param):
                reflecting_params.append(param)
            else:
                non_reflecting_params.append(param)
        
        # Print logs
        for param in reflecting_params:
            print(f"{Fore.GREEN}[info] {url} [{param} reflecting]")
        for param in non_reflecting_params:
            print(f"{Fore.RED}[info] {url} [{param} not reflecting]")

        return reflecting_params

    except requests.RequestException as e:
        print(f"{Fore.RED}[error] {url}: {str(e)}")
        return []

def process_urls(file_or_url):
    if file_or_url.startswith('http'):
        urls = [file_or_url]
    else:
        if not os.path.isfile(file_or_url):
            print(f"{Fore.RED}[error] File not found: {file_or_url}")
            return

        with open(file_or_url, 'r') as f:
            urls = [line.strip() for line in f if line.strip()]

    total_tested = 0
    total_reflecting = 0
    reflecting_urls = []

    for url in urls:
        reflecting_params = check_url(url)
        if reflecting_params:
            reflecting_urls.append(url)
            total_reflecting += 1
        total_tested += 1

    # Save reflecting URLs to file
    with open('reflectparams.txt', 'w') as f:
        for url in reflecting_urls:
            f.write(url + '\n')

    # Print summary
    print(f"{Fore.GREEN}[summary] Total URLs tested: {total_tested}")
    print(f"{Fore.GREEN}[summary] Total reflecting URLs: {total_reflecting}")

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Test URL parameters for reflection.")
    parser.add_argument('input', type=str, help='URL or file containing URLs to test')
    args = parser.parse_args()

    print_banner()
