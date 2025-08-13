# Dockerfile
FROM mcr.microsoft.com/playwright/python:v1.53.0-noble
WORKDIR /app

# System has Playwright + browsers preinstalled in this image.
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
CMD ["celery","-A","tasks","worker","-l","INFO","-Q","auth"]
