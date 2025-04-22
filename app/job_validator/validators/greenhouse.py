import requests
from bs4 import BeautifulSoup
from app.job_validator.base import BaseValidator
from datetime import datetime

class GreenhouseValidator(BaseValidator):
    def __init__(self, url: str):
        super().__init__(url)
        self.soup = None

    def _load_page(self):
        response = requests.get(self.url, timeout=10)
        if response.status_code != 200:
            return False
        self.soup = BeautifulSoup(response.text, "html.parser")
        return True

    def validate(self) -> bool:
        if not self._load_page():
            return False

        # Check if it's a real job post: has an "application" form or job title
        job_title = self.soup.find("h1")
        apply_form = self.soup.find("form", id="job_application")

        return bool(job_title or apply_form)

    def extract_metadata(self) -> dict:
        if not self.soup:
            self._load_page()

        metadata = {
            "title": None,
            "company": None,
            "location": None,
            "posted_time": None,
            "description": None,
            "requirements": None,
            "responsibilities": None,
        }

        # Title
        title_tag = self.soup.find("h1", class_="app-title")
        if title_tag:
            metadata["title"] = title_tag.get_text(strip=True)

        # Location
        loc_tag = self.soup.find("div", class_="location")
        if loc_tag:
            metadata["location"] = loc_tag.get_text(strip=True)

        # Description & requirements
        desc_div = self.soup.find("div", class_="content")
        if desc_div:
            metadata["description"] = desc_div.get_text(separator="\n", strip=True)

        # Greenhouse doesn’t always show posted date, so we skip it for now
        metadata["posted_time"] = None  # Optional: can be filled with scraped date

        return metadata
