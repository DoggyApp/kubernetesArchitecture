# Use a slim Python base image
FROM python:3.13-slim-bookworm

# Install system dependencies
RUN apt-get update && apt-get install -y \
    build-essential \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Set working directory
WORKDIR /app

# Copy code and requirements
COPY requirements.txt ./
COPY prometheus-webhook.py ./app.py  

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Expose the port Flask/Gunicorn will listen on
EXPOSE 5000

# Run Gunicorn with 4 workers
CMD ["gunicorn", "-w", "4", "-b", "0.0.0.0:5000", "app:app"]
