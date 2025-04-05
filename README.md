# LazyXSS - Advanced Reflected XSS Scanner

<div align="center">

[![GitHub stars](https://img.shields.io/github/stars/iamunixtz/LazyXss?style=social)](https://github.com/iamunixtz/LazyXss/stargazers)
[![GitHub forks](https://img.shields.io/github/forks/iamunixtz/LazyXss?style=social)](https://github.com/iamunixtz/LazyXss/network/members)
[![GitHub issues](https://img.shields.io/github/issues/iamunixtz/LazyXss)](https://github.com/iamunixtz/LazyXss/issues)
[![License](https://img.shields.io/github/license/iamunixtz/LazyXss)](https://github.com/iamunixtz/LazyXss/blob/main/LICENSE) <!-- Assuming you have a LICENSE file -->

</div>

LazyXSS is a powerful and efficient Python tool designed to automate the detection and confirmation of **reflected** Cross-Site Scripting (XSS) vulnerabilities in web applications. It meticulously tests **all GET parameters** found in provided URLs, supports scanning multiple targets from a file, and generates comprehensive, multi-page HTML reports with a modern UI.

<div align="center">

**LazyXSS in Action!**
![image](https://github.com/user-attachments/assets/772131f1-e761-4a7e-bb78-f7f03540e957)

</div>

## Key Features

*   **Comprehensive Parameter Testing:** Automatically identifies and tests *all* GET parameters within each URL.
*   **Reflected XSS Focus:** Detects vulnerabilities where payloads are reflected in the HTTP response.
*   **Selenium Confirmation:** Uses headless Chrome/Chromium via Selenium to confirm vulnerabilities by detecting JavaScript alert execution, reducing false positives.
*   **Multi-threaded Scanning:** Leverages threading for faster scanning of multiple URL variations.
*   **Configurable Concurrency:** Fine-tune performance with separate controls for overall threads (`-t`) and concurrent Selenium browser instances (`--selenium-workers`).
*   **Modern HTML Reporting:** Generates detailed, paginated HTML reports with a futuristic dashboard UI for confirmed vulnerabilities.
*   **Basic WAF Detection:** Attempts to identify common WAFs (Cloudflare, Akamai, Generic Blocks) that might interfere with scanning.
*   **Proxy Support:** Route HTTP requests (excluding Selenium) through an HTTP/HTTPS proxy.
*   **Payload Encoding:** Supports URL-encoding payloads multiple times (`-e`).
*   **Customizable Timeout:** Adjust the timeout for Selenium checks (`-T`).
*   **Explicit Chrome Path:** Specify the path to your Chrome/Chromium executable if automatic detection fails (`--chrome-path`).
*   **Save Report on Interrupt:** Attempts to save the current findings to the HTML report if the scan is interrupted (Ctrl+C) and vulnerabilities were found.
*   **Randomized User-Agents:** Uses common user agents randomly for HTTP requests.

## Video Tutorial

*Note: This video may show an older version of the tool.*
<div align="center">
  <a href="https://youtu.be/7d0vryZCf5k">
    <img src="https://img.youtube.com/vi/7d0vryZCf5k/0.jpg" alt="LazyXSS Video Tutorial"/>
  </a>
</div>

## Requirements

*   Python 3.x
*   pip (Python package installer)
*   **Google Chrome** or **Chromium** browser installed.

## Installation (Linux - Debian/Ubuntu Example)

1.  **Update System & Install Dependencies:**
    ```bash
    sudo apt update && sudo apt upgrade -y
    sudo apt install python3 python3-pip git wget -y
    ```
2.  **Install Google Chrome / Chromium:**
    *   **Chromium (Recommended for servers/headless):**
        ```bash
        sudo apt install chromium-browser -y
        ```
    *   **Google Chrome (Alternative):** Download the `.deb` package from Google and install it:
        ```bash
        wget https://dl.google.com/linux/direct/google-chrome-stable_current_amd64.deb
        sudo apt install ./google-chrome-stable_current_amd64.deb -y
        rm google-chrome-stable_current_amd64.deb
        ```
3.  **Clone the Repository:**
    ```bash
    git clone https://github.com/Iamunixtz/lazyXss.git
    cd lazyXss
    ```
4.  **Install Python Requirements:**
    ```bash
    pip3 install -r requirements.txt
    ```

## Installation (Windows)

1.  Install **Python 3.x** from [python.org](https://www.python.org/) (ensure "Add Python to PATH" is checked during installation).
2.  Install **Google Chrome**.
3.  Open Command Prompt or PowerShell.
4.  **Clone the Repository:**
    ```bash
    git clone https://github.com/Iamunixtz/lazyXss.git
    cd lazyXss
    ```
5.  **Install Python Requirements:**
    ```bash
    pip install -r requirements.txt
    ```
6.  **(Important):** If the script shows `Chrome Version: N/A`, you likely need to use the `--chrome-path` argument to specify the full path to your `chrome.exe` (see Usage).

## Usage

```text
usage: python3 lazyxssX53x.py [OPTIONS]

Example (URL): python3 lazyxssX53x.py -u "http://test.com?q=test&debug=0" -p payloads.txt
Example (File): python3 lazyxssX53x.py -f urls.txt -p payloads.txt -o results.txt

Options:
  -u, --url            Specify a single URL to test.
  -f, --file           Specify a file containing URLs (one per line).
  -p, --payloads       Specify the payload file (default: payloads.txt).
  -t, --threads        Number of concurrent URL processing threads (default: 20).
  -e, --encoding       Number of times to URL-encode the payloads (default: 0).
  -o, --output         Output file to write vulnerable URLs (default: result.txt).
                       The HTML report will be named based on this file (e.g., result_page_1.html).
  -T, --time-sec       Timeout in seconds for Selenium checks (default: 2).
  --chrome-path        Specify the full path to the chrome/chromium executable.
                       (Use if automatic detection fails)
  --selenium-workers   Number of concurrent Selenium browser instances (default: 5).
                       Increase cautiously based on system resources.
  --proxy              Specify a proxy server (e.g., http://user:pass@127.0.0.1:8080).
                       (Note: Affects HTTP requests, not Selenium checks).
  -h, --help           Show this help message and exit.

Description:
  High-speed XSS scanner with HTTP reflection and Selenium verification.
  Generates a futuristic HTML report (if vulnerabilities are found).
```

## Example Usage

### Scan a single URL (multiple parameters):

```bash
python3 lazyxssX53x.py -u "http://testphp.vulnweb.com/search.php?test=query&search=test" -p pay.txt -o vuln.txt
```
*(This will test parameters `test` and `search` separately, plus append to the end)*

### Scan multiple URLs from a file:

```bash
python3 lazyxssX53x.py -f urls.txt -p payloads.txt -o scan_results.txt
```

### Scan using a specific Chrome path (Windows Example):

```bash
python3 lazyxssX53x.py -u "http://example.com/page?id=1" --chrome-path "C:\Program Files\Google\Chrome\Application\chrome.exe"
```

### Scan using an HTTP Proxy:

```bash
python3 lazyxssX53x.py -f urls.txt --proxy http://127.0.0.1:8080
```

### Scan with increased Selenium concurrency (use with caution!):

```bash
python3 lazyxssX53x.py -f urls.txt -t 30 --selenium-workers 10
```

## Reporting

If vulnerabilities are confirmed via Selenium, a multi-page HTML report (`<output_filename>_page_N.html`) is generated using a futuristic dashboard theme. The report includes summary statistics and a paginated list of vulnerable URLs and payloads.

<div align="center">

**Example Report UI Snippet**
![image](https://github.com/user-attachments/assets/15b5626e-4e8b-4319-93fc-6b313c54de8b)

</div>

## Important Notes

*   **Reflected XSS:** This tool primarily focuses on reflected XSS and confirms findings using Selenium's alert detection. It does **not** currently perform advanced DOM XSS analysis.
*   **Chrome Path:** If you see `Chrome Version: N/A`, the script couldn't find Chrome automatically. Use the `--chrome-path` argument to provide the full path to your `chrome.exe` or `chromium-browser` executable.
*   **Resource Usage:** Selenium can be resource-intensive. Monitor your CPU/RAM when using high numbers for `--selenium-workers`.
*   **WAF Detection:** WAF detection is basic and might not identify all WAFs or may have false positives.
*   **Proxy Limitation:** The `--proxy` option currently only affects HTTP requests made by the `requests` library (like reflection checks and WAF detection), not the Selenium browser instances.
*   **Ethical Use:** This tool is intended for educational purposes and authorized security testing only. **Always obtain permission** before scanning any website you do not own.

## Contribution

Contributions are welcome! Feel free to submit issues or pull requests to help improve LazyXSS.

## Support the Author

If you find this tool helpful, consider supporting my work:

<div align="center">
<a href="https://buymeacoffee.com/iamunixtz" target="_blank"><img src="https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=&slug=iamunixtz&button_colour=06b6d4&font_colour=0f172a&font_family=Inter&outline_colour=000000&coffee_colour=FFDD00" alt="Buy Me A Coffee" style="height: 41px !important;width: 174px !important;" ></a>
</div>

---

**Author:** Iamunixtz | [GitHub](https://github.com/iamunixtz) | [Twitter/X](https://x.com/iamunixtz)
