import requests
from typing import Optional
import re

from app.config import settings
from app.log_config import logger
from app.services.gpt_fallback import classify_location_with_gpt


def clean_location(location: str) -> str:
    # Remove words like "Remote", "Hybrid", etc.
    location = re.sub(r'\b(remote|hybrid|onsite|relocation)\b', '', location, flags=re.IGNORECASE)
    # Remove company prefixes or internal codes (e.g., "Samsung Israel R&D Center - SIRC")
    # Remove dashes, extra whitespace
    location = location.replace('-', ' ')
    return location.strip()

def is_location_in_israel(location: Optional[str]) -> bool:
    """
    Uses OpenCage API to determine if the location is in Israel.

    Args:
        location (Optional[str]): Location string (e.g., "Migdal HaEmek", "Berlin")

    Returns:
        bool: True if OpenCage identifies it as being in Israel, False otherwise.
    """
    if not location:
        return False
    
    try:
        location = clean_location(location)
        if "israel" in location.lower():
            return True
        split_location = location.split(",")
        if len(split_location) > 1:
            last_item = split_location[-1].strip().lower()
            # If location has multiple parts, check the last part
            if 'il' == last_item.lower():
                logger.info(f"📍 Location '{location}' contains 'il' in the last part")
                return True
        
        url = "https://api.opencagedata.com/geocode/v1/json"
        params = {
            "q": location,
            "key": settings.opencage_api_key,
            "limit": 1,
            "language": "en"
        }
        
        response = requests.get(url, params=params, timeout=5)
        data = response.json()

        if response.status_code != 200:
            # OpenCage failed at HTTP level — don't fallback to GPT
            logger.warning(f"🌍 OpenCage failed with HTTP {response.status_code}")
            return False
        if not data.get("results"):
            # OpenCage returned OK, but couldn't resolve location → use GPT fallback
            logger.info(f"🌍 OpenCage returned no results for '{location}' fallback to chatgpt")
            is_location_in_israel = classify_location_with_gpt(location)
            if is_location_in_israel:
                logger.info(f"📍 GPT classified location '{location}' as in Israel.")
                return True
            else:
                logger.info(f"📍 GPT classified location '{location}' as NOT in Israel")
                return False

        components = data["results"][0]["components"]
        country = components.get("country", "").lower()
        return "israel" in country

    except Exception as e:
        logger.error(f"OpenCage API error: {e}")
        return False
