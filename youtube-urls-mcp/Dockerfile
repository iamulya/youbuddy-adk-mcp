# Use an official Python runtime as a parent image
FROM python:3.10-slim

# Set the working directory in the container
WORKDIR /app

# Copy the dependencies file to the working directory
COPY requirements.txt .

# Install any needed packages specified in requirements.txt
# --no-cache-dir: Disables the cache, reducing image size
# --compile: Compiles Python source files to .pyc, which can sometimes speed up startup
RUN pip install --no-cache-dir --compile -r requirements.txt

# Copy the rest of the application code to the working directory
COPY . .

# Expose the port the app runs on (FastAPI default, Uvicorn will listen here)
# This is more for documentation; Cloud Run uses the PORT env var.
EXPOSE 8080

# Command to run the application using Uvicorn
# Cloud Run sets the PORT environment variable, so we use that.
# --host 0.0.0.0 makes the server accessible from outside the container.
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8080"]