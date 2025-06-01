import inspect
from typing import Optional
from urllib.parse import urlparse
from abc import ABC, abstractmethod

from app.utils.location_utils import is_location_in_israel
from app.log_config import logger  


class BaseValidator(ABC):
    """
    Abstract base class for job validators.
    All site-specific validators must inherit from this.
    """

    def __init__(self, url: str):
        self.url = url
        self.error_reason: Optional[str] = None
        self.job_status: Optional[str] = None

    def uses_driver(self) -> bool:
        """
        Whether this validator needs a shared WebDriver (Selenium).
        Override in subclasses.
        """
        return False
        # Default implementation returns False. Override in subclasses if needed.   
    
    def set_driver(self, driver):
        """
        Injects a shared Selenium driver (if uses_driver returns True).
        Override in subclasses that use Selenium.
        """
        pass

    @abstractmethod
    def validate(self) -> bool:
        """
        Validates if the URL is a real job post and still open.
        Returns True if valid, False otherwise.
        """
        pass

    @abstractmethod
    def extract_metadata(self) -> dict:
        """
        Extracts fields from the job post page like:
        - title
        - company
        - location
        - posted_time
        - description
        - requirements
        - responsibilities (if possible)

        Returns a dictionary with this info.
        """
        pass

    def url_is_company_page(self, url: str) -> bool:
        
        """
        Default logic to check if the URL is likely a company landing page.
        Can be overridden by each validator.

        Example: Comeet URLs with only 3 path parts like:
        /jobs/company-name/title/id → probably job page
        /jobs/company-name → probably company page
        """
        # Example logic: check if the URL contains "company"
        # Check URL pattern
        path_parts = urlparse(url).path.strip('/').split('/')
        if len(path_parts) == 3:
            return True
        return False
    
    def log_prefix(self, depth: int = 1) -> str:
        """
        Returns the prefix for logging function calls.
        This can be overridden by subclasses to provide custom prefixes.
        """
        try:
            frame = inspect.stack()[depth]
            func = frame.function
            lineno = frame.lineno
            return f"{self.__class__.__name__}.{func}():L{lineno}"
        except Exception as e:
            return "ERROR: Could not get log prefix: " + str(e)

    def set_job_status_and_reason_if_not_israel(self, location: str) -> bool:
        """
        using exteranl geo api to check. Sets the job status and error reason if the location is not in israel
        Returns True if the location is not in israel, False otherwise.
        Args:
            location (str): The job location to check.
        Returns:
            bool: True if the location is not in israel, False otherwise (also fir empty location).
        """
        if location and not is_location_in_israel(location):
            self.error_reason = f"Job location '{location}' is not in Israel"
            self.job_status = "validation failed"
            logger.warning(f"❌ Location not in Israel: {location}")
            return True
        return False
