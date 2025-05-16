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
from bs4 import BeautifulSoup
from app.services.gpt_fallback import gpt_extract_job_metadata_from_html
from datetime import datetime
import pytz
import re
import json


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
                EC.presence_of_element_located((By.CSS_SELECTOR, "button")) #h1, button
            )
            return True
        except Exception as e:
            logger.error(f"Comeet Validation error while waiting for button to appear in job page: {e}")
            return False

    def normalize_location(self, location_str: str) -> str:
        """
        Normalize raw location strings to consistent form.
     """
        location_str = location_str.strip().lower()

        # Common known city mappings
        known_locations = {
            "tel aviv": "Tel Aviv, Israel",
            "herzliya": "Herzliya, Israel",
            "jerusalem": "Jerusalem, Israel",
            "haifa": "Haifa, Israel",
            "petah tikva": "Petah Tikva, Israel",
            "rishon lezion": "Rishon LeZion, Israel",
            "beer sheva": "Beer Sheva, Israel",
            "kfar saba": "Kfar Saba, Israel",
            "netanya": "Netanya, Israel",
            "israel": "Israel",
        }

        for key, value in known_locations.items():
            if key in location_str:
                return value

        # Default: capitalize first letters
        return location_str.title()


    def extract_json_ld(self,soup):
        """
        Extracts JSON-LD data from the HTML soup.
        """
        try:
        # Find the <script> tag with type "application/ld+json"
            scripts = soup.find_all("script", type="application/ld+json")
            for script in scripts:
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict) and data.get("@type") == "JobPosting":
                        return data
                except json.JSONDecodeError:
                    continue
            jsonld_tag = soup.find("script", {"type": "application/ld+json"})
            if jsonld_tag:
                    try:
                        raw_text = jsonld_tag.string or jsonld_tag.text
                        # Clean illegal characters: remove unescaped newlines inside strings
                        safe_text = re.sub(r'(?<!\\)[\r\n]+', r' ', raw_text)
                        decoder = json.JSONDecoder()
                        # Truncate anything after the first top-level closing brace
                        job_json, _ = decoder.raw_decode(safe_text.strip())
                        return job_json
                    except (json.JSONDecodeError, ValueError) as e:
                        print(f"❌ Failed to parse cleaned JSON-LD: {e}")
                        return {}

        except Exception as e:
            logger.error(f"Error extracting JSON-LD: {e}")
            return {}

    def get_title(self,soup, json_ld):
        """
        Extracts the job title from JSON-LD or HTML.
        """
        if json_ld and json_ld.get("title"):
            return json_ld.get("title")
        title_tag = soup.find("h1")
        if title_tag:
            return title_tag.get_text(strip=True)
        h2 = soup.find("h2")
        if h2:
            return h2.get_text(strip=True)
        return None
    #

    def get_company(self, soup, json_ld, url):
        """
        Extracts the company name from JSON-LD or URL.
        """
        if json_ld:
            hiring_org = json_ld.get("hiringOrganization", {})
            if isinstance(hiring_org, dict):
                return hiring_org.get("name")
        # Fallback to extracting from URL
        path_parts = urlparse(url).path.strip("/").split("/")
        if len(path_parts) >= 2:
            return path_parts[1].capitalize()
        return None
    def get_visible_html_text(self, soup):
        """
        Extracts visible text from the HTML soup.
        """
        for tag in soup(["script", "style","meta"]):
            # Remove script, style, and meta tags
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)
    def get_location(self,soup, json_ld):
        """
        Extracts the job location from JSON-LD or HTML. <span ng-if="getLocationName(position.location)" class="">Tel Aviv-Yafo, Tel Aviv District, IL</span>
        """
        if json_ld:
            job_location = json_ld.get("jobLocation", {})
            if isinstance(job_location, dict):
                address = job_location.get("address", {})
                if isinstance(address, dict) and address:
                    return address.get("addressLocality")

         # Try 2: positionDetails with icon
        ul = soup.find("ul", class_="positionDetails")
        if ul:
            for li in ul.find_all("li"):
                icon = li.find("i", class_="fa fa-map-marker")
                if icon:
                    return li.get_text(strip=True).replace(icon.get_text(strip=True), "").strip()
        # Fallback to HTML parsing
        location_tag = soup.find("div", class_="location")
        if location_tag:
            return location_tag.get_text(strip=True)
        # Try 3: Search full page for "fa-map-marker"
        for icon in soup.find_all("i", class_="fa fa-map-marker"):
            li = icon.find_parent("li")
            if li:
                return li.get_text(strip=True).replace(icon.get_text(strip=True), "").strip()

        subheader = soup.find("div", class_="careerHeroHeader__subheader")
        if subheader:
            spans = subheader.find_all("span")
        if spans:
            location_text = spans[0].get_text(strip=True)
            return location_text
        return None

    def get_posted_date(self,json_ld):
        """
        Extracts the posted date from JSON-LD.
        """
        if json_ld:
            date_posted = json_ld.get("datePosted")
            if date_posted:
                try:
                    return datetime.fromisoformat(date_posted.replace("Z", "+00:00"))
                except ValueError as e:
                    logger.error(f"Error parsing date: {e}")
                    pass
        return None

    def get_section_by_keywords(self,soup, keywords):
        for tag in soup.find_all(["h2", "h3", "strong", "b"]):
            text = tag.get_text(strip=True).lower()
            if any(k in text for k in keywords):
                ul = tag.find_next_sibling("ul")
                if ul:
                    return [li.get_text(strip=True) for li in ul.find_all("li")]
                div = tag.find_next_sibling("div")
                if div:
                    return div.get_text(strip=True)
        return None

    def get_description(self,soup, json_ld):
        """
        Extracts the job description from JSON-LD or HTML.
        """
        if json_ld and json_ld.get("description"):
            # Clean illegal characters: remove unescaped newlines inside strings
            safe_text = re.sub(r'(?<!\\)[\r\n]+', r' ', json_ld.get("description"))
            if safe_text:
                # Decode JSON safely
                try:
                    decoder = json.JSONDecoder()
                    job_json, _ = decoder.raw_decode(safe_text.strip())
                    return job_json
                except (json.JSONDecodeError, ValueError) as e:
                    logger.error(f"Failed to parse cleaned JSON-LD: {e}")
            description = json_ld.get("description")
            if description:
                return BeautifulSoup(description, "html.parser").get_text(separator="\n", strip=True)
        # Fallback to HTML parsing
        description_section = soup.find("div", class_="description")
        if description_section:
            return description_section.get_text(separator="\n", strip=True)
        return None

    def get_responsibilities(self,soup):
        """
        Extracts the responsibilities section from HTML.
        """
        responsibilities_heading = soup.find(
            lambda tag: tag.name in ["h2", "h3", "strong", "b"] and "responsibilities" in tag.get_text(strip=True).lower()
        )
        if responsibilities_heading:
            ul = responsibilities_heading.find_next_sibling("ul")
            if ul:
                return [li.get_text(strip=True) for li in ul.find_all("li")]
        resp =  self.get_section_by_keywords(soup, ["responsibilit", "what you'll do", "you will do"])
        if resp:
            return resp
        return []

    def get_requirements(self,soup):
        """
        Extracts the requirements section from HTML.
        """
        requirements_heading = soup.find(lambda tag: tag.name in ["h2", "h3"] and "requirements" in tag.get_text(strip=True).lower())
        if requirements_heading:
            ul = requirements_heading.find_next_sibling("ul")
            if ul:
                return [li.get_text(strip=True) for li in ul.find_all("li")]
        return self.get_section_by_keywords(soup, ["requirement", "qualifications", "experience"])
        return []

    def extract_metadata(self) -> dict:
        self.driver.get(self.url)  # ✅ self.url is passed in the constructor
        html = self.driver.page_source
        soup = BeautifulSoup(html, "html.parser")
        json_ld = self.extract_json_ld(soup)

        # Step 1: Try all structured extractors
        title = self.get_title(soup, json_ld)
        company = self.get_company(soup, json_ld, self.url)
        location = self.get_location(soup, json_ld)
        posted_date = self.get_posted_date(json_ld)
        description = self.get_description(soup, json_ld)
        responsibilities = self.get_responsibilities(soup)
        requirements = self.get_requirements(soup)

        missing_fields = []
        if not description: missing_fields.append("description")
        # if not responsibilities: missing_fields.append("responsibilities")
        if not requirements: missing_fields.append("requirements")
        if not location: missing_fields.append("location")

        prompt = None
        special_notes = ""
        if "requirements" in missing_fields:
            special_notes += "\n- 'Requirements' may appear under headings like 'Are you a good fit?', 'Qualifications', 'Skills', or similar."
        if "responsibilities" in missing_fields:
            special_notes += "\n- 'Responsibilities' may appear under 'What you'll do', 'Your day-to-day', etc."

        if missing_fields:
            prompt = f"""
            From the following HTML, extract ONLY the following fields: {', '.join(missing_fields)}.
            Respond in JSON with exactly those keys.

            {special_notes}

            HTML:
            {html[:12000]}  # Optional limit for safety
        """.strip()

                # Step 2: GPT fallback if critical fields are missing
            # visible_text_only = self.get_visible_html_text(soup)

            # Use full structured HTML for GPT, fallback to main section if available
            main = soup.find("div", class_="company-description")
            html_for_gpt = str(main) if main else str(soup)
                
            gpt_result = gpt_extract_job_metadata_from_html(html_for_gpt, prompt)
            usage = gpt_result.get("usage")

            if usage:
                pricing = {"input": 0.0005, "output": 0.0015}
                gpt_cost_usd = (
                    usage["prompt_tokens"] * pricing["input"] +
                    usage["completion_tokens"] * pricing["output"]
                ) / 1000
                print(f"💵 GPT used: {usage['total_tokens']} tokens → ${gpt_cost_usd:.5f}")

            # gpt_result = gpt_extract_job_metadata_from_html(visible_text_only,prompt)
            description = description or gpt_result.get("description")
            responsibilities = responsibilities or gpt_result.get("responsibilities")
            requirements = requirements or gpt_result.get("requirements")
            title = title or gpt_result.get("title")
            location = location or gpt_result.get("location")
            posted_date = posted_date or gpt_result.get("posted_date")

            
              # 🧠 Special retry: if location is still missing or unclear
            if not location:
                retry_prompt = """
            From the following HTML, extract ONLY the **location of the job**.
            Only return the place where the job itself is located — not the company HQ, contact address, or offices in other countries.

            Respond in JSON like:
            { "location": "Tel Aviv, Israel" }

            HTML:
            """ + html[:12000]  # Optional limit for safety
                

                gpt_result = gpt_extract_job_metadata_from_html(html, retry_prompt)
                location = gpt_result.get("location")

            # 💰 Pricing logic
            usage = gpt_result.get("usage")
            if usage:
                pricing = {"input": 0.0005, "output": 0.0015}
                gpt_cost_usd = (
                    usage["prompt_tokens"] * pricing["input"] +
                    usage["completion_tokens"] * pricing["output"]
                ) / 1000
                print(f"💵 GPT used: {usage['total_tokens']} tokens → ${gpt_cost_usd:.5f}")

        # Step 3: Filter out non-Israel jobs
        if not location or "israel" not in location.lower() and 'il' not in location.lower():
            logger.warning(f"❌ Location not in israel: {location}")

        job_data = {
            "title": title,
            "company": company,
            "location": location,
            "posted_date": posted_date,
            "description": description,
            "responsibilities": responsibilities,
            "requirements":    requirements,
        }

        return job_data
        # ✅ New helper for fallback
        def extract_text(selector):
            tag = soup.select_one(selector)
            return tag.get_text(strip=True) if tag else None

        def get_section_text_by_title(title_keywords):
            for h in soup.find_all(["h2", "h3", "strong"]):
                if any(k in h.text.lower() for k in title_keywords):
                    ul = h.find_next("ul")
                    if ul:
                        return "\n".join(li.get_text(strip=True) for li in ul.find_all("li"))
            return None

        def get_location_from_html():
            icon_tags = soup.find_all("i", class_="fa-map-marker")
            for icon in icon_tags:
                li = icon.find_parent("li")
                if li:
                    return li.text.strip()
            # Fallback via raw search
            match = re.search(r">([^<>]{1,50}),?\s*Israel<", html)
            if match:
                return match.group(1).strip() + ", Israel"
            return None

        # ✅ Try extracting metadata directly
        title = extract_text("h2.positionName") or extract_text("h1")
        company = extract_text("#companyLogo + h2") or "Comeet"

        location = get_location_from_html()
        if not location:
            location = extract_text("li:has(i.fa-map-marker)")

        description = get_section_text_by_title(["description"])
        responsibilities = get_section_text_by_title(["responsibilities", "as a", "you will"])
        requirements = get_section_text_by_title(["requirements", "qualifications", "experience"])

        # ✅ Fallback: parse <script type="application/ld+json">
        if not all([title, location]):
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    data = json.loads(script.string)
                    if isinstance(data, dict):
                        title = title or data.get("title")
                        location = location or data.get("jobLocation", {}).get("address", {}).get("addressLocality") \
                            or data.get("jobLocation", {}).get("name")
                        posted_date_raw = data.get("datePosted")
                        if posted_date_raw:
                            posted_date = datetime.fromisoformat(posted_date_raw.replace("Z", "+00:00")).astimezone(pytz.timezone("Israel"))
                        else:
                            posted_date = None
                except Exception:
                    continue
        else:
            posted_date = None  # Will use validator default

        # ✅ If still missing fields, fallback to GPT
        if not any([description, requirements, responsibilities]):
            gpt_data = gpt_extract_job_metadata_from_html(html)
            description = description or gpt_data.get("description")
            responsibilities = responsibilities or gpt_data.get("responsibilities")
            requirements = requirements or gpt_data.get("requirements")
            title = title or gpt_data.get("title")
            location = location or gpt_data.get("location")
            posted_date = posted_date or gpt_data.get("posted_date")

        # ✅ Location filter: must be Israel
        if not location or "israel" not in location.lower():
            self.mark_invalid("Location not in Israel")
            return {}

        return {
            "title": title,
            "company": company,
            "location": location,
            "posted_date": posted_date,
            "description": description,
            "responsibilities": responsibilities,
            "requirements": requirements,
        }
