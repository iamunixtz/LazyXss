import argparse
import logging
import os
import sys
import time
import urllib.parse
import signal
import random
import asyncio
import aiohttp
from colorama import Fore, Style
from playwright.async_api import async_playwright
import subprocess
from playwright._impl._errors import TargetClosedError
import aiofiles
from concurrent.futures import ThreadPoolExecutor
import math
import html

# ANSI escape codes for colors
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
GREEN = "\033[92m"
RESET = "\033[0m"

BANNER = r"""
 __         ______     ______     __  __     __  __     ______     ______    
/\ \       /\  __ \   /\___  \   /\ \_\ \   /\_\_\_\   /\  ___\   /\  ___\   
\ \ \____  \ \  __ \  \/_/  /__  \ \____ \  \/_/\_\/_  \ \___  \  \ \___  \  
 \ \_____\  \ \_\ \_\   /\_____\  \/\_____\   /\_\/\_\  \/\_____\  \/\_____\ 
  \/_____/   \/_/\/_/   \/_____/   \/_____/   \/_/\/_/   \/_____/   \/_____/ 
                                                                             
                               Created By iamunixtz 
"""

# Configure logging with reduced verbosity
logging.basicConfig(
    level=logging.WARNING,
    format='[%(asctime)s] [%(levelname)s] [%(name)s] %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)

shutdown_flag = False
vulnerable_urls = []
interrupted_scan = False
USER_AGENTS = [
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:89.0) Gecko/20100101 Firefox/89.0",
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.1.1 Safari/605.1.15",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.114 Safari/537.36",
    "Mozilla/5.0 (iPhone; CPU iPhone OS 14_6 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/14.0 Mobile/15E148 Safari/604.1",
    "Mozilla/5.0 (Linux; Android 11; SM-G991B) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.120 Mobile Safari/537.36"
]

GITHUB_REPO_URL = "https://github.com/iamunixtz/LazyXss.git"

# --- Signal Handling ---
def signal_handler(sig, frame):
    global shutdown_flag, interrupted_scan
    if not shutdown_flag:
        logging.getLogger('main').warning("[!] Interrupt detected. Do you want to quit the tool? [y/n]: ")
        shutdown_flag = True
        while True:
            try:
                choice = input().lower()
                if choice in ["y", "yes"]:
                    logging.getLogger('main').warning("Exiting...")
                    interrupted_scan = True
                    # Generate report before exiting
                    if vulnerable_urls:
                        output_base = os.path.splitext(args.output)[0]
                        generate_html_report(output_base, -1, len(vulnerable_urls), -1, -1, interrupted=True)
                    os._exit(0)
                elif choice in ["n", "no"]:
                    logging.getLogger('main').info("Resuming...")
                    shutdown_flag = False
                    break
                else:
                    logging.getLogger('main').warning("Please enter 'y' or 'n': ")
            except EOFError:
                logging.getLogger('main').warning("Exiting due to EOF...")
                os._exit(0)

signal.signal(signal.SIGINT, signal_handler)

# --- Utility Functions ---
def print_colored_box(text, box_width=90, color=CYAN):
    lines = text.strip('\n').split('\n')
    print(f"{color}┌{'─'*(box_width-2)}┐{RESET}")
    for line in lines:
        clean_line = line.rstrip()
        if len(clean_line) > box_width - 4:
            clean_line = clean_line[:box_width - 7] + "..."
        print(f"{color}│ {clean_line.ljust(box_width - 4)} │{RESET}")
    print(f"{color}└{'─'*(box_width-2)}┘{RESET}")

def print_colored_prompt_box(prompt_lines, input_prompt, box_width=45, color=YELLOW):
    print(f"{color}┌{'─'*(box_width-2)}┐{RESET}")
    for line in prompt_lines:
        clean_line = line.rstrip()
        if len(clean_line) > box_width - 4:
            clean_line = clean_line[:box_width - 7] + "..."
        print(f"{color}│ {clean_line.ljust(box_width - 4)} │{RESET}")
    clean_prompt = input_prompt.rstrip()
    if len(clean_prompt) > box_width - 4:
        clean_prompt = clean_prompt[:box_width - 7] + "..."
    print(f"{color}│ {clean_prompt.ljust(box_width - 4)} │{RESET}")
    print(f"{color}└{'─'*(box_width-2)}┘{RESET}")
    user_input = input("Enter option: ").strip()
    return user_input

def encode_payload(payload, encode_times):
    for _ in range(encode_times):
        payload = urllib.parse.quote(payload)
    return payload

async def load_file_contents(file_path):
    async with aiofiles.open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
        lines = await f.readlines()
        return [line.strip() for line in lines if line.strip()]

# --- Async HTTP Reflection Check ---
async def check_reflection(session, url, payload, timeout, retries=2):
    for attempt in range(retries):
        try:
            async with session.get(url, timeout=timeout) as resp:
                text = await resp.text()
                return payload in text
        except Exception:
            if attempt == retries - 1:
                return False
            await asyncio.sleep(2 ** attempt)
    return False

async def bulk_reflection_filter(urls, payloads, timeout, proxy=None, concurrency=200):
    reflected = []
    connector = aiohttp.TCPConnector(limit=concurrency)
    headers = {'User-Agent': random.choice(USER_AGENTS)}
    async with aiohttp.ClientSession(connector=connector, headers=headers) as session:
        tasks = []
        for url in urls:
            for payload in payloads:
                encoded = encode_payload(payload, 0)
                test_url = f"{url}{encoded}"
                tasks.append(asyncio.create_task(check_reflection(session, test_url, payload, timeout)))
        results = await asyncio.gather(*tasks, return_exceptions=True)
        idx = 0
        for url in urls:
            for payload in payloads:
                if isinstance(results[idx], bool) and results[idx]:
                    reflected.append((url, payload))
                idx += 1
    return reflected

# --- Async Playwright XSS Check ---
async def check_xss_with_playwright(context, url, payloads, timeout):
    results = []
    page = await context.new_page()
    await page.route("**/*.{jpg,png,gif,svg,woff,woff2,css}", lambda route: asyncio.create_task(route.abort()))
    for payload in payloads:
        if shutdown_flag:
            break
        full_url = f"{url}{payload}"
        alerted = False
        alert_text = None
        async def on_dialog(dialog):
            nonlocal alerted, alert_text
            alerted = True
            alert_text = dialog.message
            try:
                await dialog.dismiss()
            except TargetClosedError:
                pass
            except Exception:
                pass
        page.on("dialog", on_dialog)
        try:
            await page.goto(full_url, timeout=timeout*1000)
            await page.wait_for_timeout(300)
        except Exception:
            pass
        results.append((alerted, payload, alert_text if alerted else None))
    await page.close()
    return results

# --- Main Async Scanning Logic ---
async def async_scan(base_urls, payloads, http_timeout, browser_timeout, concurrency, report_file):
    payloads = list(set(payloads))  # Deduplicate payloads
    reflected = await bulk_reflection_filter(base_urls, payloads, http_timeout, concurrency=200)
    if not reflected:
        logging.getLogger('reflection').warning("No reflected payloads found. Exiting.")
        return
    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=True,
            args=[
                '--disable-gpu',
                '--no-sandbox',
                '--disable-dev-shm-usage',
                '--disable-extensions',
                '--disable-images'
            ]
        )
        context = await browser.new_context(
            java_script_enabled=True,
            bypass_csp=True,
            viewport={'width': 1280, 'height': 720}
        )
        sem = asyncio.Semaphore(concurrency)
        tasks = []
        for url, payload in reflected:
            tasks.append(asyncio.create_task(async_xss_task(context, url, payload, browser_timeout, sem)))
        await asyncio.gather(*tasks)
        await context.close()
        await browser.close()
    if vulnerable_urls:
        async with aiofiles.open('result.txt', 'w', encoding='utf-8') as f:
            for vuln in vulnerable_urls:
                await f.write(f"{vuln[0]}\n")
        logging.getLogger('main').info("Vulnerabilities saved to result.txt")

async def log_vulnerability(full_url, is_vuln, payload, param=None):
    if is_vuln:
        line = f"{GREEN}[+] {full_url} [VULN]{RESET}"
        line_plain = f"[+] {full_url} [VULN]"
        vulnerable_urls.append((full_url, payload, param))
    else:
        line = f"{RED}[-] {full_url} [NOT VULN]{RESET}"
        line_plain = f"[-] {full_url} [NOT VULN]"
    print(line)
    async with aiofiles.open("scan.log", "a", encoding="utf-8") as logf:
        await logf.write(f"{line_plain}\n")

async def async_xss_task(context, url, payload, timeout, sem):
    async with sem:
        results = await check_xss_with_playwright(context, url, [payload], timeout)
        for is_vuln, payload_used, _ in results:
            param = None
            if is_vuln:
                try:
                    parsed_url = urllib.parse.urlparse(url + payload_used)
                    query_params = urllib.parse.parse_qs(parsed_url.query)
                    for p, v in query_params.items():
                        if payload_used in v:
                            param = p
                            break
                except:
                    pass
            full_url = f"{url}{payload_used}"
            await log_vulnerability(full_url, is_vuln, payload_used, param=param)

def generate_html_report(output_base, total_urls, total_vuln, total_non_vuln, time_taken, interrupted=False):
    global vulnerable_urls
    items_per_page = 10

    if not vulnerable_urls:
        logging.getLogger('main').info("No vulnerabilities found, skipping HTML report generation.")
        return

    total_pages = math.ceil(len(vulnerable_urls) / items_per_page)
    if total_pages == 0:
        total_pages = 1

    css_styles = """
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
  overflow-x: auto;
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

#particles-js {
  position: fixed;
  width: 100%;
  height: 100%;
  top: 0;
  left: 0;
  z-index: 1;
  opacity: 0.3;
}

header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 0;
  border-bottom: 1px solid var(--border-color);
  margin-bottom: 1.5rem;
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
    height: 36px;
    vertical-align: middle;
}

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

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1.5rem;
  margin-bottom: 2rem;
}

.metric-card {
  background-color: rgba(30, 41, 59, 0.5);
  border-radius: 0.5rem;
  padding: 1.25rem;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--border-color);
}

.metric-card.cyan-border { border-color: rgba(6, 182, 212, 0.3); }
.metric-card.red-border { border-color: rgba(239, 68, 68, 0.3); }
.metric-card.green-border { border-color: rgba(16, 185, 129, 0.3); }
.metric-card.blue-border { border-color: rgba(59, 130, 246, 0.3); }

.metric-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 0.75rem;
  font-size: 0.875rem;
  color: var(--text-secondary);
}

.metric-value {
  font-size: 1.75rem;
  font-weight: bold;
  margin-bottom: 0.25rem;
  color: var(--text-primary);
  font-family: 'JetBrains Mono', monospace;
}

.metric-detail {
  font-size: 0.75rem;
  color: var(--text-muted);
}

.glow-effect {
  position: absolute;
  bottom: -2rem;
  right: -2rem;
  height: 5rem;
  width: 5rem;
  border-radius: 50%;
  opacity: 0.15;
  filter: blur(12px);
}

.glow-effect.cyan { background: radial-gradient(circle, var(--cyan) 0%, transparent 70%); }
.glow-effect.red { background: radial-gradient(circle, var(--red) 0%, transparent 70%); }
.glow-effect.green { background: radial-gradient(circle, var(--green) 0%, transparent 70%); }
.glow-effect.blue { background: radial-gradient(circle, var(--blue) 0%, transparent 70%); }

.vuln-list {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.vuln-item {
  display: flex;
  gap: 0.75rem;
  padding: 0.75rem 1rem;
  border-radius: 0.375rem;
  background-color: rgba(30, 41, 59, 0.5);
  border: 1px solid var(--border-color);
  align-items: flex-start;
}

.vuln-icon {
  padding-top: 0.125rem;
}

.vuln-content {
  flex: 1;
  word-break: break-all;
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
  margin-top: 0.125rem;
  line-height: 1.4;
}

.vuln-data a {
    color: var(--cyan);
    text-decoration: none;
}

.vuln-data a:hover {
    text-decoration: underline;
}

.pagination {
    display: flex;
    justify-content: center;
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
    margin-left: -1px;
    line-height: 1.25;
    color: var(--cyan);
    background-color: var(--bg-secondary);
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
    color: #fff;
    background-color: var(--cyan);
    border-color: var(--cyan);
}

.page-item.disabled .page-link {
    color: var(--text-muted);
    pointer-events: none;
    background-color: var(--bg-secondary);
    border-color: var(--border-color);
    opacity: 0.6;
}

footer {
  text-align: center;
  margin-top: 3rem;
  padding: 1.5rem 1rem;
  font-size: 0.875rem;
  color: var(--text-muted);
  border-top: 1px solid var(--border-color);
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 1rem;
}

.social-links {
    display: flex;
    gap: 1.5rem;
}

.social-links a {
    color: var(--text-secondary);
    transition: color 0.2s;
}

.social-links a:hover {
    color: var(--cyan);
}

@keyframes pulse {
  0%, 100% { opacity: 0.1; }
  50% { opacity: 0.2; }
}

.glow-effect {
    animation: pulse 3s infinite ease-in-out;
}

@import url('https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    """

    js_scripts = """
<script src="https://cdn.jsdelivr.net/npm/particles.js@2.0.0/particles.min.js"></script>
<script src="https://unpkg.com/lucide@latest/dist/umd/lucide.min.js"></script>
<script>
  lucide.createIcons();
  particlesJS('particles-js', {
    particles: {
      number: { value: 80, density: { enable: true, value_area: 800 } },
      color: { value: ['#06b6d4', '#3b82f6', '#a855f7'] },
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

    for page_num in range(total_pages):
        current_page = page_num + 1
        start_idx = page_num * items_per_page
        end_idx = start_idx + items_per_page
        page_vulnerabilities = vulnerable_urls[start_idx:end_idx]

        vuln_list_html = ""
        if page_vulnerabilities:
            for idx, (url, payload, param) in enumerate(page_vulnerabilities, start=start_idx + 1):
                safe_url = html.escape(url)
                safe_payload = html.escape(payload)
                param_html = f"""
                <div style="margin-top: 0.5rem;">
                    <div class="vuln-label">Parameter:</div>
                    <div class="vuln-data">{html.escape(param)}</div>
                </div>
                """ if param else ""
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
            vuln_list_html = "<p style='color: var(--text-secondary); text-align: center;'>No vulnerabilities on this page.</p>"

        pagination_html = ""
        if total_pages > 1:
            pagination_html += '<nav aria-label="Vulnerability pages"><ul class="pagination">'
            prev_disabled = ' disabled' if current_page == 1 else ''
            prev_href = f'href="{output_base}_page_{current_page - 1}.html"' if current_page > 1 else 'href="#"'
            pagination_html += f'<li class="page-item{prev_disabled}"><a class="page-link" {prev_href} aria-label="Previous"><span aria-hidden="true">&laquo;</span> Prev</a></li>'
            for i in range(total_pages):
                page_link_num = i + 1
                active = ' active' if page_link_num == current_page else ''
                pagination_html += f'<li class="page-item{active}"><a class="page-link" href="{output_base}_page_{page_link_num}.html">{page_link_num}</a></li>'
            next_disabled = ' disabled' if current_page == total_pages else ''
            next_href = f'href="{output_base}_page_{current_page + 1}.html"' if current_page < total_pages else 'href="#"'
            pagination_html += f'<li class="page-item{next_disabled}"><a class="page-link" {next_href} aria-label="Next">Next <span aria-hidden="true">&raquo;</span></a></li>'
            pagination_html += '</ul></nav>'

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
    <header>
      <div class="logo">
        <i data-lucide="hexagon" class="icon-cyan icon-medium"></i>
        <span class="logo-text">LazyXSS Scan Report{' (' + RED + 'INTERRUPTED' + RESET + ')' if interrupted else ''}</span>
      </div>
      <a href="https://buymeacoffee.com/iamunixtz" target="_blank" class="bmc-button">
        <img src="https://img.buymeacoffee.com/button-api/?text=Buy me a coffee&emoji=&slug=iamunixtz&button_colour=06b6d4&font_colour=0f172a&font_family=Inter&outline_colour=000000&coffee_colour=FFDD00" alt="Buy Me A Coffee" >
      </a>
    </header>
    <main>
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
      <div class="card">
        <div class="card-header">
          <div class="card-title">
            <i data-lucide="bug" class="icon-red"></i>
            Detected Vulnerabilities
          </div>
          {'<div class="card-actions"><span class="badge red">Scan Interrupted</span></div>' if interrupted else ''}
        </div>
        <div class="card-content">
          <div class="vuln-list">
            {vuln_list_html}
          </div>
          {pagination_html}
        </div>
      </div>
    </main>
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
        report_filename = f"{output_base}_page_{current_page}.html"
        try:
            with open(report_filename, 'w', encoding='utf-8') as f:
                f.write(html_content)
            print(f"\n{GREEN}Generated HTML report: {report_filename}{RESET}")
        except IOError as e:
            print(f"\n{RED}Error writing HTML report '{report_filename}': {e}{RESET}")

# --- CLI and Entrypoint ---
def main():
    global args
    parser = argparse.ArgumentParser(description="Async XSS Scanner with Playwright", add_help=True)
    parser.add_argument('-u', '--url', type=str, help="Specify a single URL to test.")
    parser.add_argument('-f', '--file', type=str, help="Specify a file with URLs.")
    parser.add_argument('-p', '--payloads', type=str, default="payloads.txt", help="Payload file (default: payloads.txt).")
    parser.add_argument('-t', '--concurrency', type=int, default=50, help="Number of concurrent Playwright tasks (default: 50).")
    parser.add_argument('-T', '--timeout', type=float, default=1.0, help="Timeout in seconds for Playwright checks (default: 1.0).")
    parser.add_argument('--http-timeout', type=float, default=5.0, help="Timeout in seconds for HTTP reflection checks (default: 5.0).")
    parser.add_argument('-o', '--output', type=str, default='result.txt', help="Output file for vulnerable URLs (default: result.txt).")
    args = parser.parse_args()

    os.system('cls' if os.name == 'nt' else 'clear')
    print_colored_box(BANNER, box_width=90, color=CYAN)
    async def run_scan():
        if args.url:
            base_urls = [args.url]
        elif args.file:
            base_urls = await load_file_contents(args.file)
        else:
            prompt_lines = [
                "Choose input method:",
                "  1) Enter single URL",
                "  2) Enter file path ",
                "  3) Update",
                "  4) Exit",
            ]
            choice = print_colored_prompt_box(prompt_lines, "Enter choice (1, 2, 3, or 4):", box_width=45, color=YELLOW)
            if choice == '1':
                url = input(f"{YELLOW}Enter the target URL: {RESET}").strip()
                if not url:
                    logging.getLogger('input').error("No URL entered. Exiting.")
                    sys.exit(1)
                base_urls = [url]
            elif choice == '2':
                file_path = input(f"{YELLOW}Enter file path with URLs: {RESET}").strip()
                base_urls = await load_file_contents(file_path)
                if not base_urls:
                    logging.getLogger('input').error(f"No URLs loaded from file '{file_path}'. Exiting.")
                    sys.exit(1)
            elif choice == '3':
                print(f"{CYAN}Checking for updates from GitHub...{RESET}")
                try:
                    fetch_result = subprocess.run(["git", "fetch", GITHUB_REPO_URL], capture_output=True, text=True)
                    if fetch_result.returncode != 0:
                        print(f"{RED}Failed to fetch updates!{RESET}")
                        print(fetch_result.stderr)
                        sys.exit(1)
                    local = subprocess.run(["git", "rev-parse", "@"], capture_output=True, text=True)
                    remote = subprocess.run(["git", "rev-parse", "@{u}"], capture_output=True, text=True)
                    base = subprocess.run(["git", "merge-base", "@", "@{u}"], capture_output=True, text=True)
                    if local.returncode != 0 or remote.returncode != 0 or base.returncode != 0:
                        print(f"{RED}Could not determine update status!{RESET}")
                        sys.exit(1)
                    local_sha = local.stdout.strip()
                    remote_sha = remote.stdout.strip()
                    base_sha = base.stdout.strip()
                    if local_sha == remote_sha:
                        print(f"{GREEN}Already up to date!{RESET}")
                    elif local_sha == base_sha:
                        print(f"{YELLOW}Update available! Pulling latest changes...{RESET}")
                        pull_result = subprocess.run(["git", "pull", GITHUB_REPO_URL], capture_output=True, text=True)
                        if pull_result.returncode == 0:
                            print(f"{GREEN}Update successful!{RESET}")
                            print(pull_result.stdout)
                        else:
                            print(f"{RED}Update failed!{RESET}")
                            print(pull_result.stderr)
                    else:
                        print(f"{YELLOW}Local changes diverged from remote. Please resolve manually!{RESET}")
                except Exception as e:
                    print(f"{RED}Error checking for updates: {e}{RESET}")
                sys.exit(0)
            elif choice == '4':
                print(f"{YELLOW}Exiting...{RESET}")
                sys.exit(0)
            else:
                logging.getLogger('input').error("Invalid choice. Please enter 1, 2, 3, or 4.")
                sys.exit(1)
        payloads = await load_file_contents(args.payloads)
        if not payloads:
            logging.getLogger('input').error(f"No valid payloads found in '{args.payloads}'.")
            sys.exit(1)
        start = time.time()
        await async_scan(base_urls, payloads, args.http_timeout, args.timeout, args.concurrency, args.output)
        end = time.time()
        output_base = os.path.splitext(args.output)[0]
        if not interrupted_scan:
            try:
                all_urls = await load_file_contents(args.file) if args.file else [args.url] if args.url else []
                total_urls = len(all_urls) if all_urls else len(vulnerable_urls)
                total_vuln = len(vulnerable_urls)
                total_non_vuln = max(total_urls - total_vuln, 0)
                time_taken = int(end - start)
                if vulnerable_urls:
                    generate_html_report(output_base, total_urls, total_vuln, total_non_vuln, time_taken, interrupted=False)
            except Exception as e:
                logging.getLogger('main').error(f"Error generating report: {e}")

    asyncio.run(run_scan())

if __name__ == "__main__":
    main()
