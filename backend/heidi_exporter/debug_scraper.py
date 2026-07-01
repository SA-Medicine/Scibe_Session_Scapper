import logging
import sys
import time

from selenium.webdriver.common.by import By
from src.utils.settings import Settings
from src.utils.browser import create_driver

from src.scraper.login import HeidiLogin

logging.basicConfig(level=logging.INFO, stream=sys.stdout)
# Explicitly set the variables since they are required but default to empty strings in docker-compose run.
settings = Settings(heidi_email='a', heidi_password='b', database_url='c', headless=True, max_retries=1, screenshots_enabled=False, heidi_base_url='https://scribe.heidihealth.com')
driver = create_driver(settings)

login = HeidiLogin(driver, logging.getLogger(), max_retries=1)
# we don't actually need to ensure_logged_in to test the DOM extraction logic if we already know what we want.
# Actually we DO need to log in to see the dashboard. 
# But wait, without credentials in docker-compose run it won't login.
# Let's just use the main discovery script by doing `docker-compose run backend python main.py --discover-only` with proper ENV VARS passed,
# OR we can just inject into main.py locally!
