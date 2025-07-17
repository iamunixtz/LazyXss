import queue
import threading
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from webdriver_manager.chrome import ChromeDriverManager
from selenium.webdriver.chrome.options import Options
import tempfile

class BrowserManager:
    def __init__(self, num_browsers, selenium_timeout):
        self.num_browsers = num_browsers
        self.selenium_timeout = selenium_timeout
        self.browser_pool = queue.Queue(maxsize=num_browsers)
        self.lock = threading.Lock()
        self._initialize_browsers()

    def _create_browser(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-extensions")
        chrome_options.add_argument("--blink-settings=imagesEnabled=false")
        chrome_options.add_argument("--disable-component-update")
        chrome_options.add_argument("--disable-background-networking")
        chrome_options.add_experimental_option('excludeSwitches', ['enable-logging'])
        chrome_options.set_capability("unhandledPromptBehavior", "dismiss")

        user_data_dir = tempfile.mkdtemp()
        chrome_options.add_argument(f"--user-data-dir={user_data_dir}")

        service = Service(ChromeDriverManager().install())
        driver = webdriver.Chrome(service=service, options=chrome_options)
        driver.set_page_load_timeout(self.selenium_timeout)
        driver.user_data_dir = user_data_dir
        return driver

    def _initialize_browsers(self):
        for _ in range(self.num_browsers):
            self.browser_pool.put(self._create_browser())

    def get_browser(self):
        return self.browser_pool.get()

    def return_browser(self, browser):
        self.browser_pool.put(browser)

    def close_all_browsers(self):
        while not self.browser_pool.empty():
            browser = self.browser_pool.get()
            browser.quit()
            # Clean up the user data directory
            try:
                import shutil
                shutil.rmtree(browser.user_data_dir)
            except (AttributeError, FileNotFoundError, OSError):
                pass
