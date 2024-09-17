<p align="center">
  <a href="https://github.com/iamunixtz/LazyXss/issues"><img src="https://img.shields.io/github/issues/iamunixtz/LazyXss.svg" alt="GitHub issues"></a>
  <a href="https://github.com/iamunixtz/LazyXss/stargazers"><img src="https://img.shields.io/github/stars/iamunixtz/LazyXss.svg" alt="GitHub stars"></a>
  <a href="https://github.com/iamunixtz/LazyXss/blob/master/LICENSE"><img src="https://img.shields.io/github/license/iamunixtz/LazyXss.svg" alt="GitHub license"></a>
 <a href="https://t.me/bunnys3c"><img src="https://img.shields.io/badge/Join%20Us%20On-Telegram-2599d2.svg" alt="Telegram"></a>
  <img src="https://img.shields.io/badge/Made%20with-Python-1f425f.svg" alt="Made with Python">
</p>

<div align="center">

# LazyXss

</div>


LazyXss is an automation tool designed to test and confirm XSS (Cross-Site Scripting) vulnerabilities, specifically focusing on reflected XSS in URLs.

```
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
                               \______/

usage: lazyxssX5.py [-h] [-u URL] [-f FILE] [-t THREADS] [-e ENCODING] [-o OUTPUT] [-T TIME_SEC]

XSS Vulnerability Checker Tool

options:
  -h, --help            show this help message and exit
  -u URL, --url URL     Specify a single URL to test for XSS vulnerabilities.
  -f FILE, --file FILE  Specify a file containing a list of URLs to test.
  -t THREADS, --threads THREADS
                        Specify the number of threads to use (default: 5).
  -e ENCODING, --encoding ENCODING
                        Specify the number of times to encode payloads (default: 0).
  -o OUTPUT, --output OUTPUT
                        Specify a custom file name for output results (default: result.txt).
  -T TIME_SEC, --time-sec TIME_SEC
                        Specify connection timeout in seconds (default: 10).

```

## About LazyXss 📝

LazyXss automates the process of detecting reflected XSS vulnerabilities in URLs. This tool does not scan for DOM-based XSS or other types of vulnerabilities. It focuses exclusively on reflected XSS based on the provided URL. Thank you for using LazyXss!

![Lazy XSS](lazyxss.png)

## Features v1.1✨

- [x] **Automated Testing:** Quickly checks for reflected XSS vulnerabilities in URLs.
- [x] **Configurable Payloads:** Allows you to specify and encode payloads for testing.
- [x] **Proxy Support:** Optionally use proxies for testing to avoid detection and IP blocking.
- [x] **Logging:** Detailed logging of test results and server status.
- [x] **Multi-Platform Support:** Easy installation and setup on Windows, Debian-based, Fedora-based, and macOS systems.
- [x] **Handle urls on file**
- [x] **Improving the proxy and encoding the payloads**
- [x] **Increase Threads for testing multliples urls**
- [x] **Command line mode**

## Upcoming Features 🚀

- [ ] **GUI Mode:** A graphical user interface for easier configuration and use.
- [ ] **Advanced Reporting:** Detailed and customizable reports of test results.

## Setup LazyXss 🛠

Ensure you install the latest version of Google Chrome and the corresponding version of ChromeDriver for your device to avoid errors.

### Installation Instructions

#### Windows

1. **Clone the Repository**
   ```cmd
   git clone https://github.com/iamunixtz/LazyXss.git
   cd LazyXss
   ```

2. **Install Dependencies**
   ```cmd
   pip install -r requirements.txt
   ```

3. **Run the Installer**
   ```cmd
   python installer.py
   ```

4. **Start LazyXss**
   ```cmd
   python LazyXss.py -h
   ```

#### Debian-based Systems (e.g., Ubuntu)

1. **Update and Upgrade Packages**
   ```bash
   sudo apt update && sudo apt upgrade
   ```

2. **Install Dependencies**
   ```bash
   sudo apt install git python3-pip
   git clone https://github.com/iamunixtz/LazyXss.git
   cd LazyXss
   pip3 install -r requirements.txt
   ```

3. **Run the Installer**
   ```bash
   python3 installer.py
   ```

4. **Start LazyXss**
   ```bash
   python3 LazyXss.py -h 
   ```

#### Fedora-based Systems

1. **Update Packages**
   ```bash
   sudo dnf update
   ```

2. **Install Dependencies**
   ```bash
   sudo dnf install git python3-pip
   git clone https://github.com/iamunixtz/LazyXss.git
   cd LazyXss
   pip3 install -r requirements.txt
   ```

3. **Run the Installer**
   ```bash
   python3 installer.py
   ```

4. **Start LazyXss**
   ```bash
   python3 LazyXss.py
   ```

#### macOS

1. **Install Homebrew** (if not already installed)
   ```bash
   /bin/bash -c "$(curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh)"
   ```

2. **Install Dependencies**
   ```bash
   brew install git python
   git clone https://github.com/iamunixtz/LazyXss.git
   cd LazyXss
   pip3 install -r requirements.txt
   ```

3. **Run the Installer**
   ```bash
   python3 installer.py
   ```

4. **Start LazyXss**
   ```bash
   python3 LazyXss.py
   ```

## Contributions and Feedback 🤧

If you encounter any issues or have suggestions for improvements, please share them with us. Contributions are always welcome!

## Warning ⚠️

Running LazyXss may consume significant CPU resources. Ensure you are using a machine with adequate performance to avoid potential slowdowns or crashes. It is not recommended for use on low-specification systems.
