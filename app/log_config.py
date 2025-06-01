import os
import sys

from loguru import logger 


# Remove default handler
logger.remove()


log_dir = os.path.join(os.path.dirname(__file__), "logs", "job_validator")
print("📁 Log directory:", log_dir)
os.makedirs(log_dir, exist_ok=True) 
# Console output
logger.add(
    sys.stdout,
    level="DEBUG",
    colorize=True,
    format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
)

# File output (rotates at 10 MB, retains 7 days, compressed)
log_file_path = os.path.join(log_dir, "job_validator.log")

logger.add(
    "logs/job_scraper.log",
    rotation="10 MB",
    retention="7 days",
    compression="zip",
    level="DEBUG",
    enqueue=True,
)

# ✅ Print current logger handlers info (for debug)
print("🛠️ Logger setup complete:")
print(f"  📄 Log file path: {log_file_path}")
print(f"  🖥️ Console logging: ENABLED")
print(f"  📦 File logging: ENABLED (rotation @ 10MB, retention 7d, compressed)")

# Test log
logger.debug("Logger successfully configured.")
