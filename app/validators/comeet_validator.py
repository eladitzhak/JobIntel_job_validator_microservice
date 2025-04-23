import json
from datetime import datetime
from urllib.parse import urlparse
import re
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from bs4 import BeautifulSoup
from app.log_config import logger
from selenium.webdriver.chrome.webdriver import WebDriver

from app.validators.base import BaseValidator

WAIT_TIME_TO_LOAD_PAGE = 15  # seconds
EXPECTED_SELECTOR = "h1, button"


class ComeetValidator(BaseValidator):
 
    def __init__(self, url: str):
        super().__init__(url)
        # self.driver = self._init_driver()
        # self.wait = WebDriverWait(self.driver, WAIT_TIME_TO_LOAD_PAGE)
        self.driver = None
        self.wait = None

    def uses_driver(self) -> bool:
        return True

    def set_driver(self, driver: WebDriver):
        self.driver = driver
        self.wait = WebDriverWait(driver, WAIT_TIME_TO_LOAD_PAGE)
        

    def _init_driver(self):
        options = Options()
        options.add_argument("--headless")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-gpu")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--ignore-certificate-errors")
        return webdriver.Chrome(options=options)
    
    def is_page_full_loaded(self):
        try:
            self.driver.get(self.url)
            self.wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, ".careerHeroHeader h1")))
            return True
        except Exception:
            return False

    def validate(self) -> bool:
        try:
            self.driver.get(self.url)
            # Wait for job title or apply button
            self.wait.until(
                EC.presence_of_element_located((By.CSS_SELECTOR, "h1, button"))
            )
            return True
        except Exception as e:
            logger.error(f"Comeet Validation error: {e}")
            return False
      
    def extract_metadata(self) -> dict:
        metadata = {
            "title": None,
            "company": None,
            "location": None,
            "posted_time": None,
            "description": None,
            "requirements": None,
            "responsibilities": None,
        }

        try:
            soup = BeautifulSoup(self.driver.page_source, "html.parser")

            # Title
            h1 = soup.select_one(".careerHeroHeader h1")
            if h1:
                metadata["title"] = h1.text.strip()

            # Company from URL
            parts = urlparse(self.url).path.strip("/").split("/")
            if len(parts) >= 2:
                metadata["company"] = parts[1].capitalize()

            # Location (first item in subheader)
            subheader = soup.select_one(".careerHeroHeader__subheader")
            if subheader:
                sub_parts = subheader.text.strip().split("·")
                if sub_parts:
                    metadata["location"] = sub_parts[0].strip()

            # Posted Date + Description from JSON-LD
            jsonld_tag = soup.find("script", {"type": "application/ld+json"})
            if jsonld_tag:
                try:
                    raw_text = jsonld_tag.string or jsonld_tag.text
                    # Clean illegal characters: remove unescaped newlines inside strings
                    safe_text = re.sub(r'(?<!\\)[\r\n]+', r' ', raw_text)
                    decoder = json.JSONDecoder()
                    # Truncate anything after the first top-level closing brace
                    job_json, _ = decoder.raw_decode(safe_text.strip())

                    metadata = {
                        "title": job_json.get("title") if metadata["title"] is None else metadata["title"],
                        "company": job_json.get("hiringOrganization", {}).get("name") if metadata["company"] is None else metadata["company"],
                        # "company": job_json.get("hiringOrganization", {}).get("name"),
                        "location": job_json.get("jobLocation", {}).get("address", {}).get("addressLocality"),
                        "description": job_json.get("description"),
                        "posted_time": job_json.get("datePosted"),
                    }
                except (json.JSONDecodeError, ValueError) as e:
                    print(f"❌ Failed to parse cleaned JSON-LD: {e}")

             # --- Section Helpers ---
            def extract_requirements(soup: BeautifulSoup) -> str | list[str]:
                req_header = soup.find("h3", string=lambda s: s and "requirement" in s.lower())
                if req_header:
                    description_div = req_header.find_next("div", class_="company-description")
                    if description_div:
                        ul_elements = description_div.find_all("ul")
                        if ul_elements:
                            all_items = []
                            for ul in ul_elements:
                                items = [li.get_text(strip=True) for li in ul.find_all("li")]
                                all_items.extend(items)
                            return all_items
                        else:
                            return description_div.get_text(separator="\n", strip=True)
                return None

            def extract_responsibilities(soup: BeautifulSoup) -> str | list[str]:
                header = soup.find(lambda tag:
                    tag.name in ["h3", "h2", "b", "strong"] and
                    "responsibilit" in tag.get_text(strip=True).lower()
                )
                if header:
                    description_div = header.find_next("div", class_="company-description")
                    if description_div:
                        ul_elements = description_div.find_all("ul")
                        if ul_elements:
                            return [li.get_text(strip=True) for ul in ul_elements for li in ul.find_all("li")]
                        return description_div.get_text(separator="\n", strip=True)
                return None

            def extract_responsibilities_fallback(soup: BeautifulSoup):
                for tag in soup.find_all(["h3", "h2", "b", "strong"]):
                    if "responsibilit" in tag.get_text(strip=True).lower():
                        ul = tag.find_next("ul")
                        if ul:
                            return [li.get_text(strip=True) for li in ul.find_all("li")]
                        p = tag.find_next("p")
                        if p:
                            return p.get_text(strip=True)
                        div = tag.find_next("div")
                        if div:
                            return div.get_text(strip=True)
                return None
            
                    # --- Set into metadata ---
            metadata["requirements"] = extract_requirements(soup)
            metadata["responsibilities"] = extract_responsibilities_fallback(soup) or extract_responsibilities(soup)
            
        

            def extract_section(header_name: str):
                section = soup.find("h2", string=lambda s: s and header_name.lower() in s.lower())
                if section:
                    ul = section.find_next_sibling("ul")
                    if ul:
                        return [li.get_text(strip=True) for li in ul.find_all("li")]
                    desc = section.find_next_sibling("div", class_="company-description")
                    if desc:
                        return desc.get_text(separator="\n", strip=True)
                return None

            
            
            # metadata["responsibilities"] = extract_section("Responsibilities")
            # metadata["requirements"] = extract_section("Requirements")
        except Exception as e:
            logger.error(f"Error extracting metadata from Comeet: {e}")
            metadata = {
                "title": None,
                "company": None,
                "location": None,
                "posted_time": None,
                "description": None,
                "requirements": None,
                "responsibilities": None,
            }
        finally:
                return metadata


