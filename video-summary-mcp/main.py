import os
import logging
import base64
import binascii # For catching base64 decoding errors
import uvicorn

from google import genai
from google.genai import types

from fastapi import FastAPI, HTTPException, Body # Import Body
from pydantic import BaseModel, Field, HttpUrl # Import HttpUrl for better validation (optional)

from fastapi_mcp import FastApiMCP

# --- Configure Logging ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

# --- Initialize FastAPI App ---
app = FastAPI(
    title="Video Summarization Service",
    description="An API service that uses Google Gemini to summarize videos from a URL.",
    version="1.0.0",
)

# --- Environment Variable Check ---
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
if not GEMINI_API_KEY:
    logger.error("FATAL: GEMINI_API_KEY environment variable not set.")

class SummaryRequest(BaseModel):
    video_url: HttpUrl

# --- Pydantic Models for Request/Response Schemas ---
class SummaryResponse(BaseModel):
    summary: str = Field(..., description="The generated summary of the video.")

class ErrorDetail(BaseModel):
    error: str = Field(..., description="Description of the error.")

# --- API Endpoints ---
@app.post(
    '/summary',
    response_model=SummaryResponse,
    responses={
        400: {"model": ErrorDetail, "description": "Bad Request (e.g., invalid URL format in body, Gemini cannot access URL)"},
        422: {"model": ErrorDetail, "description": "Validation Error (e.g., missing 'video_url' in body)"}, # FastAPI uses 422 for Pydantic errors
        500: {"model": ErrorDetail, "description": "Internal Server Error (e.g., API key missing, unexpected Gemini API error)"},
        503: {"model": ErrorDetail, "description": "Gemini API Service Unavailable or Processing Error"},
    },
    summary="Generate Video Summary",
    operation_id="get_youtube_video_summary",
    description="Accepts a JSON request body containing the video URL (`video_url`) and returns a text summary.",
    tags=["Summarization"] # Tag for grouping in OpenAPI docs
)
async def generate_summary(
    request_data: SummaryRequest = Body()
):
    """
    FastAPI route handler for GET /summary requests.
    Validates input, calls Gemini API, and returns the summary.
    """
    if not GEMINI_API_KEY:
        logger.error("GEMINI_API_KEY is not configured.")
        raise HTTPException(status_code=500, detail="Server configuration error: API key missing")

    client = genai.Client(
        api_key=GEMINI_API_KEY,
    )

    video_url = str(request_data.video_url)
    logging.info(f"Summary video url: {video_url}")

    msg1_video1 = types.Part.from_uri(
        file_uri=video_url,
        mime_type="video/*",
    )

    model = "gemini-2.5-flash-preview-04-17"
    contents = [
        types.Content(
        role="user",
        parts=[
            msg1_video1,
            types.Part.from_text(text="""identify the main topics and provide concise summary for each""")
        ]
        ),
    ]
    generate_content_config = types.GenerateContentConfig(
        temperature = 1,
        top_p = 1,
        seed = 0,
        max_output_tokens = 65535,
        response_modalities = ["TEXT"],
        safety_settings = [types.SafetySetting(
        category="HARM_CATEGORY_HATE_SPEECH",
        threshold="OFF"
        ),types.SafetySetting(
        category="HARM_CATEGORY_DANGEROUS_CONTENT",
        threshold="OFF"
        ),types.SafetySetting(
        category="HARM_CATEGORY_SEXUALLY_EXPLICIT",
        threshold="OFF"
        ),types.SafetySetting(
        category="HARM_CATEGORY_HARASSMENT",
        threshold="OFF"
        )],
    )

    response = ""
    for chunk in client.models.generate_content_stream(
        model = model,
        contents = contents,
        config = generate_content_config,
        ):
        print(chunk.text, end="")
        response = response + chunk.text

    return SummaryResponse(summary=response)
    

@app.get(
    '/',
    summary="Health Check",
    description="Basic index route to confirm the service is running.",
    tags=["System"]
)
async def index():
    """Basic index route to confirm service is running."""
    return {"message": "Video Summary Service is running. Use the /summary endpoint."}

mcp = FastApiMCP(
    app,
    name="YouTube Video Summarization Service MCP",
    description="MCP server for the YouTube Video Summarization Service",
    include_tags=["Summarization"],
    describe_full_response_schema=True,  # Describe the full response JSON-schema instead of just a response example
    describe_all_responses=True,  # Describe all the possible responses instead of just the success (2XX) response
)

mcp.mount()

# --- Run the App (for local development) ---
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    logger.info(f"Starting FastAPI server on host 0.0.0.0:{port}")
    # Use uvicorn to run the FastAPI app
    # reload=True is useful for development, disable for production
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)