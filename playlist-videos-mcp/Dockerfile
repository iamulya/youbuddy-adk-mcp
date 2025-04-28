# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set environment variables
# Prevents Python from writing pyc files to disc (recommended)
ENV PYTHONDONTWRITEBYTECODE 1
# Ensures Python output is sent straight to terminal (useful for logging)
ENV PYTHONUNBUFFERED 1

# Set the working directory in the container
WORKDIR /app

# Install system dependencies if any (e.g., build tools if needed by some Python packages)
# RUN apt-get update && apt-get install -y --no-install-recommends some-package && rm -rf /var/lib/apt/lists/*

# Copy the requirements file into the container at /app
COPY requirements.txt .

# Install Python dependencies
# --no-cache-dir reduces image size
# --upgrade pip ensures we have the latest pip version
RUN pip install --no-cache-dir --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Copy the rest of the application code into the container at /app
COPY . .

# Expose the port the app runs on (Cloud Run uses the PORT env var, often 8080)
# This EXPOSE line is informational for humans/other tools; Cloud Run handles the actual port mapping.
EXPOSE 8080

# Define the command to run the application
# Cloud Run injects the PORT environment variable, which Uvicorn should listen on.
# Uvicorn needs to listen on 0.0.0.0 to accept connections from outside the container.
# The port here (8080) acts as a default if PORT isn't set, but Cloud Run *will* set PORT.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]