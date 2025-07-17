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
from requests.exceptions import SSLError
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
from selenium.common.exceptions import WebDriverException, NoAlertPresentException, TimeoutException
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
import re
import math
import html
import random
import socket

from lazyxss_browser_manager import BrowserManager

# ANSI escape codes for colors
GREEN = "\033[92m"
CYAN = "\033[96m"
RED = "\033[91m"
RESET = "\033[0m"

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(message)s')
# Suppress excessive retry messages from urllib3
logging.getLogger("urllib3").setLevel(logging.WARNING)

# Global semaphore to limit concurrent Selenium instances
# Initialized in main() based on args
selenium_semaphore = None

# Flag for graceful shutdown
shutdown_flag = threading.Event()

# Track vulnerable URLs for the report
vulnerable_urls = []

# Flag to indicate if scan was interrupted
interrupted_scan = False

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
    global vulnerable_urls, global_args, interrupted_scan # Need args for output base
    if not shutdown_flag.is_set():
        # Ensure prompt is on a new line without extra separators
        print("\nInterrupt detected. Do you want to quit the tool? [y/n]: ", end='', flush=True)
        shutdown_flag.set()
        # Don't cleanup selenium immediately, allow report generation first if quitting
        # cleanup_selenium()
        while True:
            try:
                choice = input().lower()
                if choice in ["y", "yes"]:
                    print("Exiting...")
                    interrupted_scan = True # Set flag for report
                    # --- Save Report on Exit --- #
                    if vulnerable_urls and global_args:
                        print("Attempting to save report for found vulnerabilities before exiting...")
                        try:
                            output_base = os.path.splitext(global_args.output)[0]
                            # Pass interrupted flag and only vuln count
                            generate_html_report(output_base, -1, len(vulnerable_urls), -1, -1, interrupted=True)
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

def generate_html_report(output_base, total_urls, total_vuln, total_non_vuln, time_taken, interrupted=False):
    """Generate the HTML report with the futuristic dashboard UI, including pagination.
       Handles interrupted scans gracefully.
    """
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
            for idx, (url, payload, param) in enumerate(page_vulnerabilities, start=start_idx + 1):
                safe_url = html.escape(url)
                safe_payload = html.escape(payload)
                param_html = ""
                if param:
                    safe_param = html.escape(param)
                    param_html = f"""
                    <div style="margin-top: 0.5rem;">
                        <div class="vuln-label">Parameter:</div>
                        <div class="vuln-data">{safe_param}</div>
                    </div>
                    """
                vuln_list_html += f"""
                <div class="vuln-item">
                  <div class="vuln-icon icon-red"><i data-lucide="shield-alert" class="icon-medium"></i></div>
                  <div class="vuln-content">
                      <div>
                          <div class="vuln-label">URL:</div>
                          <div class="vuln-data"><a href="{safe_url}" target="_blank">{safe_url}</a></div>
                      </div>
                      {param_html}
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

        # --- Conditionally generate metric cards for non-interrupted scans --- #
        non_vuln_card_html = ''
        duration_card_html = ''
        if not interrupted:
            non_vuln_card_html = f'''
        <div class="metric-card green-border">
                        <div class="metric-header">
            <div>Non-Vulnerable</div>
            <i data-lucide="shield-check" class="icon-green icon-medium"></i>
                        </div>
                        <div class="metric-value">{total_non_vuln}</div>
          <div class="metric-detail">URLs without confirmed XSS</div>
           <div class="glow-effect green"></div>
                    </div>'''
            duration_card_html = f'''
        <div class="metric-card cyan-border">
                        <div class="metric-header">
            <div>Scan Duration</div>
            <i data-lucide="clock" class="icon-cyan icon-medium"></i>
                        </div>
                        <div class="metric-value">{time_taken}s</div>
          <div class="metric-detail">Total time elapsed</div>
           <div class="glow-effect cyan"></div>
                    </div>'''
        # ------------------------------------------------------------------ #

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
          <span class=\"logo-text\">LazyXSS Scan Report{f' ({RED}INTERRUPTED{RESET})' if interrupted else ''}</span>
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
        {non_vuln_card_html}
        {duration_card_html}
      </div>

      <!-- Vulnerable URLs List -->
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <i data-lucide="bug" class="icon-red"></i>
            Detected Vulnerabilities
          </div>
          {f'<div class="card-actions"><span class="badge red">Scan Interrupted</span></div>' if interrupted else ''}
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
    """Print the usage manual instructions in a more structured format."""
    # Define column widths for alignment
    opt_width = 22
    desc_width = 55

    manual = (
        f"\n{GREEN}SYNOPSIS{RESET}\n"
        f"  python3 lazyxssX53x.py [OPTIONS]\n\n"
        f"{GREEN}DESCRIPTION{RESET}\n"
        f"  High-speed XSS scanner with HTTP reflection and Selenium verification.\n"
        f"  Tests all GET parameters in provided URLs and generates a futuristic\n"
        f"  HTML report if vulnerabilities are found.\n\n"
        f"{GREEN}OPTIONS{RESET}\n"
        f"  {'-u, --url':<{opt_width}} {'Specify a single URL to test.':<{desc_width}}\n"
        f"  {'-f, --file':<{opt_width}} {'Specify a file containing URLs (one per line).':<{desc_width}}\n"
        f"  {'-p, --payloads':<{opt_width}} {'Specify the payload file (default: payloads.txt).':<{desc_width}}\n"
        f"  {'-t, --threads':<{opt_width}} {'Number of concurrent URL processing threads (default: 20).':<{desc_width}}\n"
        f"  {'-e, --encoding':<{opt_width}} {'Number of times to URL-encode the payloads (default: 0).':<{desc_width}}\n"
        f"  {'-o, --output':<{opt_width}} {'Output file for vulnerable URLs (default: result.txt).':<{desc_width}}\n"
        f"  {'':<{opt_width}} {'HTML report uses this base name (e.g., result_page_1.html).':<{desc_width}}\n"
        f"  {'-T, --time-sec':<{opt_width}} {'Timeout in seconds for Selenium checks (default: 2).':<{desc_width}}\n"
        f"  {'--selenium-workers':<{opt_width}} {'Number of concurrent Selenium browser instances (default: 5).':<{desc_width}}\n"
        f"  {'':<{opt_width}} {'Increase cautiously based on system resources.':<{desc_width}}\n"
        f"  {'--proxy':<{opt_width}} {'Specify a proxy server (e.g., http://127.0.0.1:8080).':<{desc_width}}\n"
        f"  {'':<{opt_width}} {'(Note: Affects HTTP requests, not Selenium checks).':<{desc_width}}\n"
        f"  {'--http-timeout':<{opt_width}} {'Timeout in seconds for HTTP requests (connect & read) (default: 20).':<{desc_width}}\n"
        f"  {'-h, --help':<{opt_width}} {'Show this help message and exit.':<{desc_width}}\n\n"
        f"{GREEN}EXAMPLES{RESET}\n"
        f"  Scan a single URL (multiple parameters):\n"
        f"    python3 lazyxss.py -u \"http://test.com?q=test&debug=0\" -p pay.txt\n\n"
        f"  Scan multiple URLs from a file:\n"
        f"    python3 lazyxss.py -f urls.txt -p payloads.txt -o results.txt\n\n"
        f"  Scan using an HTTP Proxy:\n"
        f"    python3 lazyxss.py -f urls.txt --proxy http://127.0.0.1:8080\n\n"
        f"  Scan with increased Selenium concurrency:\n"
        f"    python3 lazyxss.py -f urls.txt -t 30 --selenium-workers 10\n"

    )
    # Update example commands to use correct script name
    manual = manual.replace("python3 lazyxss.py", f"python3 {os.path.basename(sys.argv[0])}")
    print(manual)

class CustomHelpAction(argparse.Action):
    """Custom help action that prints the usage manual and banner."""
    def __call__(self, parser, namespace, values, option_string=None):
        # Clear screen first
        os.system('cls' if os.name == 'nt' else 'clear')
        # Print banner FIRST
        print_banner()
        # Print custom manual SECOND
        print_usage_manual()
        # DO NOT print default help (parser.print_help() removed)
        parser.exit()

def load_file_contents(file_path):
    """Yield non-empty, stripped lines from a file."""
    if not os.path.isfile(file_path):
        logging.error(f"{RED}File '{file_path}' does not exist.{RESET}")
        return
    with open(file_path, 'r') as file:
        for line in file:
            stripped_line = line.strip()
            if stripped_line:
                yield stripped_line

def encode_payload(payload, encode_times):
    """Encode a payload multiple times using URL encoding."""
    encoded = payload
    for _ in range(encode_times):
        encoded = urllib.parse.quote(encoded)
    return encoded

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

def check_reflection(url, payload, session, http_timeout):
    """Check if payload is reflected with high accuracy, using specific timeout.
       Returns True if reflected, False if not reflected, None on network errors."""
    if shutdown_flag.is_set():
        return None # Indicate shutdown/cancellation
    try:
        # Explicitly set connect and read timeouts using a tuple
        response = session.get(url, timeout=(http_timeout, http_timeout))
        # Check for reflection based on the effective_payload derived from the URL
        # Need to unquote both the payload and response for comparison
        decoded_payload = urllib.parse.unquote(payload)
        decoded_response = urllib.parse.unquote(response.text)
        return decoded_payload in decoded_response # Returns True or False
    except requests.exceptions.ConnectTimeout:
        logging.warning(f"{RED}[!] Connection Timeout: {url} (Check host/firewall/network){RESET}")
        return None # Indicate network error
    except requests.exceptions.ReadTimeout:
        logging.warning(f"{RED}[!] Read Timeout ({http_timeout}s) during reflection check for: {url}{RESET}")
        logging.warning(f"{RED}    _ Reason: Connection established, but server did not send data in time. Server might be slow, overloaded, or a WAF delayed the response.{RESET}")
        return None # Indicate network error
    except requests.exceptions.SSLError:
        # Specific handling for SSL verification errors
        logging.warning(f"{RED}[!] SSL Certificate Verify Failed: {url} (Check system certs or target config){RESET}")
        return None # Indicate network error (SSL)
    except requests.exceptions.RequestException as e:
        logging.warning(f"{RED}[!] Request Exception during reflection check for {url}: {e}{RESET}")
        logging.warning(f"{RED}    _ Reason: General network issue (DNS, SSL, Proxy error, etc.). Check URL validity and network settings.{RESET}")
        return None # Indicate network error
    except Exception as e:
        # Keep generic error for unexpected issues
        logging.error(f"{RED}Unexpected error during reflection check for {url}: {e}{RESET}")
        return None # Indicate other error

def check_xss_with_selenium(driver, url, payloads, selenium_timeout):
    """High-speed, accurate Selenium check for XSS using WebDriverWait."""
    results = []
    wait_timeout = selenium_timeout # Use the full timeout specified by -T
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

### Logging and Worker Functions

def log_vulnerability(full_url, is_vuln, payload, output_file, param=None):
    """Log vulnerability status and write vulnerable URLs."""
    global vulnerable_urls
    status = f"{GREEN}[vuln]{RESET}" if is_vuln else f"{RED}[not vuln]{RESET}"
    message = f"{GREEN}[info]{RESET} {full_url} {status}"
    if is_vuln and param:
        message += f" (param: {param})"
    logging.info(message)
    if output_file and is_vuln and not shutdown_flag.is_set():
        output_file.write(f"{full_url}\n")
        output_file.flush()
        vulnerable_urls.append((full_url, payload, param))

def worker(browser_manager, url_queue, payloads, proxies, encode_times, http_timeout, selenium_timeout, output_file):
    """Worker function processes URLs from the queue."""
    session = create_session(proxies)
    browser = browser_manager.get_browser()
    try:
        while not url_queue.empty():
            if shutdown_flag.is_set():
                break
            base_url = url_queue.get()
            for payload in payloads:
                if shutdown_flag.is_set():
                    break

                full_url = f"{base_url}{payload}" # Simple append
                encoded_payload = encode_payload(payload, encode_times)
                full_encoded_url = f"{base_url}{encoded_payload}"

                # Perform reflection check
                reflected = check_reflection(full_encoded_url, payload, session, http_timeout)

                if reflected is True:
                    # If reflected, perform Selenium check
                    results = check_xss_with_selenium(browser, full_encoded_url, [payload], selenium_timeout)
                    for is_vuln, payload_used, _ in results:
                        param = None
                        if is_vuln:
                            try:
                                parsed_url = urllib.parse.urlparse(full_encoded_url)
                                query_params = urllib.parse.parse_qs(parsed_url.query)
                                for p, v in query_params.items():
                                    if payload in v:
                                        param = p
                                        break
                            except:
                                pass
                        log_vulnerability(full_encoded_url, is_vuln, payload_used, output_file, param=param)
                elif reflected is False:
                    # Only log non-vuln if request succeeded but no reflection
                    log_vulnerability(full_encoded_url, False, payload, output_file)
            url_queue.task_done()
    finally:
        browser_manager.return_browser(browser)

def test_xss(base_urls, payloads_to_test, proxies, encode_times, num_threads, http_timeout, selenium_timeout, output_file, output_base, num_browsers):
    """Test multiple base URLs against multiple payloads for XSS."""
    global vulnerable_urls, interrupted_scan
    start_time = time.time()

    url_generator = iter(base_urls)
    total_payloads = len(payloads_to_test)
    # The total number of URLs is unknown if it's a generator, so we can't estimate total tests.

    logging.info(f"{CYAN}[info] Starting scan...{RESET}")

    browser_manager = BrowserManager(num_browsers=num_browsers, selenium_timeout=selenium_timeout)
    url_queue = queue.Queue()

    # To avoid loading all URLs into the queue at once, we can feed the queue in a separate thread.
    def queue_feeder(url_gen, q):
        for url in url_gen:
            q.put(url)

    feeder_thread = threading.Thread(target=queue_feeder, args=(url_generator, url_queue))
    feeder_thread.start()

    threads = []
    for _ in range(num_threads):
        thread = threading.Thread(target=worker, args=(
            browser_manager, url_queue, payloads_to_test, proxies, encode_times, http_timeout, selenium_timeout, output_file
        ))
        thread.start()
        threads.append(thread)

    try:
        # Wait for all URLs to be processed
        url_queue.join()
        # Signal shutdown to threads
        shutdown_flag.set()
    except (KeyboardInterrupt, SystemExit):
        shutdown_flag.set()
        interrupted_scan = True

    for thread in threads:
        thread.join()

    feeder_thread.join()
    browser_manager.close_all_browsers()

    end_time = time.time()
    time_taken = int(end_time - start_time)
    total_vuln = len(vulnerable_urls)
    # Since we don't know the total number of URLs, we can't calculate non-vulnerable or total tests.

    # Generate HTML report
    if vulnerable_urls:
        report_name_base = f"{output_base}_page_1.html"
        print(f"\n{GREEN}Generated HTML report (check {report_name_base} ...){RESET}")
        generate_html_report(output_base, -1, total_vuln, -1, time_taken, interrupted=interrupted_scan)
    elif not interrupted_scan:
        print(f"\n{CYAN}Scan completed. No vulnerabilities found.{RESET}")

    # Print Summary Table (only if not interrupted)
    if not interrupted_scan:
        col1_width = 25
        col2_width = 12 # Adjusted for potentially larger numbers
        total_width = col1_width + col2_width + 3

        print("\n" + "╔" + "═"*col1_width + "╦" + "═"*col2_width + "╗")
        print(f"║ {CYAN}{'Scan Summary':^{total_width-4}} {RESET} ║")
        print("╠" + "═"*col1_width + "╬" + "═"*col2_width + "╣")
        print(f"║ {'Metric':<{col1_width-2}} ║ {'Value':<{col2_width-2}} ║")
        print("╠" + "═"*col1_width + "╬" + "═"*col2_width + "╣")
        print(f"║ {'Payloads Loaded:':<{col1_width-2}} ║ {total_payloads:<{col2_width-2}} ║")

        vuln_val_str = str(total_vuln)
        vuln_val_display = f"{GREEN}{total_vuln}{RESET}" if total_vuln > 0 else vuln_val_str
        padding_needed = col2_width - 2 - len(vuln_val_str)
        print(f"║ {'Vulnerabilities Found:':<{col1_width-2}} ║ {vuln_val_display}{' '*padding_needed} ║")

        time_str = f"{time_taken} sec"
        padding_needed_time = col2_width - 2 - len(time_str)
        print(f"║ {'Time Taken:':<{col1_width-2}} ║ {time_str}{' '*padding_needed_time} ║")

        print("╚" + "═"*col1_width + "╩" + "═"*col2_width + "╝")

# Store args globally for access in worker threads if needed (e.g., for chrome_path)
# Alternatively, pass args down through function calls
global_args = None

### Main Function

def recon_urls(urls, http_timeout, proxy):
    """
    Performs a reconnaissance scan on a list of URLs to find parameters
    that reflect their input.
    """
    logging.info(f"{CYAN}[info] Starting reconnaissance scan...{RESET}")
    reflecting_urls = []
    session = create_session(proxy)

    for url in urls:
        try:
            parsed_url = urllib.parse.urlparse(url)
            params = urllib.parse.parse_qs(parsed_url.query)
            if not params:
                logging.info(f"{CYAN}[info] Skipping URL with no parameters: {url}{RESET}")
                continue

            for param, values in params.items():
                test_payload = "lazyxss"
                # Create a copy of the params, replace the value of the current param
                test_params = params.copy()
                test_params[param] = test_payload

                # Rebuild the URL with the test payload
                new_query = urllib.parse.urlencode(test_params, doseq=True)
                test_url = parsed_url._replace(query=new_query).geturl()

                # Check for reflection
                if check_reflection(test_url, test_payload, session, http_timeout):
                    logging.info(f"{GREEN}[reflecting] {url} (parameter: {param}){RESET}")
                    if url not in reflecting_urls:
                        reflecting_urls.append(url)
                    # Once one reflecting param is found, we can move to the next URL
                    break
        except Exception as e:
            logging.error(f"{RED}Error during recon for {url}: {e}{RESET}")

    output_filename = "reflecting_urls.txt"
    with open(output_filename, "w") as f:
        for url in reflecting_urls:
            f.write(url + "\n")

    logging.info(f"\n{GREEN}Reconnaissance complete. Found {len(reflecting_urls)} reflecting URLs.{RESET}")
    logging.info(f"{GREEN}A list of these URLs has been saved to {output_filename}{RESET}")

def main():
    """Main function: parse arguments, display banner, and start scanning."""
    global global_args # Declare modification of globals

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
    parser.add_argument('--selenium-workers', type=int, default=5, help="Number of concurrent Selenium instances (default: 5).")
    parser.add_argument('--proxy', type=str, help="Proxy server URL (e.g., http://127.0.0.1:8080).")
    parser.add_argument('--http-timeout', type=int, default=20, help="Timeout in seconds for HTTP requests (connect & read) (default: 20).")
    parser.add_argument('--recon', action='store_true', help="Perform a preliminary reflection check to find promising URLs.")

    args = parser.parse_args()
    global_args = args # Store args globally

    # Display banner
    print_banner()

    # ---- Recon Mode ----
    if args.recon:
        urls_for_recon = []
        if args.url:
            urls_for_recon.append(args.url)
        elif args.file:
            urls_for_recon = list(load_file_contents(args.file))

        if not urls_for_recon:
            print(f"{RED}Error: No URLs provided for reconnaissance.{RESET}")
            sys.exit(1)

        recon_urls(urls_for_recon, args.http_timeout, args.proxy)
        sys.exit(0)

    # ---- Refined Startup Logging ----
    if args.url:
        logging.info(f"{CYAN}[info] Target URL: {args.url}{RESET}")
    else:
        logging.info(f"{CYAN}[info] Target File: {args.file}{RESET}")
    logging.info(f"{CYAN}[info] Payload File: {args.payloads}{RESET}")
    # Load payloads early to get count
    payloads = list(load_file_contents(args.payloads))
    if not payloads:
        print(f"{RED}Error: No valid payloads found in '{args.payloads}'.{RESET}")
        sys.exit(1)
    logging.info(f"{CYAN}[info] Total Payloads: {len(payloads)}{RESET}")

    # Load URLs
    if args.url:
        base_urls = [args.url]
    else:
        base_urls = load_file_contents(args.file)

    # --- DNS Pre-check (Moved Here) --- #
    try:
        first_target_url = next(iter(base_urls), None)
        if not first_target_url:
             raise ValueError("URL list is empty before DNS check.")
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

    # --- Create list of tests (Base URL + Payload combinations) --- #
    # This is illustrative - the actual combination happens in the worker now
    # total_tests_planned = len(base_urls) * len(payloads)
    # logging.info(f"{CYAN}[info] Total Tests Planned: {total_tests_planned}{RESET}")
    # ------------------------------------------------------------ #

    # Validate threads
    if args.threads < 1:
        print(f"{RED}Error: Number of threads must be at least 1.{RESET}")
        sys.exit(1)

    # Validate timeout
    if args.time_sec < 1:
        print(f"{RED}Error: Timeout must be at least 1 second.{RESET}")
        sys.exit(1)

    print("\n") # Add a newline after detection attempt

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
            base_urls=base_urls,
            payloads_to_test=payloads,
            proxies=args.proxy,
            encode_times=args.encoding,
            num_threads=args.threads,
            http_timeout=args.http_timeout, # Pass HTTP timeout
            selenium_timeout=args.time_sec, # Pass Selenium timeout (existing -T)
            output_file=output_file,
            output_base=output_base,
            num_browsers=args.selenium_workers
        )
    finally:
        output_file.close()

if __name__ == "__main__":
    main()
