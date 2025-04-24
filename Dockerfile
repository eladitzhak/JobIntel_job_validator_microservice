FROM python:3.11-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Chrome + ChromeDriver
RUN apt-get update && apt-get install -y \
    wget curl unzip gnupg2 ca-certificates \
    chromium chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Set env for Chrome & chromedriver
ENV CHROME_BIN=/usr/bin/chromium
ENV PATH="/usr/lib/chromium/:${PATH}"

# Set workdir
WORKDIR /app

# Install Python packages
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy rest of the app
COPY . .

# 🔧 Add this to make `app` package resolvable
ENV PYTHONPATH=/app

# CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"]

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port 8000 ${UVICORN_RELOAD}"]

