import logging
import os
from typing import List, Dict, Union

from fastapi import FastAPI, HTTPException, Query
from pytube import Playlist
from pytube.exceptions import RegexMatchError, PytubeError

from fastapi_mcp import FastApiMCP

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="YouTube Playlist Video URL Extractor",
    description="API to fetch all video URLs from a public YouTube playlist.",
    version="1.0.0"
)

@app.get(
    "/health",
    tags=["Health Check"],
    summary="Check if the API is running",
    response_model=Dict[str, str]
)
async def health_check():
    """
    Simple health check endpoint.
    """
    return {"status": "ok"}

@app.get(
    "/playlist/videos",
    operation_id="get_playlist_videos",
    tags=["YouTube"],
    description="Get all video URLs from a YouTube Playlist URL",
    summary="Get all video URLs from a YouTube Playlist URL",
    response_model=Dict[str, Union[str, int, List[str]]]
)
async def get_playlist_videos(
    playlist_url: str = Query(
        ..., # Make parameter required
        description="The full URL of the public YouTube playlist (e.g., https://www.youtube.com/playlist?list=PLxxxx...)",
        example="https://www.youtube.com/playlist?list=PL6gx4Cwl9DGCkg2uj3PxUWhMDuTw3VKjM" # Example: Google I/O 2023 playlist
    )
):
    """
    Retrieves all video URLs from a given public YouTube playlist URL.

    - **playlist_url**: The full URL of the target YouTube playlist. Must be public.
    """
    logger.info(f"Received request for playlist URL: {playlist_url}")

    try:
        playlist = Playlist(playlist_url)

        # Accessing video_urls triggers the network request if not already cached.
        # This might take a moment for long playlists.
        logger.info(f"Fetching videos for playlist: '{playlist.title}' (owner: {playlist.owner})")

        # Check if playlist is empty or inaccessible (sometimes throws KeyError instead of returning empty)
        # Accessing len or first video can trigger fetch
        if not playlist.video_urls:
             # Attempting to access length might be needed to trigger potential errors for empty/private playlists
             try:
                 logger.warning(f"Playlist '{playlist.title}' appears empty or inaccessible after fetching URLs.")
                 # Raise exception here as pytube might not always throw one for empty lists
                 raise PytubeError(f"Playlist '{playlist.title}' is empty or video URLs could not be retrieved.")
             except KeyError as ke:
                 logger.error(f"KeyError encountered, potentially private or invalid playlist: {playlist_url}. Error: {ke}")
                 raise HTTPException(
                    status_code=404,
                    detail=f"Playlist not found or is private. Could not retrieve video information. Pytube KeyError: {ke}"
                ) from ke

        video_urls = list(playlist.video_urls) # Convert generator to list
        count = len(video_urls)
        logger.info(f"Successfully retrieved {count} video URLs from playlist '{playlist.title}'.")

        return {
            "playlist_title": playlist.title,
            "playlist_url": playlist.playlist_url,
            "video_count": count,
            "video_urls": video_urls
        }

    except RegexMatchError as e:
        logger.error(f"Invalid YouTube Playlist URL format: {playlist_url}. Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=400,
            detail=f"Invalid YouTube Playlist URL format provided. Please check the URL. Error: {e}"
        )
    except KeyError as e:
         # This often happens if the playlist is private, deleted, or pytube fails to parse data
        logger.error(f"KeyError encountered for playlist: {playlist_url}. Might be private, deleted, or parsing failed. Error: {e}", exc_info=True)
        raise HTTPException(
            status_code=404, # Or 403 if definitively private, but 404 is safer
            detail=f"Playlist not found, is private, or data could not be parsed. KeyError: {e}"
        )
    except PytubeError as e:
        # Catch specific Pytube errors (network issues, extraction problems)
        logger.error(f"A Pytube error occurred for playlist {playlist_url}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500, # Internal Server Error or specific code based on error type
            detail=f"An error occurred while fetching playlist data: {e}"
        )
    except Exception as e:
        # Catch any other unexpected errors
        logger.error(f"An unexpected error occurred for playlist {playlist_url}: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected internal server error occurred: {e}"
        )

# Optional: Add root endpoint for basic info or link to docs
@app.get("/", include_in_schema=False)
async def root():
    return {"message": "Welcome to the YouTube Playlist Extractor API!", "docs": "/docs"}

mcp = FastApiMCP(
    app,
    name="YouTube Video Summarization Service MCP",
    include_tags=["YouTube"],
    description="MCP server for the YouTube Video Summarization Service",
    describe_full_response_schema=True,  # Describe the full response JSON-schema instead of just a response example
    describe_all_responses=True,  # Describe all the possible responses instead of just the success (2XX) response
)

mcp.mount()

# Uvicorn entry point for local testing (optional, Dockerfile CMD is primary for Cloud Run)
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080)) # Use PORT env var if available, default 8080
    uvicorn.run(app, host="0.0.0.0", port=port)