# app/validators/factory.py

from urllib.parse import urlparse
from app.validators.comeet_validator import ComeetValidator
from app.validators.greenhouse import GreenhouseValidator
# from app.validators.lever import LeverValidator
# from app.validators.gpt_fallback import GPTFallbackValidator

class ValidatorFactory:
    """Factory class to create validators based on the job post link."""

    @staticmethod
    def create_validator(link: str):
        """Create a validator instance based on the job post link."""
        domain = urlparse(link).netloc

        if "greenhouse.io" in domain:
            return GreenhouseValidator(link)
        elif "comeet.com" in domain:
            return ComeetValidator(link)

        # elif "lever.co" in domain:
        #     return LeverValidator(link)

        # If domain not supported, fallback (optional for now)
        # return GPTFallbackValidator(link)

        raise ValueError(f"No validator implemented for domain: {domain}")
