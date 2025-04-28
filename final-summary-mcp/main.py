import os
import logging
import uvicorn # Import uvicorn for running the app

from google import genai
# from google.genai import types # types might be needed if using GenerationConfig

from fastapi import FastAPI, HTTPException, Body, Request # Import FastAPI components
from fastapi.responses import PlainTextResponse # For the simple index route response

from fastapi_mcp import FastApiMCP

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# --- Initialize FastAPI App ---
app = FastAPI(
    title="Final Summary Service",
    description="An API to generate summaries from other text summaries.",
    version="1.0.0"
)

# --- Global Client Initialization (Optional but can be efficient) ---
# It's often better to initialize clients outside the request handler
# if the configuration doesn't change per request.
# However, we need the API key which might change or needs checking per request.
# Let's stick to initializing within the handler for this refactor to match original logic closely.

@app.post(
    "/summary", 
    operation_id="generate_final_summary", 
    description="Generate a comprehensive and coherent summary from a numbered list of key points from a number of youtube videos.",
    summary="Generate a comprehensive and coherent summary from a numbered list of key points from a number of youtube videos.",
    tags=["Final Summarization"])
async def generate_summary(
    # Use Body(...) to receive the raw request body as a string
    input_data: str = Body(..., media_type="text/plain", description="Numbered list of key points from YouTube videos.")
):
    """
    Generates a comprehensive and coherent summary from a numbered list of key points from a number of youtube videos.
    """
    #client = genai.Client(
     #   vertexai=True,
      #  project="genai-setup",
       # location="us-central1",
    #)

    gemini_api_key = os.environ.get("GEMINI_API_KEY")
    if not gemini_api_key:
        logging.error("FATAL: GEMINI_API_KEY environment variable not set.")
        # Use HTTPException for errors in FastAPI
        raise HTTPException(
            status_code=500,
            detail="Server configuration error: API key missing"
        )

    try:

        client = genai.Client(
            api_key=gemini_api_key,
        )

        input_data = request.get_data(as_text=True)

        prompt_template = f"""**Role:** You are an expert synthesizer of information.

        **Goal:** Combine information from multiple topical summaries into one comprehensive and coherent final summary.

        **Input Data:**I am providing a numbered list of key points from a number of youtube videos. Each point has a descriptive title and a summary of that aspect.

        **Your Task:**
        1.  Read through all the provided title-summary pairs.
        2.  Identify the connections and overarching narrative across the sections.
        3.  Write a **single, flowing final summary** that integrates the key information from *all* the provided summaries.
        4.  **Crucially, ensure that every concept represented by the Bolded Headings is explicitly mentioned or clearly addressed within your final summary.** Weave these topics naturally into the narrative.
        5.  The final output should be easy to read and understand, presenting a unified overview of the collective information.

        **Generate the Final Summary based on the provided input data:**
        {input_data}
        """

        logging.info(f"Prompt Template: {prompt_template}")

        model_name = "gemini-2.5-flash-preview-04-17"
        
        response = client.models.generate_content(
            model=f"models/{model_name}", # Model name format [5]
            contents=prompt_template # Pass the formatted string [5]
            # Optional generation config can be added here, e.g.,
            # generation_config=types.GenerationConfig(temperature=0.7) [8]
        )

        logging.info("Summary generated successfully.")
        # FastAPI automatically handles JSON serialization for dicts
        return {
            "summary": response.text
        }

    except Exception as e:
        logging.error(f"Error during Gemini API call or processing: {e}", exc_info=True)
        raise HTTPException(
            status_code=503, # Service Unavailable might be more apt than 500
            detail=f"Error generating summary: {e}"
        )

@app.get("/", tags=["Health Check"], response_class=PlainTextResponse)
async def index():
    """Basic index route to confirm service is running."""
    # Return plain text directly
    return "YouTube Summary Service is running. Use POST /summary endpoint."

mcp = FastApiMCP(
    app,
    name="Final Summarization Service MCP",
    include_tags=["Final Summarization"],
    description="MCP server for generating a comprehensive summary from other text summaries",
    describe_full_response_schema=True,  # Describe the full response JSON-schema instead of just a response example
    describe_all_responses=True,  # Describe all the possible responses instead of just the success (2XX) response
)

mcp.mount()

# This is used for local development testing ONLY
# An ASGI server like Uvicorn/Hypercorn will run the app in production (Cloud Run)
if __name__ == "__main__":
    port = int(os.environ.get("PORT", 8080))
    # Use uvicorn.run for local development
    # --reload enables auto-reloading on code changes
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
    # Note: Replace "main" with the actual name of your Python file (e.g., "app_fastapi.py" -> "app_fastapi:app")