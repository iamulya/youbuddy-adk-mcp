import os
import math
from datetime import datetime, timezone
from fastapi import FastAPI, HTTPException, Query
from pydantic import BaseModel, HttpUrl, Field
from typing import List, Optional
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from dotenv import load_dotenv

# Load environment variables from .env file for local development
load_dotenv()

# --- Configuration ---
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")
YOUTUBE_API_SERVICE_NAME = "youtube"
YOUTUBE_API_VERSION = "v3"

if not YOUTUBE_API_KEY:
    print("WARNING: YOUTUBE_API_KEY environment variable not set.")
    # In a real app, consider raising an error or having more robust handling.

# --- Custom Scoring Configuration ---
# These weights determine the importance of ratio vs. recency. Tune these!
RATIO_WEIGHT = 0.6
RECENCY_WEIGHT = 0.4
# Scale factor to bring timestamp magnitude closer to ratio magnitude (requires tuning)
# Timestamps are large (~1.7e9), ratios are small (often < 0.1).
# Adjust this factor based on testing to get desired balance.
RECENCY_SCALE_FACTOR = 1e10 # Example: Divide timestamp by 10 billion

# How many videos to fetch initially to find the top 10 after custom sorting
INITIAL_FETCH_COUNT = 50


# --- Pydantic Models (remain the same) ---
class VideoStatistics(BaseModel):
    viewCount: Optional[int] = None
    likeCount: Optional[int] = None
    favoriteCount: Optional[int] = None
    commentCount: Optional[int] = None

class VideoSnippet(BaseModel):
    publishedAt: str
    channelId: str
    title: str
    description: str
    channelTitle: str

class VideoItem(BaseModel):
    id: str
    url: HttpUrl
    title: str
    channelTitle: str
    publishedAt: str
    description: Optional[str] = None
    viewCount: Optional[int] = None
    likeCount: Optional[int] = None
    # You could add the calculated score here for debugging if needed
    # customScore: Optional[float] = None

# --- FastAPI App ---
app = FastAPI(
    title="YouTube Video Search API",
    description="Search for top videos based on a custom score (view/like ratio & recency).",
    version="1.1.0" # Increment version
)

# --- YouTube Service Helper (remains the same) ---
def get_youtube_service():
    if not YOUTUBE_API_KEY:
        raise HTTPException(status_code=500, detail="YouTube API Key is not configured on the server.")
    try:
        return build(YOUTUBE_API_SERVICE_NAME, YOUTUBE_API_VERSION, developerKey=YOUTUBE_API_KEY)
    except Exception as e:
        print(f"Error building YouTube service: {e}")
        raise HTTPException(status_code=500, detail="Could not initialize YouTube service.")


# --- Custom Score Calculation ---
def calculate_score(view_count: Optional[int], like_count: Optional[int], published_at_str: str) -> float:
    """Calculates a custom score based on view/like ratio and recency."""
    # Ratio Component
    ratio_score = 0.0
    if view_count and like_count and view_count > 0:
        ratio = like_count / view_count
        # Simple ratio, potentially cap or use log scale if needed
        ratio_score = ratio
    elif like_count and like_count > 0 and (view_count is None or view_count == 0):
         ratio_score = 0.01 # Assign a small default score if likes exist but views don't (unlikely but possible)

    # Recency Component
    recency_score = 0.0
    try:
        # Parse ISO 8601 string with timezone awareness
        published_dt = datetime.fromisoformat(published_at_str.replace('Z', '+00:00'))
        # Convert to POSIX timestamp (seconds since epoch, UTC)
        published_timestamp = published_dt.timestamp()
        # Scale the timestamp - adjust RECENCY_SCALE_FACTOR as needed
        recency_score = published_timestamp / RECENCY_SCALE_FACTOR
    except (ValueError, TypeError):
        print(f"Could not parse date: {published_at_str}")
        # Handle invalid date format - assign zero score for recency

    # Combined Weighted Score
    # Ensure weights sum roughly to 1 or normalize if preferred
    final_score = (RATIO_WEIGHT * ratio_score) + (RECENCY_WEIGHT * recency_score)
    return final_score


# --- API Endpoint ---
@app.get("/search", response_model=List[VideoItem])
async def search_videos_custom_score(
    query: str = Query(..., description="The search term or topic for videos."),
    max_results: int = Query(10, ge=1, le=INITIAL_FETCH_COUNT, description=f"Number of top results to return (1-{INITIAL_FETCH_COUNT}, default 10).")
):
    """
    Searches YouTube for videos based on a query and returns the top results
    sorted by a custom score combining view-to-like ratio and recency.
    """
    youtube = get_youtube_service()
    videos_with_scores = []

    try:
        # 1. Search for a larger pool of relevant videos
        print(f"Searching YouTube for '{query}', fetching up to {INITIAL_FETCH_COUNT} relevant videos...")
        search_request = youtube.search().list(
            q=query,
            part="snippet",
            type="video",
            order="relevance", # Start with relevance to get a good initial pool
            maxResults=INITIAL_FETCH_COUNT # Fetch more initially
        )
        search_response = search_request.execute()

        video_ids = []
        for item in search_response.get("items", []):
            if item.get("id", {}).get("kind") == "youtube#video":
                video_ids.append(item["id"]["videoId"])

        if not video_ids:
            print("No video IDs found in initial search.")
            return []

        print(f"Found {len(video_ids)} video IDs. Fetching details...")

        # 2. Get statistics and precise snippets for the found video IDs
        # Need to fetch in batches if video_ids > 50 (max IDs per videos().list call)
        detailed_videos = []
        for i in range(0, len(video_ids), 50):
             batch_ids = video_ids[i:i+50]
             video_details_request = youtube.videos().list(
                 part="snippet,statistics",
                 id=",".join(batch_ids)
             )
             video_details_response = video_details_request.execute()
             detailed_videos.extend(video_details_response.get("items", []))

        print(f"Fetched details for {len(detailed_videos)} videos. Calculating scores...")

        # 3. Calculate custom score for each video
        for video_data in detailed_videos:
            video_id = video_data["id"]
            snippet = video_data.get("snippet", {})
            stats = video_data.get("statistics", {})

            view_count_str = stats.get("viewCount")
            like_count_str = stats.get("likeCount")
            published_at = snippet.get("publishedAt")

            # Convert stats safely to integers
            view_count = int(view_count_str) if view_count_str else None
            like_count = int(like_count_str) if like_count_str else None

            if published_at: # Only proceed if we have a published date
                score = calculate_score(view_count, like_count, published_at)

                videos_with_scores.append({
                    "id": video_id,
                    "url": f"https://www.youtube.com/watch?v={video_id}",
                    "title": snippet.get("title", "N/A"),
                    "channelTitle": snippet.get("channelTitle", "N/A"),
                    "publishedAt": published_at,
                    "description": snippet.get("description"),
                    "viewCount": view_count,
                    "likeCount": like_count,
                    "customScore": score # Store score for sorting
                })
            else:
                print(f"Skipping video {video_id} due to missing publishedAt date.")


        # 4. Sort videos by the calculated custom score (descending)
        print(f"Calculated scores for {len(videos_with_scores)} videos. Sorting...")
        videos_with_scores.sort(key=lambda x: x["customScore"], reverse=True)

        # 5. Select the top N results (default 10, or as specified by max_results)
        top_videos = videos_with_scores[:max_results]
        print(f"Returning top {len(top_videos)} videos based on custom score.")

        # 6. Format into response model (excluding the customScore if not in the model)
        results = [VideoItem(**video) for video in top_videos]
        return results

    except HttpError as e:
        print(f"An HTTP error {e.resp.status} occurred: {e.content}")
        error_content = e.content.decode('utf-8') if isinstance(e.content, bytes) else str(e.content)
        raise HTTPException(status_code=e.resp.status, detail=f"YouTube API Error: {error_content}")
    except Exception as e:
        import traceback
        print(f"An unexpected error occurred: {e}")
        print(traceback.format_exc()) # Print stack trace for debugging
        raise HTTPException(status_code=500, detail=f"An internal server error occurred: {str(e)}")


# For local testing:
if __name__ == "__main__":
    import uvicorn
    if not YOUTUBE_API_KEY:
        print("ERROR: YOUTUBE_API_KEY environment variable not set. Create a .env file or set it.")
    else:
        print("Starting Uvicorn server for local development...")
        uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True) # Added reload=True for convenience