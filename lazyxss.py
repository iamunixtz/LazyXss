import argparse
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.parse
import concurrent.futures
import signal
import requests
from requests.adapters import HTTPAdapter
from requests.packages.urllib3.util.retry import Retry
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, NoAlertPresentException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import psutil
import re
import math
import html
import random
import socket

# ANSI escape codes for colors
GREEN = "\033[92m"
CYAN = "\033[96m"
RED = "\033[91m"
RESET = "\033[0m"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')

# Global semaphore to limit concurrent Selenium instances
# Initialized in main() based on args
selenium_semaphore = None

# Flag for graceful shutdown
shutdown_flag = threading.Event()

# Track Selenium processes for cleanup
selenium_processes = []

# Track vulnerable URLs for the report
vulnerable_urls = []

# Global variable to store chrome path if provided
chrome_executable_path = None

# --- User Agent List ---
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36"
]
# ---------------------

### Signal Handlers for Ctrl+C and Ctrl+Z
def signal_handler(sig, frame):
    """Handle Ctrl+C (SIGINT) and Ctrl+Z (SIGTSTP) gracefully."""
    global vulnerable_urls, global_args # Need args for output base
    if not shutdown_flag.is_set():
        print("\nInterrupt detected. Do you want to quit the tool? [y/n]: ", end='', flush=True)
        shutdown_flag.set()
        # Don't cleanup selenium immediately, allow report generation first if quitting
        # cleanup_selenium()
        while True:
            try:
                choice = input().lower()
                if choice in ["y", "yes"]:
                    print("Exiting...")
                    # --- Save Report on Exit --- #
                    if vulnerable_urls and global_args:
                        print("Attempting to save report before exiting...")
                        try:
                            output_base = os.path.splitext(global_args.output)[0]
                            # Need total counts, might be inaccurate on early exit
                            # Use placeholders or calculate based on current state if possible
                            # For simplicity, using placeholder values or len(vulnerable_urls)
                            est_total = len(vulnerable_urls) # Placeholder
                            generate_html_report(output_base, est_total, len(vulnerable_urls), 0, -1)
                        except Exception as e:
                            print(f"{RED}Could not save report on exit: {e}{RESET}")
                    # -------------------------- #
                    cleanup_selenium() # Cleanup after attempting save
                    os._exit(0)
                elif choice in ["n", "no"]:
                    print("Resuming...")
                    shutdown_flag.clear()
                    break
                else:
                    print("Please enter 'y' or 'n': ", end='', flush=True)
            except EOFError:
                print("Exiting due to EOF...")
                cleanup_selenium() # Cleanup on EOF too
                os._exit(0)

signal.signal(signal.SIGINT, signal_handler)
# Only register SIGTSTP on non-Windows platforms
if sys.platform != 'win32':
    signal.signal(signal.SIGTSTP, signal_handler)

### Cleanup Function
def cleanup_selenium():
    """Close all Selenium-related Chrome processes."""
    global selenium_processes
    for proc in selenium_processes[:]:
        try:
            if proc.is_running():
                proc.terminate()
                proc.wait(timeout=2)
        except (psutil.NoSuchProcess, psutil.TimeoutExpired):
            pass
        finally:
            selenium_processes.remove(proc)
    selenium_processes.clear()

### Utility Functions

def get_terminal_width():
    """Return the terminal width, defaulting to 80."""
    try:
        return shutil.get_terminal_size().columns
    except Exception:
        return 80

def print_banner():
    """Print a centered, green banner with a fully connected frame."""
    term_width = get_terminal_width()
    banner_lines = [
        "██╗      █████╗ ███████╗██╗   ██╗    ██╗  ██╗███████╗███████╗",
        "██║     ██╔══██╗╚══███╔╝╚██╗ ██╔╝    ╚██╗██╔╝██╔════╝██╔════╝",
        "██║     ███████║  ███╔╝  ╚████╔╝      ╚███╔╝ ███████╗███████╗",
        "██║     ██╔══██║ ███╔╝    ╚██╔╝       ██╔██╗ ╚════██║╚════██║",
        "███████╗██║  ██║███████╗   ██║       ██╔╝ ██╗███████║███████║",
        "╚══════╝╚═╝  ╚═╝╚══════╝   ╚═╝       ╚═╝  ╚═╝╚══════╝╚══════╝",
        "https://github.com/iamunixtz/LazyXss"
    ]
    max_line_length = max(len(line) for line in banner_lines)
    frame_width = max(max_line_length + 4, term_width - 4)  # Adjust frame to screen size
    frame_border_top = f"{GREEN}╔{'═' * (frame_width + 2)}╗{RESET}"
    frame_border_bottom = f"{GREEN}╚{'═' * (frame_width + 2)}╝{RESET}"
    print(frame_border_top)
    for line in banner_lines:
        print(f"{GREEN}║{RESET} {GREEN}{line.center(frame_width)}{RESET} {GREEN}║{RESET}")
    print(frame_border_bottom)
    print("\n")

def generate_html_report(output_base, total_urls, total_vuln, total_non_vuln, time_taken):
    """Generate the HTML report with the futuristic dashboard UI, including pagination."""
    global vulnerable_urls
    items_per_page = 10 # Number of vulnerabilities per page

    if not vulnerable_urls:
        logging.info("No vulnerabilities found, skipping HTML report generation.")
        return

    total_pages = math.ceil(len(vulnerable_urls) / items_per_page)
    if total_pages == 0: total_pages = 1 # Ensure at least one page if list is empty (though checked above)

    for page_num in range(total_pages):
        current_page = page_num + 1
        start_idx = page_num * items_per_page
        end_idx = start_idx + items_per_page
        page_vulnerabilities = vulnerable_urls[start_idx:end_idx]

        # ---- CSS from styles.css ----
        css_styles = """
/* Base styles */
:root {
  --bg-primary: #0f172a;
  --bg-secondary: #1e293b;
  --bg-tertiary: #334155;
  --text-primary: #f1f5f9;
  --text-secondary: #94a3b8;
  --text-muted: #64748b;
  --border-color: rgba(148, 163, 184, 0.2);
  --card-bg: rgba(30, 41, 59, 0.5);
  --cyan: #06b6d4;
  --cyan-dark: #0891b2;
  --blue: #3b82f6;
  --blue-dark: #2563eb;
  --purple: #a855f7;
  --purple-dark: #9333ea;
  --green: #10b981;
  --green-dark: #059669;
  --amber: #f59e0b;
  --amber-dark: #d97706;
  --red: #ef4444;
  --red-dark: #dc2626;
  --pink: #ec4899;
  --indigo: #6366f1;
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Inter', sans-serif;
  background: linear-gradient(to bottom right, #000, #0f172a);
  color: var(--text-primary);
  min-height: 100vh;
  position: relative;
  overflow-x: auto; /* Allow horizontal scroll if needed */
}

.dark {
  color-scheme: dark;
}

.container {
  max-width: 1400px;
  margin: 0 auto;
  padding: 1rem;
  position: relative;
  z-index: 10;
}

/* Particles background */
#particles-js {
  position: fixed; /* Use fixed to keep it in background */
  width: 100%;
  height: 100%;
  top: 0;
  left: 0;
  z-index: 1;
  opacity: 0.3;
}

/* Header */
header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 0;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 1.5rem;
}

.header-left {
    display: flex;
    align-items: center;
    gap: 1rem;
}

.logo {
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.logo-text {
  font-weight: bold;
  font-size: 1.25rem;
  background: linear-gradient(to right, var(--cyan), var(--blue));
  -webkit-background-clip: text;
  background-clip: text;
  color: transparent;
}

.bmc-button img {
    height: 36px; /* Adjust size as needed */
    vertical-align: middle;
}

/* Card */
.card {
  background-color: var(--card-bg);
  border: 1px solid var(--border-color);
  border-radius: 0.5rem;
  backdrop-filter: blur(8px);
  overflow: hidden;
  margin-bottom: 1.5rem;
}

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem;
  border-bottom: 1px solid var(--border-color);
}

.card-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 500;
}

.card-content {
  padding: 1rem;
}

/* Icons */
.icon-small {
  width: 1rem;
  height: 1rem;
}

.icon-medium {
  width: 1.5rem;
  height: 1.5rem;
}

.icon-large {
    width: 1.8rem;
    height: 1.8rem;
}

.icon-cyan {
  color: var(--cyan);
}

.icon-blue {
  color: var(--blue);
}

.icon-green {
  color: var(--green);
}

.icon-amber {
  color: var(--amber);
}

.icon-red {
    color: var(--red);
}

.icon-purple {
  color: var(--purple);
}

/* Metrics */
.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); /* Responsive grid */
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.metric-card {
  background-color: rgba(30, 41, 59, 0.5);
  border-radius: 0.5rem;
  padding: 1.25rem; /* Slightly more padding */
  position: relative;
  overflow: hidden;
  border: 1px solid var(--border-color); /* Default border */
}

.metric-card.cyan-border { border-color: rgba(6, 182, 212, 0.3); }
.metric-card.red-border { border-color: rgba(239, 68, 68, 0.3); }
.metric-card.green-border { border-color: rgba(16, 185, 129, 0.3); }
.metric-card.blue-border { border-color: rgba(59, 130, 246, 0.3); }


.metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center; /* Align icon vertically */
  margin-bottom: 0.75rem; /* More space */
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.metric-value {
  font-size: 1.75rem; /* Larger value */
  font-weight: bold;
  margin-bottom: 0.25rem;
  color: var(--text-primary); /* Simpler color */
  font-family: 'JetBrains Mono', monospace; /* Monospace for numbers */

}

.metric-detail {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.glow-effect {
  position: absolute;
  bottom: -2rem; /* Adjust position */
  right: -2rem;
  height: 5rem; /* Adjust size */
  width: 5rem;
  border-radius: 50%;
  opacity: 0.15; /* Adjust opacity */
  filter: blur(12px); /* Adjust blur */
}

.glow-effect.cyan { background: radial-gradient(circle, var(--cyan) 0%, transparent 70%); }
.glow-effect.red { background: radial-gradient(circle, var(--red) 0%, transparent 70%); }
.glow-effect.green { background: radial-gradient(circle, var(--green) 0%, transparent 70%); }
.glow-effect.blue { background: radial-gradient(circle, var(--blue) 0%, transparent 70%); }


/* Vulnerability List Specific Styles */
.vuln-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.vuln-item {
  display: flex;
  gap: 0.75rem;
  padding: 0.75rem 1rem; /* Adjust padding */
  border-radius: 0.375rem;
  background-color: rgba(30, 41, 59, 0.5);
  border: 1px solid var(--border-color);
  align-items: flex-start; /* Align icon to top */
}

.vuln-icon {
  padding-top: 0.125rem; /* Align icon slightly better */
}

.vuln-content {
  flex: 1;
  word-break: break-all; /* Prevent long URLs/payloads from overflowing */
}

.vuln-label {
  font-size: 0.75rem;
  color: var(--text-muted);
  font-weight: 500;
}

.vuln-data {
  font-size: 0.875rem;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
  margin-top: 0.125rem; /* Small space below label */
  line-height: 1.4;
}

.vuln-data a {
    color: var(--cyan); /* Make links cyan */
    text-decoration: none;
}

.vuln-data a:hover {
    text-decoration: underline;
}

/* Pagination Styles (Bootstrap-inspired, themed) */
.pagination {
    display: flex;
    justify-content: center; /* Center pagination */
    padding-left: 0;
    list-style: none;
    border-radius: 0.25rem;
    margin-top: 2rem;
}

.page-item:first-child .page-link {
    margin-left: 0;
    border-top-left-radius: 0.25rem;
    border-bottom-left-radius: 0.25rem;
}
.page-item:last-child .page-link {
    border-top-right-radius: 0.25rem;
    border-bottom-right-radius: 0.25rem;
}

.page-item .page-link {
    position: relative;
    display: block;
    padding: 0.5rem 0.75rem;
    margin-left: -1px; /* Collapse borders */
    line-height: 1.25;
    color: var(--cyan); /* Link color */
    background-color: var(--bg-secondary); /* Background */
    border: 1px solid var(--border-color);
    text-decoration: none;
    transition: color .15s ease-in-out,background-color .15s ease-in-out,border-color .15s ease-in-out;
}

.page-item .page-link:hover {
    z-index: 2;
    color: var(--cyan-dark);
    background-color: var(--bg-tertiary);
    border-color: var(--border-color);
}

.page-item.active .page-link {
    z-index: 3;
    color: #fff; /* Active text color */
    background-color: var(--cyan); /* Active background */
    border-color: var(--cyan);
}

.page-item.disabled .page-link {
    color: var(--text-muted); /* Disabled text color */
    pointer-events: none;
    background-color: var(--bg-secondary);
    border-color: var(--border-color);
    opacity: 0.6;
}

/* Footer */
footer {
  text-align: center;
  margin-top: 3rem;
  padding: 1.5rem 1rem; /* More padding */
  font-size: 0.875rem;
  color: var(--text-muted);
  border-top: 1px solid var(--border-color);
  display: flex; /* Use flexbox for alignment */
  flex-direction: column; /* Stack items vertically */
  align-items: center; /* Center items */
  gap: 1rem; /* Space between text and icons */
}

.social-links {
    display: flex;
    gap: 1.5rem; /* Space between icons */
}

.social-links a {
    color: var(--text-secondary);
    transition: color 0.2s;
}

.social-links a:hover {
    color: var(--cyan);
}

/* Animations */
@keyframes pulse {
  0%, 100% { opacity: 0.1; }
  50% { opacity: 0.2; }
}

.glow-effect {
    animation: pulse 3s infinite ease-in-out;
}

/* Add JetBrains Mono font */
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
        """

        # ---- JavaScript Snippets ----
        js_scripts = """
<script src="https://cdn.jsdelivr.net/npm/particles.js@2.0.0/particles.min.js"></script>
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
<script>
  // Initialize Lucide icons
  lucide.createIcons();

  // Initialize particles.js
  particlesJS('particles-js', {
    particles: {
      number: { value: 80, density: { enable: true, value_area: 800 } },
      color: { value: ['#06b6d4', '#3b82f6', '#a855f7'] }, // Cyan, Blue, Purple
      shape: { type: 'circle' },
      opacity: { value: 0.4, random: true, anim: { enable: true, speed: 0.8, opacity_min: 0.1, sync: false } },
      size: { value: 2.5, random: true, anim: { enable: true, speed: 2, size_min: 0.3, sync: false } },
      line_linked: { enable: true, distance: 120, color: '#06b6d4', opacity: 0.25, width: 1 },
      move: { enable: true, speed: 1, direction: 'none', random: true, straight: false, out_mode: 'out', bounce: false }
    },
    interactivity: {
      detect_on: 'canvas',
      events: { onhover: { enable: true, mode: 'grab' }, onclick: { enable: false }, resize: true },
      modes: { grab: { distance: 100, line_linked: { opacity: 0.5 } } }
    },
    retina_detect: true
  });
</script>
    """

        # ---- Generate Vulnerability List HTML for the current page ----
        vuln_list_html = ""
        if page_vulnerabilities:
            for idx, (url, payload) in enumerate(page_vulnerabilities, start=start_idx + 1):
                safe_url = html.escape(url)
                safe_payload = html.escape(payload)
                vuln_list_html += f"""
                <div class="vuln-item">
                  <div class="vuln-icon icon-red"><i data-lucide="shield-alert" class="icon-medium"></i></div>
                  <div class="vuln-content">
                      <div>
                          <div class="vuln-label">URL:</div>
                          <div class="vuln-data"><a href="{safe_url}" target="_blank">{safe_url}</a></div>
                      </div>
                      <div style="margin-top: 0.5rem;">
                          <div class="vuln-label">Payload:</div>
                          <div class="vuln-data">{safe_payload}</div>
                      </div>
                  </div>
                </div>
                """
        else:
             # This case shouldn't happen if total_pages > 0 but included for safety
             vuln_list_html = "<p style='color: var(--text-secondary); text-align: center;'>No vulnerabilities on this page.</p>"

        # ---- Generate Pagination Links ----
        pagination_html = ""
        if total_pages > 1:
            pagination_html += '<nav aria-label="Vulnerability pages"><ul class="pagination">'

            # Previous Link
            prev_disabled = ' disabled' if current_page == 1 else ''
            prev_href = f'href="{output_base}_page_{current_page - 1}.html"' if current_page > 1 else 'href="#"'
            pagination_html += f'<li class="page-item{prev_disabled}"><a class="page-link" {prev_href} aria-label="Previous"><span aria-hidden="true">&laquo;</span> Prev</a></li>'

            # Page Number Links (Basic implementation - could add ellipsis for many pages later)
            for i in range(total_pages):
                page_link_num = i + 1
                active = ' active' if page_link_num == current_page else ''
                pagination_html += f'<li class="page-item{active}"><a class="page-link" href="{output_base}_page_{page_link_num}.html">{page_link_num}</a></li>'

            # Next Link
            next_disabled = ' disabled' if current_page == total_pages else ''
            next_href = f'href="{output_base}_page_{current_page + 1}.html"' if current_page < total_pages else 'href="#"'
            pagination_html += f'<li class="page-item{next_disabled}"><a class="page-link" {next_href} aria-label="Next">Next <span aria-hidden="true">&raquo;</span></a></li>'

            pagination_html += '</ul></nav>'

        # ---- Main HTML Structure ----
        html_content = f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>LazyXSS Scan Report - Page {current_page}/{total_pages}</title>
  <style>
    {css_styles}
  </style>
</head>
<body class="dark">
  <div id="particles-js"></div>
  <div class="container">
    <!-- Header -->
    <header>
      <!-- <div class=\"header-left\"> -->
        <div class=\"logo\">
          <i data-lucide=\"hexagon\" class=\"icon-cyan icon-medium\"></i>
          <span class=\"logo-text\">LazyXSS Scan Report</span>
        </div>
        <a href=\"https://buymeacoffee.com/iamunixtz\" target=\"_blank\" class=\"bmc-button\">
          <img src=\"https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=&slug=iamunixtz&button_colour=06b6d4&font_colour=0f172a&font_family=Inter&outline_colour=000000&coffee_colour=FFDD00\" alt=\"Buy Me A Coffee\" >
        </a>
      <!-- </div> -->
    </header>

    <!-- Main content -->
    <main>
      <!-- Scan Summary Metrics -->
      <div class="metrics-grid">
        <div class="metric-card blue-border">
          <div class="metric-header">
            <div>URLs Tested</div>
            <i data-lucide="list" class="icon-blue icon-medium"></i>
          </div>
          <div class="metric-value">{total_urls}</div>
          <div class="metric-detail">Total URLs scanned</div>
          <div class="glow-effect blue"></div>
        </div>
        <div class="metric-card red-border">
          <div class="metric-header">
            <div>Vulnerabilities Found</div>
            <i data-lucide="shield-alert" class="icon-red icon-medium"></i>
          </div>
          <div class="metric-value">{total_vuln}</div>
          <div class="metric-detail">Reflected & Confirmed XSS</div>
           <div class="glow-effect red"></div>
        </div>
        <div class="metric-card green-border">
          <div class="metric-header">
            <div>Non-Vulnerable</div>
            <i data-lucide="shield-check" class="icon-green icon-medium"></i>
          </div>
          <div class="metric-value">{total_non_vuln}</div>
          <div class="metric-detail">URLs without confirmed XSS</div>
           <div class="glow-effect green"></div>
        </div>
         <div class="metric-card cyan-border">
          <div class="metric-header">
            <div>Scan Duration</div>
            <i data-lucide="clock" class="icon-cyan icon-medium"></i>
          </div>
          <div class="metric-value">{time_taken}s</div>
          <div class="metric-detail">Total time elapsed</div>
           <div class="glow-effect cyan"></div>
        </div>
      </div>

      <!-- Vulnerable URLs List -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <i data-lucide="bug" class="icon-red"></i>
            Detected Vulnerabilities
          </div>
        </div>
        <div class="card-content">
          <div class="vuln-list">
            {vuln_list_html}
          </div>
          {pagination_html}
        </div>
      </div>
    </main>

    <!-- Footer -->
    <footer>
      <div>LazyXss Scanner | Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}</div>
      <div class="social-links">
        <a href="https://github.com/iamunixtz/" target="_blank" title="GitHub"><i data-lucide="github" class="icon-large"></i></a>
        <a href="https://x.com/iamunixtz" target="_blank" title="Twitter/X"><i data-lucide="twitter" class="icon-large"></i></a>
      </div>
    </footer>

  </div>

  {js_scripts}
</body>
</html>
"""

        # Write the HTML file for the current page
        report_filename = f"{output_base}_page_{current_page}.html"
        try:
            with open(report_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"\n{GREEN}Generated HTML report: {report_filename}{RESET}")
        except IOError as e:
            print(f"\n{RED}Error writing HTML report '{report_filename}': {e}{RESET}")

def print_usage_manual():
    """Print the usage manual instructions."""
    manual = (
        "Usage: python3 lazyxssX53x.py [OPTIONS]\n\n"
        "Example (URL): python3 lazyxssX53x.py -u \"http://test.com?q=test\" -p payloads.txt\n"
        "Example (File): python3 lazyxssX53x.py -f urls.txt -p payloads.txt -o results.txt\n\n"
        "Options:\n"
        "  -u, --url            Specify a single URL to test.\n"
        "  -f, --file           Specify a file containing URLs (one per line).\n"
        "  -p, --payloads       Specify the payload file (default: payloads.txt).\n"
        "  -t, --threads        Number of threads (default: 50).\n"
        "  -e, --encoding       Number of times to URL-encode the payloads (default: 0).\n"
        "  -o, --output         Output file to write vulnerable URLs (default: result.txt).\n"
        "                       The HTML report will be named based on this file (e.g., result.html).\n"
        "  -T, --time-sec       Timeout in seconds for Selenium checks (default: 2).\n"
        "  --chrome-path        Specify the full path to the chrome/chromium executable.\n"
        "                       (Use if automatic detection fails)\n"
        "  --selenium-workers   Number of concurrent Selenium browser instances (default: 5).\n"
        "                       Increase cautiously based on system resources.\n"
        "  --proxy              Specify a proxy server (e.g., http://user:pass@127.0.0.1:8080).\n"
        "                       (Note: Affects HTTP requests, not Selenium checks).\n"
        "  -h, --help           Show this help message and exit.\n\n"
        "Description:\n"
        "  High-speed XSS scanner with HTTP reflection and Selenium verification.\n"
        "  Generates a futuristic HTML report (if vulnerabilities are found).\n"
    )
    print(manual)

class CustomHelpAction(argparse.Action):
    """Custom help action that prints the usage manual and banner."""
    def __call__(self, parser, namespace, values, option_string=None):
        print_usage_manual()
        print_banner()
        parser.print_help()
        parser.exit()

def get_chrome_version():
    """Get the numeric Chrome version, checking common paths for Windows/Linux."""
    version = "N/A"
    commands = []

    if sys.platform == 'win32':
        # Windows: Check registry, common Program Files locations
        try:
            import winreg
            reg_paths = [
                r"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\App Paths\\chrome.exe",
                # Add other potential registry keys if needed
            ]
            chrome_path = None
            for path in reg_paths:
                 try:
                     key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
                     chrome_path = winreg.QueryValue(key, None) # Get default value
                     winreg.CloseKey(key)
                     if chrome_path and os.path.exists(chrome_path):
                         # Ensure path with spaces is quoted for the command
                         commands.append(f'\"{chrome_path}\" --version')
                         break # Found via registry
                 except OSError:
                     continue # Key not found or access denied

            # Fallback to common paths if registry fails or wasn't found
            if not chrome_path or not any(chrome_path in cmd for cmd in commands):
                 common_paths = [
                    os.path.expandvars("%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe"),
                    os.path.expandvars("%ProgramFiles(x86)%\\Google\\Chrome\\Application\\chrome.exe"),
                    os.path.expandvars("%LocalAppData%\\Google\\Chrome\\Application\\chrome.exe"),
                 ]
                 for path in common_paths:
                     if os.path.exists(path):
                         # Ensure path with spaces is quoted for the command
                         commands.append(f'\"{path}\" --version')

        except ImportError:
             # If winreg is not available (shouldn't happen on Windows usually)
             pass # Will try default command later
        except Exception as e:
            # Log potential issues during Windows detection
            logging.debug(f"Windows Chrome detection error: {e}")
            pass

    elif sys.platform == 'darwin': # macOS
        commands.append("/Applications/Google\\\\ Chrome.app/Contents/MacOS/Google\\\\ Chrome --version")
    else: # Linux/Other
        commands.extend([
            "google-chrome --version",
            "google-chrome-stable --version",
            "chromium-browser --version",
            "chromium --version"
        ])

    # Try the collected commands
    for cmd in commands:
        try:
            # Use shell=True cautiously, paths with spaces are quoted now
            # Set encoding explicitly for Windows
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL,
                                              text=True, encoding='utf-8', errors='ignore', timeout=2)
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)', output.strip())
            if match:
                version = match.group(1)
                logging.debug(f"Found Chrome version {version} using command: {cmd}")
                break # Found version
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logging.debug(f"Command failed for Chrome detection: {cmd} - {e}")
            continue # Command failed or not found, try next
        except Exception as e:
            logging.debug(f"Unexpected error during Chrome command execution: {cmd} - {e}")
            continue

    # If no version found via specific paths/commands, try a generic command as a last resort
    if version == "N/A" and sys.platform == 'win32':
        try:
            # Generic command for Windows, might find it if it's in PATH
            cmd = 'chrome --version'
            output = subprocess.check_output(cmd, shell=True, stderr=subprocess.DEVNULL,
                                              text=True, encoding='utf-8', errors='ignore', timeout=2)
            match = re.search(r'(\d+\.\d+\.\d+\.\d+)', output.strip())
            if match:
                version = match.group(1)
                logging.debug(f"Found Chrome version {version} using generic command: {cmd}")
        except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
            logging.debug(f"Generic command failed for Chrome detection: {cmd} - {e}")
        except Exception as e:
            logging.debug(f"Unexpected error during generic Chrome command execution: {cmd} - {e}")

    if version == "N/A":
        logging.warning(f"{RED}Could not automatically detect Chrome version. Selenium checks might fail.{RESET}")

    return version

def load_file_contents(file_path):
    """Load and return non-empty, stripped lines from a file."""
    if not os.path.isfile(file_path):
        logging.error(f"{RED}File '{file_path}' does not exist.{RESET}")
        return None
    with open(file_path, 'r') as file:
        lines = [line.strip() for line in file if line.strip()]
        return lines if lines else None

def encode_payload(payload, encode_times):
    """Encode a payload multiple times using URL encoding."""
    encoded = payload
    for _ in range(encode_times):
        encoded = urllib.parse.quote(encoded)
    return encoded

def generate_url_variations(base_url, payloads):
    """Generates URL variations by injecting RAW payloads into each parameter."""
    variations = []
    try:
        parsed_url = urllib.parse.urlparse(base_url)
        query_params = urllib.parse.parse_qs(parsed_url.query, keep_blank_values=True)

        # 1. Test original URL by appending payload (current behavior)
        # This handles cases with no params or testing the whole query string context
        for payload in payloads:
            # Simple append might be less effective if params exist, but include for baseline
            variations.append(f"{base_url}{payload}")

        # 2. Test each parameter individually
        for param_name in query_params:
            original_values = query_params[param_name] # It's a list
            for payload in payloads:
                # Create a copy to modify
                new_params = query_params.copy()
                # Replace the current parameter's value(s) with the RAW payload
                new_params[param_name] = [payload]

                # Rebuild query string - doseq=True handles multiple values if needed, though we replace with one payload
                new_query = urllib.parse.urlencode(new_params, doseq=True)
                # Reconstruct the URL
                new_url = urllib.parse.urlunparse((
                    parsed_url.scheme,
                    parsed_url.netloc,
                    parsed_url.path,
                    parsed_url.params,
                    new_query,
                    parsed_url.fragment
                ))
                variations.append(new_url)

        # Deduplicate (though unlikely with this method unless payload equals original value)
        variations = list(set(variations))
        logging.debug(f"Generated {len(variations)} variations for {base_url}")
        return variations

    except Exception as e:
        logging.error(f"{RED}Error parsing or generating variations for URL '{base_url}': {e}{RESET}")
        return [base_url] # Return original URL on error

### HTTP and Selenium Scanning Functions

def create_session(proxy_url=None):
    """Create a requests session with optimized retry logic and optional proxy."""
    session = requests.Session()
    # Set a random User-Agent for the session
    session.headers.update({'User-Agent': random.choice(USER_AGENTS)})

    retry = Retry(total=2, backoff_factor=0.1, status_forcelist=[500, 502, 503, 504])
    adapter = HTTPAdapter(max_retries=retry, pool_connections=100, pool_maxsize=100)
    session.mount('http://', adapter)
    session.mount('https://', adapter)

    if proxy_url:
        proxies = {
            'http': proxy_url,
            'https': proxy_url
        }
        session.proxies.update(proxies)
        logging.info(f"{CYAN}[info] Using proxy: {proxy_url}{RESET}")

    return session

def check_reflection(url, payload, session, timeout):
    """Check if payload is reflected with high accuracy."""
    if shutdown_flag.is_set():
        return False
    try:
        response = session.get(f"{url}{payload}", timeout=timeout)
        decoded_payload = urllib.parse.unquote(payload)
        return payload in response.text or decoded_payload in response.text
    except (requests.RequestException, requests.Timeout):
        return False

def check_xss_with_selenium(url, payloads, timeout=2):
    """High-speed, accurate Selenium check for XSS using WebDriverWait."""
    global chrome_executable_path # Access the global variable
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--blink-settings=imagesEnabled=false")
    # --- Add flags to potentially reduce telemetry/update checks --- #
    chrome_options.add_argument("--disable-component-update")
    chrome_options.add_argument("--disable-background-networking")
    # Add experimental options if necessary, use with caution
    # chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
    # ------------------------------------------------------------- #
    chrome_options.set_capability("unhandledPromptBehavior", "dismiss")

    # Set Chrome binary location if provided via argument
    if chrome_executable_path and os.path.exists(chrome_executable_path):
        logging.debug(f"Using specified Chrome binary: {chrome_executable_path}")
        chrome_options.binary_location = chrome_executable_path
    elif chrome_executable_path:
        logging.warning(f"{RED}Specified Chrome path does not exist: {chrome_executable_path}{RESET}")

    with tempfile.TemporaryDirectory() as tmpdirname:
        chrome_options.add_argument(f"--user-data-dir={tmpdirname}")
        service = Service()
        driver = None
        try:
            driver = webdriver.Chrome(service=service, options=chrome_options)
            driver.set_page_load_timeout(timeout)
            try:
                pid = driver.service.process.pid
                proc = psutil.Process(pid)
                selenium_processes.append(proc)
            except psutil.NoSuchProcess:
                return [(False, p, None) for p in payloads]
            results = []
            # Use the full timeout provided for waiting for the alert
            # wait_timeout = max(0.1, timeout * 0.5) # Wait for half the page load timeout, min 0.1s
            wait_timeout = timeout # Use the full timeout specified by -T
            logging.debug(f"WebDriverWait timeout for alert: {wait_timeout}s")

            for payload in payloads:
                if shutdown_flag.is_set():
                    break
                full_url = f"{url}{payload}"
                alerted = False
                alert_text = None
                try:
                    driver.get(full_url)
                    # Add a very small fixed delay to allow initial script execution
                    time.sleep(0.05)
                    # Explicitly wait for an alert to be present
                    wait = WebDriverWait(driver, wait_timeout)
                    alert = wait.until(EC.alert_is_present())
                    if alert:
                        alert_text = alert.text
                        alert.accept()
                        alerted = True
                        logging.debug(f"Alert detected for {full_url} with text: {alert_text}")
                    else:
                         # This case should technically not be reached if wait.until succeeded
                         logging.debug(f"No alert detected (wait.until returned non-alert?) for {full_url}")
                except TimeoutException:
                    # No alert appeared within the wait timeout
                    logging.debug(f"Timeout ({wait_timeout}s) waiting for alert on {full_url}")
                    alerted = False
                except NoAlertPresentException:
                    # Should be caught by WebDriverWait, but as a fallback
                    logging.debug(f"NoAlertPresentException (fallback) after wait for {full_url}")
                    alerted = False
                except WebDriverException as e:
                    # More specific logging for WebDriver errors
                    logging.warning(f"{RED}WebDriverException for {full_url}: {str(e).splitlines()[0]}{RESET}") # Log first line of error
                    alerted = False
                finally:
                    results.append((alerted, payload, alert_text if alerted else None))
                    try:
                       driver.get("about:blank") # Navigate away to clear state
                    except WebDriverException:
                        pass # Ignore errors navigating away
            return results
        finally:
            if driver:
                driver.quit()
                try:
                    selenium_processes.remove(proc)
                except (ValueError, psutil.NoSuchProcess):
                    pass

def safe_launch_selenium(url, payloads, timeout):
    """Launch Selenium with extreme efficiency."""
    if shutdown_flag.is_set():
        return [(False, p, None) for p in payloads]
    with selenium_semaphore:
        while psutil.cpu_percent() > 60 or psutil.virtual_memory().percent > 60:
            if shutdown_flag.is_set():
                return [(False, p, None) for p in payloads]
            time.sleep(0.5)
        return check_xss_with_selenium(url, payloads, timeout)

### Logging and Worker Functions

def log_vulnerability(full_url, is_vuln, payload, output_file):
    """Log vulnerability status and write vulnerable URLs."""
    global vulnerable_urls
    status = f"{GREEN}[vuln]{RESET}" if is_vuln else f"{RED}[not vuln]{RESET}"
    message = f"{GREEN}[info]{RESET} {full_url} {status}"
    logging.info(message)
    if output_file and is_vuln and not shutdown_flag.is_set():
        output_file.write(f"{full_url}\n")
        output_file.flush()
        vulnerable_urls.append((full_url, payload))

def test_url_payload(url, payloads, proxies, encode_times, timeout, output_file):
    """Test a single specific URL variation (reflection check + potential Selenium).
       Note: 'payloads' argument is somewhat redundant here now, but kept for structure."""
    session = create_session(proxies)
    # Since the payload is already IN the URL, we just need one 'effective' payload for reflection check
    # Extract the presumed payload part for logging/comparison (this is an approximation)
    # Handle potential errors if URL doesn't contain '='
    try:
        effective_payload = urllib.parse.unquote(url.split('=')[-1]) # Get last value and decode once for comparison/logging
    except IndexError:
        effective_payload = "" # No params?

    # --- Apply encoding only if requested --- #
    encoded_url = url
    if encode_times > 0:
        # This part needs refinement - how to encode just the payload part within the URL?
        # For now, let's skip targeted encoding here as it's complex.
        # The original encode_payload function worked on the standalone payload.
        # We will rely on check_reflection handling potential encoding issues for now.
        # A more robust solution would involve parsing, encoding the specific value, and rebuilding.
        pass # Placeholder - Encoding before request needs careful implementation here.
        logging.debug(f"Encoding ({encode_times} rounds) requested but not applied pre-request in this version.")
    # --------------------------------------- #

    # Perform reflection check on the specific URL variation
    # Pass the *original* potentially unencoded payload for reflection check
    reflected = check_reflection(url, effective_payload, session, timeout)

    if reflected:
        # If reflected, perform Selenium check on this specific URL variation
        # Pass the extracted payload for logging consistency
        results = safe_launch_selenium(url, [effective_payload], timeout)
        for is_vuln, payload_used_in_selenium, _ in results:
            # Log using the full URL variation and the extracted payload
            log_vulnerability(url, is_vuln, payload_used_in_selenium, output_file)
    else:
        # Log as not vulnerable if not reflected
        log_vulnerability(url, False, effective_payload, output_file)

def worker(url_variation, payloads, proxies, encode_times, timeout, output_file):
    """Worker function now processes a single URL variation."""
    if not shutdown_flag.is_set():
        # Pass the single URL variation and the original payloads list (though redundant inside)
        test_url_payload(url_variation, payloads, proxies, encode_times, timeout, output_file)

def test_xss(urls_to_scan, payloads_to_test, proxies, encode_times, num_threads, timeout, output_file, output_base):
    """Test multiple URLs (potentially with variations) for XSS."""
    global vulnerable_urls
    start_time = time.time()
    # This now receives the expanded list of URLs (parameter variations)
    # total_urls_tested = 0 # This variable is not used, remove?
    base_url_count = len(urls_to_scan) # Keep track of original URLs provided

    with concurrent.futures.ThreadPoolExecutor(max_workers=num_threads) as executor:
        futures = [
            executor.submit(worker, url, payloads_to_test, proxies, encode_times, timeout, output_file)
            for url in urls_to_scan
        ]
        try:
            # Update progress bar using tqdm or similar could go here
            processed_count = 0
            for future in concurrent.futures.as_completed(futures):
                if shutdown_flag.is_set():
                    break
                try:
                    future.result() # Check for exceptions from worker
                except Exception as exc:
                     logging.error(f"{RED}Worker thread generated an exception: {exc}{RESET}")
                processed_count += 1 # Assuming one future corresponds to one URL
                # Simple progress indicator (can be replaced with tqdm)
                # print(f"Progress: {processed_count}/{len(urls)} URLs", end='\r')

            # Ensure progress indicator line is cleared
            # print(" " * 50, end='\r')

        finally:
            # Wait for remaining futures to complete or cancel if shutting down
            if shutdown_flag.is_set():
                logging.info("\nCancelling remaining tasks...")
                for f in futures:
                    f.cancel()
            # Ensure executor shuts down properly, waiting for running tasks if not cancelled
            executor.shutdown(wait=not shutdown_flag.is_set())
            # Final cleanup after all threads are done or cancelled
            cleanup_selenium()

    end_time = time.time()
    time_taken = int(end_time - start_time)
    total_vuln = len(vulnerable_urls)
    # if reflection checks prune payloads, but gives a rough idea.
    # The number of actual tests depends on variations * payloads
    # urls_to_scan already contains the variations
    estimated_total_tests = len(urls_to_scan) # A better estimate of requests
    total_non_vuln = estimated_total_tests - total_vuln

    # Generate HTML report after scan completes (if any vulnerabilities found)
    if vulnerable_urls:
        # Inform user about multi-page report
        report_name_base = f"{output_base}_page_1.html"
        print(f"\n{GREEN}Generated HTML report (multiple pages): {report_name_base} ...{RESET}")
        # Call the report generation function (which now handles pagination internally)
        generate_html_report(output_base, estimated_total_tests, total_vuln, total_non_vuln, time_taken)
    else:
        print(f"\n{CYAN}Scan completed. No vulnerabilities found.{RESET}")
        # --- Print Summary Table --- #
        print("\n" + "="*40)
        print(f"Scan Summary".center(40))
        print("-"*40)
        print(f"| {'Metric':<25} | {'Value':<10} |")
        print("-"*40)
        print(f"| {'Base URLs Scanned:':<25} | {base_url_count:<10} |") # Report base URLs
        print(f"| {'Total Tests (Variations):':<25} | {estimated_total_tests:<10} |") # Report total variations tested
        print(f"| {'Vulnerabilities Found:':<25} | {GREEN}{total_vuln}{RESET}{ ' ' * (10 - len(str(total_vuln)) - (len(GREEN)+len(RESET)) if total_vuln > 0 else 10 - len(str(total_vuln))) } |") # Adjust spacing for color codes
        print(f"| {'Time Taken:':<25} | {time_taken:<7} sec |")
        print("="*40)
        # --------------------------- #

# Store args globally for access in worker threads if needed (e.g., for chrome_path)
# Alternatively, pass args down through function calls
global_args = None

### Main Function

def main():
    """Main function: parse arguments, display banner, and start scanning."""
    global global_args, chrome_executable_path # Declare modification of globals

    # --- Clear Screen --- #
    os.system('cls' if os.name == 'nt' else 'clear')
    # ------------------ #

    parser = argparse.ArgumentParser(
        description="XSS Vulnerability Checker Tool",
        epilog="For detailed instructions, see the usage manual above.",
        add_help=False
    )
    parser.register("action", "custom_help", CustomHelpAction)
    parser.add_argument('-h', '--help', action="custom_help", nargs=0, help="Show this help message and exit.")
    parser.add_argument('-u', '--url', type=str, help="Specify a single URL to test.")
    parser.add_argument('-f', '--file', type=str, help="Specify a file with URLs.")
    parser.add_argument('-p', '--payloads', type=str, default="payloads.txt", help="Payload file (default: payloads.txt).")
    parser.add_argument('-t', '--threads', type=int, default=20, help="Number of concurrent URL processing threads (default: 20).")
    parser.add_argument('-e', '--encoding', type=int, default=0, help="Encoding times (default: 0).")
    parser.add_argument('-o', '--output', type=str, default='result.txt', help="Output file (default: result.txt).")
    parser.add_argument('-T', '--time-sec', type=int, default=2, help="Timeout in seconds for Selenium checks (default: 2).")
    parser.add_argument('--chrome-path', type=str, help="Specify the full path to the chrome executable.")
    parser.add_argument('--selenium-workers', type=int, default=5, help="Number of concurrent Selenium instances (default: 5).")
    parser.add_argument('--proxy', type=str, help="Proxy server URL (e.g., http://127.0.0.1:8080).")

    args = parser.parse_args()
    global_args = args # Store args globally

    # ---- Initialize Global Semaphore ----
    global selenium_semaphore
    if args.selenium_workers < 1:
        print(f"{RED}Error: Number of selenium workers must be at least 1.{RESET}")
        sys.exit(1)
    selenium_semaphore = threading.Semaphore(args.selenium_workers)
    logging.debug(f"Using {args.selenium_workers} concurrent Selenium workers.")
    # -------------------------------------

    # Store the chrome path if provided
    if args.chrome_path:
        chrome_executable_path = args.chrome_path

    # Display banner
    print_banner()

    # ---- Refined Startup Logging ----
    if args.url:
        logging.info(f"{CYAN}[info] Target URL: {args.url}{RESET}")
    else:
        logging.info(f"{CYAN}[info] Target File: {args.file}{RESET}")
    logging.info(f"{CYAN}[info] Payload File: {args.payloads}{RESET}")
    # Load payloads early to get count
    payloads = load_file_contents(args.payloads)
    if not payloads:
        print(f"{RED}Error: No valid payloads found in '{args.payloads}'.{RESET}")
        sys.exit(1)
    logging.info(f"{CYAN}[info] Total Payloads: {len(payloads)}{RESET}")

    # Load URLs
    base_urls = []
    if args.url:
        base_urls = [args.url]
    else:
        base_urls = load_file_contents(args.file)
        if not base_urls:
            print(f"{RED}Error: No valid URLs found in the file '{args.file}'.{RESET}")
            sys.exit(1)

    # --- DNS Pre-check (Moved Here) --- #
    try:
        if not base_urls: # Should not happen if previous checks passed, but safer
             raise ValueError("Base URL list is empty before DNS check.")
        first_target_url = base_urls[0]
        hostname = urllib.parse.urlparse(first_target_url).netloc
        if hostname:
            logging.info(f"{CYAN}[info] Performing initial DNS check for: {hostname}{RESET}")
            socket.gethostbyname(hostname)
            logging.info(f"{GREEN}[info] DNS resolution successful.{RESET}")
        else:
            logging.warning(f"{RED}[!] Could not extract hostname from first URL: {first_target_url}{RESET}")
    except socket.gaierror as e:
        print(f"\n{RED}Fatal Error: Could not resolve hostname '{hostname}'.{RESET}")
        print(f"{RED}       Reason: {e}{RESET}")
        print(f"{RED}       Please check your network connection and DNS settings.{RESET}")
        sys.exit(1)
    except Exception as e:
        print(f"\n{RED}Fatal Error: Unexpected issue during initial DNS check: {e}{RESET}")
        sys.exit(1)
    # ---------------------------------- #

    if args.proxy:
        # Proxy info is logged inside create_session if used
        pass

    logging.info(f"{CYAN}[info] URL Encoding Rounds: {args.encoding}{RESET}")
    logging.info(f"{CYAN}[info] Threads: {args.threads}{RESET}")
    logging.info(f"{CYAN}[info] Selenium Workers: {args.selenium_workers}{RESET}")
    logging.info(f"{CYAN}[info] Selenium Timeout: {args.time_sec}s{RESET}")
    logging.info(f"{CYAN}[info] Output File: {args.output}{RESET}")
    # ----------------------------------

    # Validate input: either a URL or a file must be provided, but not both
    if bool(args.url) == bool(args.file):
        print(f"{RED}Error: You must specify either a URL (-u) or a file (-f), but not both.{RESET}")
        print_usage_manual()
        sys.exit(1)

    # --- Generate URL Variations --- #
    urls_to_test = []
    print(f"{CYAN}[info] Generating URL variations for {len(base_urls)} base URL(s)...{RESET}")
    for base_url in base_urls:
        urls_to_test.extend(generate_url_variations(base_url, payloads))
    if not urls_to_test:
        print(f"{RED}Error: Failed to generate any URLs to test.{RESET}")
        sys.exit(1)
    logging.info(f"{CYAN}[info] Total URLs/Variations to test: {len(urls_to_test)}{RESET}")
    # ----------------------------- #

    # Validate encoding times
    if args.encoding < 0:
        print(f"{RED}Error: Encoding times cannot be negative.{RESET}")
        sys.exit(1)

    # Validate threads
    if args.threads < 1:
        print(f"{RED}Error: Number of threads must be at least 1.{RESET}")
        sys.exit(1)

    # Validate timeout
    if args.time_sec < 1:
        print(f"{RED}Error: Timeout must be at least 1 second.{RESET}")
        sys.exit(1)

    # Display Chrome version (now done silently by get_chrome_version)
    # chrome_version = get_chrome_version()
    # print(f"{CYAN}Chrome Version: {chrome_version}{RESET}\\n\")
    get_chrome_version() # Run detection, logs warning if N/A
    print("\n") # Add a newline after detection attempt

    # ---- WAF Detection ----
    first_url = urls_to_test[0] # Use the first URL for WAF check
    detect_waf(first_url, args.proxy)
    # ---------------------

    logging.info(f"{CYAN}[info] Scan Starting...{RESET}")

    # Open output file
    try:
        output_file = open(args.output, 'w')
    except Exception as e:
        print(f"{RED}Error: Could not open output file '{args.output}': {e}{RESET}")
        sys.exit(1)

    # Generate output base name for HTML report (remove extension)
    output_base = os.path.splitext(args.output)[0]

    # Start scanning
    try:
        test_xss(
            urls_to_scan=urls_to_test, # Pass the expanded list
            payloads_to_test=payloads,
            proxies=args.proxy,
            encode_times=args.encoding,
            num_threads=min(args.threads, len(urls_to_test)), # Adjust threads based on variations
            timeout=args.time_sec,
            output_file=output_file,
            output_base=output_base
        )
    finally:
        output_file.close()
        cleanup_selenium()

def detect_waf(url, proxy_url=None):
    """Performs basic checks to detect common WAFs."""
    test_payload = "<script>alert('WAF-Test')</script>\"'><img src=x onerror=alert(1)>"
    test_url = f"{url.split('?')[0]}?waf_test={test_payload}" # Use a clean param
    headers = {
        'User-Agent': random.choice(USER_AGENTS) # Use random user agent
    }
    session = create_session(proxy_url)
    detected_waf = None

    try:
        response = session.get(test_url, headers=headers, timeout=10)
        status = response.status_code
        resp_headers = response.headers
        resp_body = response.text.lower()

        # Cloudflare
        if 'cf-ray' in resp_headers or 'cloudflare' in resp_headers.get('server', '').lower() or '>cloudflare</a>' in resp_body:
            detected_waf = "Cloudflare"
        # Akamai
        elif 'akamai' in resp_headers.get('server', '').lower() or 'x-akamai' in resp_headers or 'akamaighost' in resp_headers.get('server', '').lower():
            detected_waf = "Akamai"
        # Generic Block (e.g., 403 Forbidden often indicates WAF/filtering)
        elif status == 403:
            detected_waf = "Generic Block (403 Forbidden)"
        # Add more specific checks here if needed (AWS WAF, Imperva, etc.)

        if detected_waf:
            logging.warning(f"{RED}[!] WAF Detected: {detected_waf} - Scan results might be affected.{RESET}")
        else:
            logging.info(f"{GREEN}[info] No obvious WAF detected in initial check.{RESET}")

    except requests.exceptions.RequestException as e:
        logging.warning(f"{RED}[!] WAF detection request failed: {e}{RESET}")
    except Exception as e:
        logging.warning(f"{RED}[!] Error during WAF detection: {e}{RESET}")

if __name__ == "__main__":
    main()
