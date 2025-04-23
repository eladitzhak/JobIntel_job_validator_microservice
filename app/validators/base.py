from abc import ABC, abstractmethod

class BaseValidator(ABC):
    """
    Abstract base class for job validators.
    All site-specific validators must inherit from this.
    """

    def __init__(self, url: str):
        self.url = url

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
