class LocationValidationError(Exception):
    """Raised when job location is outside of Israel."""
    def __init__(self, location: str):
        self.location = location
        super().__init__(f"Job location is not in Israel: {location}")