import os
import sys
import urllib.request
import subprocess
import platform
import zipfile
import tarfile

# Define URLs for different platforms and architectures
CHROME_DRIVER_URLS = {
    'windows': {
        '64': 'https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_win32.zip',
        '32': 'https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_win32.zip'
    },
    'linux': {
        '64': 'https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux64.zip',
        '32': 'https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_linux32.zip'
    },
    'mac': {
        '64': 'https://chromedriver.storage.googleapis.com/114.0.5735.90/chromedriver_mac64.zip'
    }
}

def print_banner():
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

def download_file(url, dest):
    print(f"Downloading from {url}...")
    urllib.request.urlretrieve(url, dest)
    print("Download complete.")

def extract_file(file_path, extract_to):
    print(f"Extracting {file_path} to {extract_to}...")
    if file_path.endswith('.zip'):
        with zipfile.ZipFile(file_path, 'r') as zip_ref:
            zip_ref.extractall(extract_to)
    elif file_path.endswith('.tar.gz'):
        with tarfile.open(file_path, 'r:gz') as tar_ref:
            tar_ref.extractall(extract_to)
    print("Extraction complete.")

def install_chrome_driver(os_type, arch_type):
    if os_type == 'windows':
        dest_file = 'chromedriver_win32.zip'
        extract_dir = 'chromedriver'
    elif os_type in ['linux', 'mac']:
        dest_file = 'chromedriver_linux64.zip' if arch_type == '64' else 'chromedriver_linux32.zip'
        extract_dir = 'chromedriver'
    else:
        raise ValueError("Unsupported OS type.")

    url = CHROME_DRIVER_URLS[os_type][arch_type]
    download_file(url, dest_file)
    extract_file(dest_file, extract_dir)
    
    if os_type == 'windows':
        chromedriver_path = os.path.join(extract_dir, 'chromedriver.exe')
        # Move chromedriver to a location in PATH
        subprocess.call(['move', chromedriver_path, 'C:\\Windows\\System32'], shell=True)
    elif os_type in ['linux', 'mac']:
        chromedriver_path = os.path.join(extract_dir, 'chromedriver')
        # Move chromedriver to /usr/bin and make it executable
        subprocess.call(['sudo', 'mv', chromedriver_path, '/usr/bin/chromedriver'])
        subprocess.call(['sudo', 'chmod', '+x', '/usr/bin/chromedriver'])

def main():
    # ANSI escape sequences for colored output
    global GREEN, RESET
    GREEN = '\033[92m'
    RESET = '\033[0m'
    
    print_banner()

    os_type = input(f"{GREEN}[info] Choose Your Device:\n01> Windows\n02> Linux\n03> Mac\nInput: {RESET}").strip().lower()
    os_type_map = {'01': 'windows', '02': 'linux', '03': 'mac'}
    os_type = os_type_map.get(os_type, 'windows')

    arch_type = '64'  # Default to 64-bit
    if os_type in ['linux', 'windows']:
        arch_type = input(f"{GREEN}[info] Choose Architecture Type:\n01> 64-bit\n02> 32-bit\nInput: {RESET}").strip().lower()
        arch_type_map = {'01': '64', '02': '32'}
        arch_type = arch_type_map.get(arch_type, '64')

    install_chrome_driver(os_type, arch_type)
    print(f"{GREEN}[info] ChromeDriver installation and setup complete.{RESET}")

if __name__ == "__main__":
    main()
