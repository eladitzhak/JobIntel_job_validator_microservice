from app.log_config import logger

class DriverManager:
    def __init__(self):
        self.pool = {}

    def get_or_create(self, validator):
        validator_type = type(validator).__name__.lower()

        if not validator.uses_driver():
            raise Exception(f"{validator_type} does not use a driver, but get_or_create was called.")
        
        if validator_type not in self.pool:
            if hasattr(validator, "_init_driver"):
                self.pool[validator_type] = validator._init_driver()
                logger.info(f"🚗 Created shared driver for {validator_type}")
            else:
                raise Exception(f"{validator_type} does not support driver injection.")
        return self.pool[validator_type]

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        logger.info("🧹 Shutting down all shared WebDrivers...")
        for key, driver in self.pool.items():
            try:
                driver.quit()
                logger.info(f"✅ Driver closed for {key}")
            except Exception as e:
                logger.warning(f"⚠️ Failed to quit driver for {key}: {e}")
