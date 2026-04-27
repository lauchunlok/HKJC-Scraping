"""
Shared utilities for HKJC web scrapers.

- Modern Selenium WebDriver setup with webdriver-manager
- Thread-local driver reuse (avoids spinning up a new browser per URL)
- Retry decorator for transient failures
"""
import time
import threading
import functools

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

from config import MAX_RETRIES, RETRY_DELAY, setup_logging

logger = setup_logging("scraper_utils")

# Thread-local storage for driver reuse
_thread_local = threading.local()

# Lock for driver creation (prevents concurrent chromedriver startups from conflicting)
_driver_lock = threading.Lock()

# Cache chromedriver path (resolved once, reused by all threads)
_chromedriver_path = None


def _get_chromedriver_path() -> str:
    """Get the chromedriver path, installing if needed. Thread-safe."""
    global _chromedriver_path
    if _chromedriver_path is None:
        with _driver_lock:
            if _chromedriver_path is None:
                _chromedriver_path = ChromeDriverManager().install()
                logger.info("Chromedriver installed at: %s", _chromedriver_path)
    return _chromedriver_path


def get_driver() -> webdriver.Chrome:
    """
    Get or create a headless Chrome driver for the current thread.

    Uses thread-local storage so each worker thread reuses its own
    browser instance instead of creating a new one per URL.
    """
    driver = getattr(_thread_local, "driver", None)
    if driver is None:
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--window-size=1920,1080")
        chrome_options.add_argument(
            "user-agent=Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )

        chromedriver_path = _get_chromedriver_path()

        # Retry driver creation with lock to avoid concurrent chromedriver
        # service startup failures
        for attempt in range(3):
            try:
                with _driver_lock:
                    service = Service(chromedriver_path)
                    driver = webdriver.Chrome(service=service, options=chrome_options)
                break
            except Exception as e:
                if attempt < 2:
                    logger.warning(
                        "Driver creation attempt %d/3 failed: %s — retrying...",
                        attempt + 1, e,
                    )
                    time.sleep(2 * (attempt + 1))
                else:
                    raise

        _thread_local.driver = driver
        logger.debug("Created new Chrome driver for thread %s", threading.current_thread().name)
    return driver


def quit_driver():
    """Quit the thread-local driver if it exists."""
    driver = getattr(_thread_local, "driver", None)
    if driver is not None:
        try:
            driver.quit()
        except Exception:
            pass
        _thread_local.driver = None


def retry(max_retries: int = MAX_RETRIES, delay: float = RETRY_DELAY):
    """
    Decorator that retries a function on exception.

    Args:
        max_retries: Maximum number of retry attempts.
        delay: Seconds to wait between retries (doubles each attempt).
    """
    def decorator(func):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            last_exception = None
            for attempt in range(1, max_retries + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_retries:
                        wait = delay * (2 ** (attempt - 1))
                        logger.warning(
                            "%s attempt %d/%d failed: %s — retrying in %.1fs",
                            func.__name__, attempt, max_retries, e, wait,
                        )
                        # Reset the driver on failure in case it's in a bad state
                        quit_driver()
                        time.sleep(wait)
                    else:
                        logger.error(
                            "%s failed after %d attempts: %s",
                            func.__name__, max_retries, e,
                        )
            raise last_exception
        return wrapper
    return decorator
