from __future__ import annotations

import logging

from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.remote.webdriver import WebDriver
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from src.scraper.selenium_helpers import click_text, find_first, wait_for_any
from src.services.cookie_service import CookieService
from src.utils.settings import Settings


class HeidiLogin:
    def __init__(self, driver: WebDriver, settings: Settings, logger: logging.Logger):
        self.driver = driver
        self.settings = settings
        self.logger = logger
        self.cookies = CookieService(settings.heidi_cookie_path)

    def login(self) -> None:
        if self.cookies.load(self.driver, self.settings.heidi_base_url):
            self.logger.info("[INFO] Loaded saved Heidi cookies")
        else:
            self.driver.get(self.settings.heidi_base_url)
        if self.dashboard_visible(timeout=12):
            self.logger.info("[INFO] Heidi dashboard already visible")
            self.cookies.save(self.driver)
            return
        if self._automatic_login():
            self.logger.info("[INFO] Automatic login successful")
            self.cookies.save(self.driver)
            return
        self._manual_fallback()
        self.cookies.save(self.driver)

    def dashboard_visible(self, timeout: int = 30) -> bool:
        locators = [
            (By.XPATH, "//*[normalize-space()='Scribe']"),
            (By.XPATH, "//*[normalize-space()='Evidence']"),
            (By.XPATH, "//*[normalize-space()='Tasks']"),
            (By.XPATH, "//*[normalize-space()='Comms']"),
            (By.XPATH, "//*[contains(normalize-space(.), 'Upcoming') and contains(normalize-space(.), 'Past')]"),
        ]
        try:
            wait_for_any(self.driver, locators, timeout=timeout)
            return True
        except TimeoutException:
            return False

    def _automatic_login(self) -> bool:
        if not self.settings.heidi_email or not self.settings.heidi_password:
            self.logger.warning("[WARNING] HEIDI_EMAIL or HEIDI_PASSWORD is missing; using manual login fallback")
            return False

        try:
            self._enter_email_and_continue()
            self._enter_password_and_continue()
            success = self.dashboard_visible(timeout=45)
            if not success:
                self.logger.warning("[WARNING] Automatic login: dashboard not visible after 45 s")
            return success
        except (TimeoutException, WebDriverException) as exc:
            self.logger.warning("[WARNING] Automatic login failed: %s: %s", type(exc).__name__, exc)
            return False

    def _enter_email_and_continue(self) -> None:
        self.logger.info("[INFO] Entering Heidi email")
        email_input = wait_for_any(
            self.driver,
            [
                (By.CSS_SELECTOR, "input[type='email']"),
                (By.CSS_SELECTOR, "input[name='email']"),
                (By.CSS_SELECTOR, "input[name*='email' i]"),
                (By.CSS_SELECTOR, "input[autocomplete='email']"),
                (By.XPATH, "//label[contains(normalize-space(.), 'Email')]/following::input[1]"),
                (By.XPATH, "//input[contains(@placeholder, 'name@company.com')]"),
                (By.XPATH, "//input[contains(@placeholder, 'Email') or contains(@aria-label, 'Email')]"),
            ],
            timeout=25,
        )
        email_input.clear()
        email_input.send_keys(self.settings.heidi_email)
        self._click_submit_like("Continue")

    def _enter_password_and_continue(self) -> None:
        self.logger.info("[INFO] Waiting for Heidi password page")
        password_input = wait_for_any(
            self.driver,
            [
                (By.CSS_SELECTOR, "input[type='password']"),
                (By.CSS_SELECTOR, "input[name='password']"),
                (By.CSS_SELECTOR, "input[name*='password' i]"),
                (By.CSS_SELECTOR, "input[autocomplete='current-password']"),
                (By.XPATH, "//label[contains(normalize-space(.), 'Password')]/following::input[1]"),
                (By.XPATH, "//input[contains(@placeholder, 'Password') or contains(@aria-label, 'Password')]"),
            ],
            timeout=45,
        )
        password_input.clear()
        password_input.send_keys(self.settings.heidi_password)
        self.logger.info("[INFO] Password entered, submitting")
        # Try the submit button first; fall back to pressing ENTER on the input
        # (Auth0 / Heidi's login form always accepts ENTER as form submit)
        try:
            self._click_submit_like("Continue")
        except TimeoutException:
            self.logger.info("[INFO] Submit button not found, pressing ENTER on password field")
            from selenium.webdriver.common.keys import Keys
            password_input.send_keys(Keys.RETURN)

    def _click_submit_like(self, preferred_text: str) -> None:
        try:
            click_text(self.driver, preferred_text, timeout=5)
            return
        except TimeoutException:
            pass
        button = find_first(
            self.driver,
            [
                (By.CSS_SELECTOR, "button[type='submit']"),
                (By.CSS_SELECTOR, "input[type='submit']"),
                (
                    By.XPATH,
                    "//*[self::button or @role='button'][contains(., 'Continue') or contains(., 'Log in') "
                    "or contains(., 'Sign in') or contains(., 'Sign In')]",
                ),
            ],
        )
        if button is None:
            raise TimeoutException(f"No submit button found for {preferred_text}")
        WebDriverWait(self.driver, 10).until(EC.element_to_be_clickable(button))
        button.click()

    def _manual_fallback(self) -> None:
        import sys

        # In headless mode (e.g. Docker) there is no visible browser window for the
        # user to interact with, so manual login is physically impossible.
        if self.settings.headless:
            raise RuntimeError(
                "Automatic login failed and headless mode is active — manual login is "
                "not possible in a headless/Docker environment.\n"
                "Check that HEIDI_EMAIL and HEIDI_PASSWORD are set correctly in your "
                ".env / docker-compose environment, and that the credentials work on "
                "https://scribe.heidihealth.com."
            )

        # In interactive mode, check that stdin is actually a TTY before calling input().
        # Docker and CI runners attach a non-TTY pipe to stdin, which raises EOFError.
        if not sys.stdin.isatty():
            raise RuntimeError(
                "Automatic login failed and stdin is not a terminal (no TTY) — "
                "manual login cannot be used.\n"
                "Make sure HEIDI_EMAIL and HEIDI_PASSWORD are set in your environment, "
                "or run with 'docker-compose run -it heidi_backend' to attach a TTY."
            )

        print()
        print("Automatic login failed.")
        print("Please log in manually using the open browser.")
        try:
            input("Press ENTER when the Heidi dashboard is visible.")
        except EOFError:
            raise RuntimeError(
                "Automatic login failed and stdin reached EOF — cannot prompt for manual login.\n"
                "Ensure HEIDI_EMAIL and HEIDI_PASSWORD are set correctly."
            )
        if not self.dashboard_visible(timeout=30):
            raise TimeoutException("Manual login confirmation was received, but the Heidi dashboard was not detected.")
        self.logger.info("[INFO] Manual login confirmed")

