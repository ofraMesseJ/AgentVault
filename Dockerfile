# Dockerfile - Container deployment
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies including Docker for sandboxing
RUN apt-get update && apt-get install -y \
    docker.io \
    chromium \
    chromium-driver \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
RUN playwright install chromium

# Copy application
COPY . .

# Create workspace
RUN mkdir -p workspace data/memory

# Expose Gateway port
EXPOSE 18789

# Run gateway
CMD ["python", "main.py"]