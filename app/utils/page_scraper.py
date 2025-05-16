from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
import time
import re
import json

from app.utils.chrome_driver_manger import DriverManager


class DummyValidator:
    """
    A temporary validator used only to satisfy DriverManager.
    It tells the manager that it uses a driver and knows how to init it.
    """
    def uses_driver(self):
        return True

    def _init_driver(self):
        chrome_options = Options()
        chrome_options.add_argument("--headless")
        chrome_options.add_argument("--disable-gpu")
        chrome_options.add_argument("--no-sandbox")
        chrome_options.add_argument("--disable-dev-shm-usage")
        return webdriver.Chrome(options=chrome_options)


def extract_visible_text_from_url(url: str, max_length: int = 4000) -> str:
    """
    Fetches a fully rendered job page using Selenium (via your DriverManager)
    and returns visible text content (cleaned and trimmed).

    :param url: The job post URL
    :param max_length: Max character length to return
    :return: Clean text from the page
    """
    dummy_validator = DummyValidator()

    with DriverManager() as driver_manager:
        driver = driver_manager.get_or_create(dummy_validator)
        driver.get(url)

        # Let the page fully render JS (adjust time if needed)
        time.sleep(3)

        html = driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        metadata = {}
        script_tag = soup.find("script", {"type": "application/ld+json"})
        if script_tag:
            try:
                metadata = json.loads(script_tag.string)
            except Exception as e:
                print(f"⚠️ Failed to parse ld+json: {e}")

        # Remove irrelevant tags
        for tag in soup(["script", "style", "noscript"]):
            tag.decompose()

        text = soup.get_text(separator="\n").strip()
        lines = text.splitlines()
        non_empty_lines = [line.strip() for line in lines if line.strip()]  # remove empty/whitespace-only lines
        no_saces_text =  "\n".join(non_empty_lines)
        
        return {
            "metadata": metadata,
            "visible_text": no_saces_text,
            "html": html  # Optional: you can remove this if not needed
        }   # If JSON parsing fails, return the cleaned text
            
