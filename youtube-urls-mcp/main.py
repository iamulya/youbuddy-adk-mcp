import os
import logging
from datetime import datetime, timedelta, timezone, date
from typing import List, Optional

# --- FastAPI Imports ---
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.responses import JSONResponse
import uvicorn # For running the app locally

# --- Google API Imports ---
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Pydantic Model for Response Structure ---
from pydantic import BaseModel, HttpUrl

from fastapi_mcp import FastApiMCP

# Configure logging - FastAPI doesn't configure root logger by default
# Same configuration as before is fine.
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__) # Get a specific logger

# --- Configuration ---
API_SERVICE_NAME = "youtube"
API_VERSION = "v3"

# --- Initialize FastAPI App ---
app = FastAPI(
    title="YouTube Video Fetcher API",
    description="Fetches YouTube video URLs for a specific channel on a given date.",
    version="1.0.0"
)

# --- Pydantic Response Model ---
# This improves documentation and ensures response consistency
class VideoResponse(BaseModel):
    channel_id: str
    date: str # Keep as string to match input format
    video_urls: List[HttpUrl] # Use HttpUrl for validation

# --- Dependency for API Key ---
# Using Depends makes testing easier and centralizes key retrieval
def get_api_key() -> str:
    """Retrieves the YouTube API Key from environment variables."""
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if not api_key:
        logger.error("FATAL: YOUTUBE_API_KEY environment variable not set.")
        # Raise HTTPException here, which FastAPI automatically handles
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: API key missing"
        )
    return api_key

# --- YouTube Service Logic (mostly unchanged) ---
# Consider adding caching here if the service is built often
# Using Depends helps manage the service lifecycle if needed later (e.g., reuse)
def get_youtube_service(api_key: str = Depends(get_api_key)) -> build:
    """Builds and returns the YouTube API service object."""
    try:
        youtube = build(API_SERVICE_NAME, API_VERSION, developerKey=api_key)
        logger.info("Successfully built YouTube service.")
        return youtube
    except Exception as e:
        logger.error(f"Error building YouTube service: {e}")
        # Re-raise as HTTPException for FastAPI to handle
        raise HTTPException(
            status_code=503, # Service Unavailable might be appropriate
            detail=f"Could not connect to YouTube API: {e}"
        )

def get_channel_videos_for_date(youtube: build, channel_id: str, target_date_str: str) -> List[str]:
    """
    Fetches YouTube video URLs uploaded by a specific channel on a specific date.
    (Core logic remains the same as the Flask version)

    Args:
        youtube: Authorized YouTube API service instance.
        channel_id: The ID of the YouTube channel (starts with UC...).
        target_date_str: The target date in 'YYYY-MM-DD' format.

    Returns:
        A list of video URLs.

    Raises:
        ValueError: If the date format is invalid.
        HttpError: If a YouTube API error occurs. (Handled by the caller route)
        Exception: For other unexpected errors. (Handled by the caller route)
    """
    video_urls = []
    try:
        # Validate and parse the date (raises ValueError if invalid)
        target_date = datetime.strptime(target_date_str, "%Y-%m-%d").date()
    except ValueError as e:
        logger.warning(f"Invalid date format provided: '{target_date_str}'")
        raise ValueError(f"Invalid date format: '{target_date_str}'. Use YYYY-MM-DD.") from e # Re-raise to be caught by route

    # Define the time range for the target date in UTC
    start_datetime_utc = datetime(target_date.year, target_date.month, target_date.day, 0, 0, 0, tzinfo=timezone.utc)
    end_datetime_utc = start_datetime_utc + timedelta(days=1)

    published_after = start_datetime_utc.isoformat().replace("+00:00", "Z")
    published_before = end_datetime_utc.isoformat().replace("+00:00", "Z")

    logger.info(f"Searching for videos in channel '{channel_id}' between {published_after} and {published_before}")

    next_page_token = None
    try:
        while True:
            # This block can raise HttpError
            request_api = youtube.search().list(
                part="snippet",
                channelId=channel_id,
                type="video",
                order="date",
                publishedAfter=published_after,
                publishedBefore=published_before,
                maxResults=50,
                pageToken=next_page_token
            )
            response = request_api.execute()

            for item in response.get("items", []):
                video_id = item.get("id", {}).get("videoId")
                published_at_str = item.get("snippet", {}).get("publishedAt")
                if video_id and published_at_str:
                     try:
                         # More robust parsing: Handles potential timezone variations better
                         published_dt_utc = datetime.fromisoformat(published_at_str.replace('Z', '+00:00')).astimezone(timezone.utc)
                         # Compare dates directly
                         if published_dt_utc.date() == target_date:
                             video_url = f"https://www.youtube.com/watch?v={video_id}"
                             video_urls.append(video_url)
                             logger.info(f"Found video: {video_url} published at {published_at_str}")
                         else:
                              logger.debug(f"Video {video_id} returned by API but published on {published_dt_utc.date()} (outside target {target_date}). Skipping.")
                     except ValueError:
                         logger.warning(f"Could not parse published date '{published_at_str}' for video {video_id}. Skipping.")

            next_page_token = response.get("nextPageToken")
            if not next_page_token:
                break

        logger.info(f"Found {len(video_urls)} videos for channel '{channel_id}' on {target_date_str}.")
        return video_urls

    except HttpError as e:
        # Let the route handler catch and process HttpError
        raise e
    except Exception as e:
        # Let the route handler catch unexpected errors
        raise e


# --- FastAPI Routes ---

@app.get("/", tags=["General"], summary="Health Check")
async def index():
    """Basic index route to confirm service is running."""
    return {"message": "YouTube Video Fetcher Service is running. Use /docs for API details."}

@app.get(
    "/videos",
    response_model=VideoResponse, # Use the Pydantic model for response structure & validation
    tags=["YouTube Videos"],
    operation_id="get_youtube_videos_for_channel_date",
    description="Retrieves a list of YouTube video URLs published by a specific channel on a specified date",
    summary="Retrieves a list of YouTube video URLs published by a specific channel on a specified date"
)
async def handle_get_videos(
    channel_id: str = Query(
        ..., # Ellipsis means the parameter is required
        description="The ID of the YouTube channel (e.g., UC...).",
        min_length=5 # Example validation
    ),
    target_date_str: str = Query(
        ...,
        alias="date", # Allows using ?date=YYYY-MM-DD in the URL
        description="Target date in YYYY-MM-DD format.",
        regex=r"^\d{4}-\d{2}-\d{2}$" # Regex validation for format
    ),
    youtube_service: build = Depends(get_youtube_service) # Inject YouTube service
):
    """
    Retrieves a list of YouTube video URLs published by a specific channel
    on a specified date.
    """
    logger.info(f"Received request for channel_id='{channel_id}', date='{target_date_str}'")

    try:
        video_list = get_channel_videos_for_date(youtube_service, channel_id, target_date_str)

        # Return data matching the VideoResponse model
        return VideoResponse(
            channel_id=channel_id,
            date=target_date_str,
            video_urls=video_list
        )

    except ValueError as e:
        # Handle invalid date format from get_channel_videos_for_date
        logger.warning(f"Bad request: Invalid date format '{target_date_str}'. {e}")
        raise HTTPException(status_code=400, detail=str(e)) # 400 Bad Request
    except HttpError as e:
        logger.error(f"YouTube API HTTP error {e.resp.status} occurred: {e.content}")
        status_code = e.resp.status
        detail = f"YouTube API error: Status {status_code}"
        http_status_code = 502 # Default to 502 Bad Gateway for upstream API errors

        if status_code == 403:
            detail += " (Possible quota exceeded or API key issue)"
            http_status_code = 403 # Forbidden
        elif status_code == 404:
             detail += f" (Channel '{channel_id}' possibly not found)"
             http_status_code = 404 # Not Found
        elif status_code >= 500:
            detail += " (YouTube server error)"
            http_status_code = 503 # Service Unavailable

        raise HTTPException(status_code=http_status_code, detail=detail)
    except Exception as e:
        logger.exception(f"An unexpected error occurred processing request for channel '{channel_id}', date '{target_date_str}'")
        raise HTTPException(
            status_code=500,
            detail="An internal server error occurred"
        )

mcp = FastApiMCP(
    app,
    name="Fetch YouTube Videos for a channel and date MCP",
    include_tags=["YouTube Videos"],
    description="MCP server to fetch YouTube Videos for a channel and date",
    describe_full_response_schema=True,  # Describe the full response JSON-schema instead of just a response example
    describe_all_responses=True,  # Describe all the possible responses instead of just the success (2XX) response
)

mcp.mount()

# --- Main Execution Block (for local development) ---
# Use Uvicorn to run the FastAPI app
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting Uvicorn server on host 0.0.0.0, port {port}")
    # Use reload=True for development, disable for production-like testing
    # Set log_level based on your preference or environment
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True, log_level="info")
    # To run without auto-reload (like in production):
    # uvicorn.run("main:app", host="0.0.0.0", port=port, log_level="info")