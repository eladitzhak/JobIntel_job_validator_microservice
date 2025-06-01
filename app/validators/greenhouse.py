from typing import Any, Dict, Optional, Tuple
import requests
from bs4 import BeautifulSoup
from datetime import datetime
import pytz
import bleach
from urllib.parse import urlparse, parse_qs
from html import unescape

from app.validators.base import BaseValidator
from app.log_config import logger
from app.services.gpt_fallback import gpt_extract_job_metadata_from_html
from app.utils.location_utils import is_location_in_israel  # To be added in Step 2



class GreenhouseValidator(BaseValidator):
    def __init__(self, url: str) -> None:
        super().__init__(url)
        self.original_url = url  # Track original URL for comparison
        self.url = url

        self.job_json: Optional[Dict[str,Any]] = None
        self.soup = None
        self.api_url = self._build_api_url_from_board_token_and_job_id()


    
    
    def _load_page(self):
        response = requests.get(self.url, timeout=10)
        if response.status_code != 200:
            return False
        self.soup = BeautifulSoup(response.text, "html.parser")
        return True

    def replace_embed_url_if_needed(self) -> None:
        """
        If the original Greenhouse URL is an embed and we have a valid board+job,
        upgrade to the canonical URL format. If that fails, fallback to absolute_url.
        """
        if not self.job_json or "embed" not in self.url:
            return

        job_id, board_token = self._parse_board_and_job_id_from_self_url()
        if board_token and job_id:
            upgraded_url = f"https://boards.greenhouse.io/{board_token}/jobs/{job_id}"
            try:
                resp = requests.head(upgraded_url, timeout=5)
                if resp.status_code in [200, 302]:
                    logger.info(f"{self.log_prefix()} - ✅ Upgraded embed URL → {upgraded_url}")
                    self.url = upgraded_url
                    return
            except Exception as e:
                logger.warning(f"{self.log_prefix()} - HEAD check failed for canonical: {e}")

        # Fallback to absolute_url
        abs_url = self.job_json.get("absolute_url")
        if abs_url and abs_url != self.url:
            logger.info(f"{self.log_prefix()} - Fallback: replacing embed with absolute_url → {abs_url}")
            self.url = abs_url

    def _parse_board_and_job_id_from_self_url(self) -> Tuple[Optional[str], Optional[str]]:
        """
        Extract board token and job ID from a greenhouse URL.
        Returns (board_token, job_id)
        Example:
        https://boards.greenhouse.io/yotpo/jobs/6879531
        → board_token: "yotpo", job_id: "6879531"
        another example:
        'https://boards.greenhouse.io/embed/job_app?for=nice&token=4550857101'
        """
        try:
            
            job_id, board_token = None, None
            parsed = urlparse(self.url)
            path_parts = parsed.path.strip("/").split("/")
            query = parse_qs(parsed.query)

            # ✅ Case 1: Embed application form
            # https://boards.greenhouse.io/embed/job_app?for=nice&token=4550857101
            if "token" in query:
                job_id = query["token"][0]  # This is the job ID
                board_token = query.get("for", [None])[0]  # This is the board token
                if board_token:
                    return board_token, job_id
             


            # ✅ Case 2: Classic URL
            # https://boards.greenhouse.io/yotpo/jobs/6769266
            if len(path_parts) >= 3 and path_parts[-2] == "jobs" and path_parts[-1].isdigit():
                board_token = path_parts[-3]
                job_id = path_parts[-1]
                return board_token, job_id


            # ✅ Case 3: Job ID via query param (?gh_jid=...)
            if "gh_jid" in query:
                job_id = query["gh_jid"][0]

                 # Try extracting board token
                board_token = None
                if "for" in query:
                    board_token = query["for"][0]
                elif path_parts:
                    board_token = path_parts[0]  # fallback to first path part

                if board_token:
                    return board_token, job_id
                return board_token, job_id

            # ✅ Case 4: Just a board embed — not a job
        # https://boards.greenhouse.io/embed/job_board?for=jfrog
            if "for" in query and "embed" in path_parts:
                return query["for"][0], None


            # ✅ Case 5: Fallback — scan for digits (job ID)
            job_id = next((part for part in path_parts if part.isdigit()), job_id)
            board_token = path_parts[0] if path_parts else board_token
            if board_token.lower() == "embed":
                board_token = None
            if job_id and board_token:
                return board_token, job_id
            
            
            if "boards.greenhouse.io" in parsed.netloc and len(path_parts) >= 1:
                board_token = path_parts[0]
                return board_token, job_id

            logger.warning(f"{self.log_prefix()} - Couldn't parse board/job from URL: {self.url}")
            return None, None
        
        except Exception as e:
            logger.error(f"{self.log_prefix()} - Error parsing job link: {e}")
            return None, None
    
    def _load_json_api(self) -> bool:
        """
            Load the job data from the Greenhouse JSON API.
        """
        # board_token, job_id = self._parse_board_and_job_id_from_self_url()
        # if not board_token or not job_id:
            # self.job_status = "error"
            # self.error_reason = "Failed to parse board_token or job_id from URL"

            # return False

        # self.api_url = f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}"

        if not self.api_url:
            logger.warning(f"{self.log_prefix()} - API URL not constructed")
            self.job_status = "error"
            self.error_reason = "missing api url Failed to parse board_token or job_id from URL"
            return False
        try:
            response = requests.get(self.api_url, timeout=7)
            self.job_json = response.json()
            if response.status_code == 404 or self.job_json.get("error") == "job not found":
                logger.warning(f"❌ Greenhouse job not found (404): {self.api_url}")
                self.error_reason = "Job not found (404 from API)"
                self.job_json = None  # Ensure consistency
                self.job_status = "validation failed"
                return False

            return True
        except Exception as e:
            logger.error(f"{self.log_prefix()} - e {e}")
            return False
        
    def bleach_clean(self, html: Optional[str]) -> str:
        """
        Clean and sanitize HTML content.
        """
        return bleach.clean(
            html or "",
            tags=["p", "ul", "ol", "li", "b", "strong", "em", "br"],
            attributes={},
            strip=True,
        )
    #TODO:##need to think if need to return the error like is not in israel of company page
    def validate(self) -> bool:
        """
        Check if job is valid and located in Israel.
        """
        if not self._load_json_api():
            logger.warning(f"❌ Failed to load Greenhouse JSON API: {self.api_url}")

            return False

        content = self.job_json.get("content", "")
        if not content or "<html>" in content.lower():  # heuristic for redirect
            logger.warning(f"❌ Invalid job content or likely redirect: {self.url}")
            self.job_status = "error"
            self.error_reason = "Empty or invalid Greenhouse job content"
            return False
        #TODO: Check if job is still open
        location = self.job_json.get("location", {}).get("name")
        if not is_location_in_israel(location):
            self.error_reason = f"Job location '{location}' is not in Israel"
            self.job_status = "validation failed"
            logger.warning(f"❌ Location not in Israel: {location}")
            return False

        return True

    def strip_ms_spans(self, html_str: str) -> str:
        """
        Unwrap Microsoft Word-style <span> elements from the HTML.
        """
        soup = BeautifulSoup(html_str, "html.parser")
        for span in soup.find_all("span"):
            if span.get("class") and any("TextRun" in cls or "ccp" in cls for cls in span["class"]):
                span.unwrap()
        return str(soup)
    
    def replace_embed_url_if_needed(self) -> None:
        """
        Upgrade embed URL to stable Greenhouse format if available and valid.
        Fallback to absolute_url only if needed.
        If the original URL is an embedded link to from without job info and the API provides a direct job URL, try to \
        make greenhouse format as we need it for future valitor checks., 
        Fallback to absolute_url in company only if needed.
        replace self.url with the direct job url version.

         If the URL is an 'embed' Greenhouse link and we can extract job ID + board token,
        try upgrading to the canonical Greenhouse job URL format.

        Replace embed-style Greenhouse URLs with a stable job-specific URL if available.
        1. If the URL is an 'embed' link (e.g. job_app?token=...), attempt to reconstruct
            the canonical Greenhouse format: https://boards.greenhouse.io/{board}/jobs/{job_id}
        2. If that fails, fallback to the API's `absolute_url` (external company site).
        3. Updates self.url only if needed.
        """
        
        if not self.job_json or "embed" not in self.url:
            return
        
        board_token, job_id,  = self._parse_board_and_job_id_from_self_url()

        # Step 1: Try upgrading to canonical Greenhouse job URL
        if board_token and job_id:
            upgraded_url = f"https://boards.greenhouse.io/{board_token}/jobs/{job_id}"
            try:
                resp = requests.head(upgraded_url, timeout=5,allow_redirects=True)
                # Use HEAD request to check if the URL is reachable
                if resp.status_code == 200:
                    logger.info(f"{self.url} - ✅ Replaced embed URL → {upgraded_url}")
                    self.url = upgraded_url
                    return
                else:
                    logger.warning(f" ❌ Canonical URL not reachable: {upgraded_url} [{resp.status_code}]")
            except Exception as e:
                logger.error(f"{self.log_prefix()} - Exception checking canonical URL: {upgraded_url} → {e}")

        # Step 2: Fallback to absolute_url from API (if any)
        absolute_url = self.job_json.get("absolute_url")
        if absolute_url and absolute_url != self.url:
            logger.info(f" - ⚠️ Falling back to absolute_url → {absolute_url}")
            self.url = absolute_url
    
    def extract_metadata(self) -> Dict[str, Optional[Any]]:
        """
        Extract structured metadata from the Greenhouse JSON.
        """
        if not self.job_json:
            self._load_json_api()

        job = self.job_json or {}

        # 🧼 Clean and sanitize HTML content
        # Step 1: Decode HTML-escaped content
        raw_html = unescape(job.get("content", ""))

        # Step 2: Remove Microsoft Word garbage spans
        cleaned_html = self.strip_ms_spans(raw_html)

        # Step 3: Final sanitization using bleach (for DB or UI display)
        # description: str = self.bleach_clean(job.get("content", ""))
        description: str = self.bleach_clean(cleaned_html)
        description_html: Optional[str] = job.get("content")

        title_raw = job.get("title", "")
        title = " ".join(title_raw.split())
        if not title:
            title = "Title inside link"

        metadata: Dict[str, Optional[Any]] = {
            "title": title,
            "company": job.get("company_name"),
            "location": job.get("location", {}).get("name"),
            "description": description,
            "responsibilities": None,
            "requirements": None,
            "posted_time": None,
        }

        self.replace_embed_url_if_needed()
        #if url changed, update the metadata link
        if self.url != self.original_url:
            metadata["link"] = self.url
        # Parse posted_time
        posted_raw: Optional[str] = job.get("updated_at") or job.get("first_published")
        if posted_raw:
            try:
                metadata["posted_time"] = datetime.fromisoformat(posted_raw.replace("Z", "+00:00"))
            except Exception:
                metadata["posted_time"] = None

        #TODO:REMOVED FOR NOW AS WE GET ALL THE DATA READY WITH TAGS FROM DESCRIPTION
        # # 🧠 Step 1: Fallback if any important fields are missing
        # missing = [k for k in ["location", "description", "requirements", "responsibilities", "company","title"] if not metadata[k]]
        # if missing:
        #     prompt = f"""
        #     From the following HTML, extract ONLY the missing fields: {', '.join(missing)}.
        #     Return JSON with those keys.

        #     - description: Only the intro and overview (no responsibilities)
        #     - responsibilities: bullet-point string as HTML (<ul><li>) not a list
        #     - requirements: return as a bullet string or paragraph html (<ul><li>), not a list
        #     - location: city or "Remote", ideally "Tel Aviv, Israel"

        #     HTML:
        #     {description[:12000]}
        #     """.strip()

        #     try:
        #         gpt_result = gpt_extract_job_metadata_from_html(description_html, prompt)

        #         for key in missing:
        #             metadata[key] = gpt_result.get(key)


        #     except Exception as e:
        #         logger.error(f"{self.log_prefix()} - GPT fallback failed: {e}")


         # 🧼 Step 2: Remove duplication (responsibilities or requirements inside description)
        
        #TODO:CHECK HERE
        def plain_text(html: str) -> str:
            from bs4 import BeautifulSoup
            return BeautifulSoup(html or "", "html.parser").get_text(separator=" ", strip=True).lower()

        desc_text = plain_text(metadata["description"] or "")
        resp_text = plain_text(metadata["responsibilities"] or "")
        reqs_text = plain_text(metadata["requirements"] or "")

        if resp_text and resp_text in desc_text:
            metadata["responsibilities"] = None
        if reqs_text and reqs_text in desc_text:
            metadata["requirements"] = None

    
    
        return metadata
    
    def url_is_company_page(self, url: str) -> bool:
        """
        Greenhouse does not use URL structure to detect company page.
        It detects invalid jobs based on JSON API result.
        This must be set *during* validate().
        """
        return self.job_json is None or not self.job_json.get("content")

    def _build_api_url_from_board_token_and_job_id(self) -> Optional[str]:
        """Build Greenhouse API URL from parsed board token and job ID."""
        board_token, job_id = self._parse_board_and_job_id_from_self_url()
        
        if board_token == "embed":
            board_token = None

        # ✅ Fallback: Try to extract board_token from absolute_url if missing
        if (not board_token or not job_id) and self.job_json:
            absolute_url = self.job_json.get("absolute_url", "")
            if absolute_url:
                parsed = urlparse(absolute_url)
                path_parts = parsed.path.strip("/").split("/")
                if "jobs" in path_parts:
                    try:
                        idx = path_parts.index("jobs")
                        job_id = path_parts[idx + 1]
                        board_token = path_parts[idx - 1] if idx >= 1 else None
                    except Exception:
                        pass

        if board_token and job_id:
            return f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}"
        return None
        
        
        if board_token and job_id:
            return f"https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}"
        elif "embed" in self.url:
            # If it's an embed link, we can still try to get the job ID from the token
            query = parse_qs(urlparse(self.url).query)
            if "token" in query:
                return f"https://boards-api.greenhouse.io/v1/boards/{query.get('for', [None])[0]}/jobs/{query['token'][0]}"

        return None

    def _compute_best_api_url(self) -> Optional[str]:
        board, job_id = self._parse_board_and_job_id_from_self_url()

        if board and job_id:
            return f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs/{job_id}"
        return None
    
    def _create_api_url(self) -> Optional[str]:
        if "embed" not in self.url:
            return self.url
        try:
            board_name, job_id = self._parse_board_and_job_id_from_self_url()
            if ("embed" in board_name or board_name is None):
                #get company name 
                response = requests.get(self.url, timeout=7)
            if response.status_code == 404 or response.json().get("error") == "job not found":
                logger.warning(f"❌ Greenhouse job not found (404): {self.api_url}")
                return None
            
            # get company name from json
            board_name = response.json().get("company")

        except Exception as e:
            pass