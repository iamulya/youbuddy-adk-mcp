# YouBuddy - ADK Agent with MCP Tools for YouTube Summarization

This project implements "YouBuddy," an AI agent built using the Google Agent Development Kit (ADK). YouBuddy assists users by fetching and summarizing YouTube videos from channels or playlists. It leverages several backend microservices exposed as ADK MCP (Message-Oriented Communications Protocol) Tool Servers.

## Overview

YouBuddy acts as a central orchestrator. When a user makes a request (e.g., "Summarize the latest videos from channel X" or "Give me a summary of the videos in playlist Y"), the agent:

1.  Determines the user's need (channel videos by date vs. playlist videos vs. simply creating summary for one video).
2.  Calls the appropriate MCP tool server to retrieve the list of relevant video URLs in case a playlist or channel is provided.
3.  Calls another MCP tool server to generate a summary for each video URL retrieved.
4.  If multiple summaries were generated, calls a final MCP tool server to combine them into a single, coherent summary.
5.  Presents the final result (single summary or combined summary) back to the user.

The system uses Google's Gemini models for summarization tasks and the YouTube Data API for fetching video metadata.

## Features

*   **Fetch Channel Videos:** Retrieve video URLs from a specific YouTube channel published on a given date.
*   **Fetch Playlist Videos:** Retrieve all video URLs from a given public YouTube playlist.
*   **Individual Video Summarization:** Generate a concise summary for a single YouTube video using Gemini (handles video modality).
*   **Combined Summarization:** Synthesize multiple individual video summaries into one comprehensive final summary using Gemini.
*   **Agent Orchestration:** Uses an ADK agent to manage the workflow and interact with the user.
*   **Microservice Architecture:** Backend functionality is split into distinct, containerized FastAPI services (MCP Tool Servers).
*   **Secure API Key Handling:** Uses Google Cloud Secret Manager to securely fetch the necessary API key for the agent.

## Architecture

The system consists of the following main components:

1.  **YouBuddy ADK Agent (`YouBuddy/`):**
    *   The central conversational agent.
    *   Built with `google-adk`.
    *   Uses Gemini (`gemini-pro` or similar) for reasoning and function calling.
    *   Connects to MCP Tool Servers defined in `.env`.
    *   Fetches the Google API Key (Gemini/Vertex) from Secret Manager.
    *   Orchestrates calls to the tools based on user requests.

2.  **MCP Tool Servers (`*-mcp/`):**
    *   Independent FastAPI microservices exposing specific functionalities as ADK Tools.
    *   Each service is containerized using Docker for easy deployment (e.g., to Cloud Run).
    *   **`youtube-urls-mcp/`:** Fetches video URLs for a specific channel and date using the YouTube Data API. Requires `YOUTUBE_API_KEY`.
    *   **`playlist-videos-mcp/`:** Fetches all video URLs from a YouTube playlist using `pytube`.
    *   **`video-summary-mcp/`:** Generates a summary for a single video URL using the Gemini API (multimodal). Requires `GEMINI_API_KEY`.
    *   **`final-summary-mcp/`:** Takes multiple text summaries and generates a final combined summary using the Gemini API. Requires `GEMINI_API_KEY`.

3.  **Video Selection Service (`video-selection/`):**
    *   A *standalone* FastAPI microservice ( **not currently integrated as an MCP tool used by the YouBuddy agent**).
    *   Searches YouTube based on a query and ranks videos using a custom score (view/like ratio and recency).
    *   Uses the YouTube Data API. Requires `YOUTUBE_API_KEY`.
    *   Containerized using Docker.

4.  **Google Cloud Services:**
    *   **Secret Manager:** Securely stores the API key needed by the agent.
    *   **Cloud Run (Recommended):** Target platform for deploying the containerized FastAPI services (MCP Tools and Video Selection).
    *   **Google AI / Vertex AI:** Provides the Gemini models used by the agent and summarization services.
    *   **YouTube Data API:** Used by services to fetch video information.

## Directory Structure

```
iamulya-youbuddy-adk-mcp/
├── README.md                 # This file
├── final-summary-mcp/        # MCP Tool: Combine summaries
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── playlist-videos-mcp/      # MCP Tool: Get playlist videos
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── video-selection/          # Standalone Service: Search/rank videos
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── video-summary-mcp/        # MCP Tool: Summarize single video
│   ├── Dockerfile
│   ├── main.py
│   └── requirements.txt
├── YouBuddy/                 # ADK Agent
│   ├── .env                  # Agent configuration (needs creation)
│   └── src/
│       ├── __init__.py
│       ├── agent.py          # Agent logic and tool loading
│       └── requirements.txt
└── youtube-urls-mcp/         # MCP Tool: Get channel videos by date
    ├── Dockerfile
    ├── main.py
    └── requirements.txt
```

## Setup & Prerequisites

1.  **Google Cloud Project:** Create or use an existing Google Cloud project.
2.  **Enable APIs:** In your GCP project, enable the following APIs:
    *   Secret Manager API
    *   Vertex AI API (or Google Generative Language API if using AI Studio keys directly)
    *   YouTube Data API v3
3.  **API Keys:**
    *   **Gemini API Key:** Obtain an API key for Gemini (either via Google AI Studio or by using Vertex AI service accounts/authentication).
    *   **YouTube Data API Key:** Create an API key restricted to the YouTube Data API v3.
4.  **Secret Manager:**
    *   Store your Gemini API Key (or the key the Agent needs) as a secret in Secret Manager.
    *   Note the **Resource Name** of the secret version (e.g., `projects/YOUR_PROJECT_NUMBER/secrets/YOUR_SECRET_ID/versions/LATEST`).
    *   Ensure the environment where the agent runs (your local machine or service account) has permission to access this secret (`secretmanager.secrets.access` role).
5.  **Software:**
    *   Python 3.10+ (Required for `google-adk[mcp]`)
    *   Docker
    *   Google Cloud SDK (`gcloud`) installed and authenticated (`gcloud auth login`, `gcloud config set project YOUR_PROJECT_ID`).
    *   `pip install google-adk[all]` (Installs the ADK CLI and necessary libraries).

## Configuration

1.  **MCP Services & Video Selection Service:**
    *   These services require API keys passed as environment variables during deployment.
    *   `final-summary-mcp`: Needs `GEMINI_API_KEY`.
    *   `playlist-videos-mcp`: No external API keys needed (uses `pytube`).
    *   `video-selection`: Needs `YOUTUBE_API_KEY`.
    *   `video-summary-mcp`: Needs `GEMINI_API_KEY`.
    *   `youtube-urls-mcp`: Needs `YOUTUBE_API_KEY`.
    *   When deploying to Cloud Run, set these environment variables in the service configuration.

2.  **YouBuddy Agent (`YouBuddy/.env`):**
    *   Navigate to the `YouBuddy/` directory.
    *   Create a file named `.env`.
    *   Copy the contents from the provided `YouBuddy/.env` template into your new file.
    *   **Fill in the values:**
        *   `MCP_URL_...`: Replace `<URL_FOR_..._TOOL>` with the actual HTTPS URLs of your deployed MCP tool services on Cloud Run (e.g., `https://final-summary-mcp-abcdef-uc.a.run.app`).
        *   `GOOGLE_API_KEY_SECRET_RESOURCE_NAME`: Paste the full Secret Manager resource name for your Gemini API Key secret.
        *   `GOOGLE_GENAI_USE_VERTEXAI`: Keep as `0` if using a Google AI Studio API key fetched from Secret Manager. Set to `1` if authenticating via Vertex AI mechanisms (may require code changes in agent).

## Deployment (Cloud Run Example)

Deploy each service (`final-summary-mcp`, `playlist-videos-mcp`, `video-selection`, `video-summary-mcp`, `youtube-urls-mcp`) to Cloud Run:

```bash
# Replace YOUR_PROJECT_ID, SERVICE_NAME, and appropriate API_KEY values

# Example for final-summary-mcp:
cd final-summary-mcp
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/final-summary-mcp .
gcloud run deploy final-summary-mcp \
    --image gcr.io/YOUR_PROJECT_ID/final-summary-mcp \
    --platform managed \
    --region YOUR_REGION \
    --allow-unauthenticated \
    --set-env-vars="GEMINI_API_KEY=YOUR_GEMINI_API_KEY" # Or use Secret Manager integration for env vars

# Example for youtube-urls-mcp:
cd ../youtube-urls-mcp
gcloud builds submit --tag gcr.io/YOUR_PROJECT_ID/youtube-urls-mcp .
gcloud run deploy youtube-urls-mcp \
    --image gcr.io/YOUR_PROJECT_ID/youtube-urls-mcp \
    --platform managed \
    --region YOUR_REGION \
    --allow-unauthenticated \
    --set-env-vars="YOUTUBE_API_KEY=YOUR_YOUTUBE_DATA_API_KEY" # Or use Secret Manager

# Repeat for other services (playlist-videos, video-summary, video-selection)
# Note: playlist-videos-mcp doesn't need external API keys set via env vars.
# Note: video-selection needs YOUTUBE_API_KEY.
# Note: video-summary-mcp needs GEMINI_API_KEY.

cd ..
```

*   Make sure `--allow-unauthenticated` is appropriate for your security needs. If you require authentication, you'll need to adjust the agent's MCP connection logic.
*   After deployment, note down the service URLs (`*.run.app`) and update the `YouBuddy/.env` file accordingly.

## Running the Agent

1.  Navigate to the `YouBuddy/` directory.
2.  Ensure your `.env` file is correctly configured with the deployed MCP service URLs and the Secret Manager resource name.
3.  Ensure your local environment is authenticated with Google Cloud (`gcloud auth application-default login` might be needed for Secret Manager access).
4.  Install the agent's dependencies: `pip install -r src/requirements.txt`
5.  Start the ADK agent web server:
    ```bash
    adk web
    ```
6.  Open your web browser and navigate to the URL provided by the `adk web` command (usually `http://localhost:8000`).

## Usage

Interact with YouBuddy through the web interface. Try requests like:

*   "Get videos from channel `UC_x5XG1OV2P6uZZ5FSM9Ttw` published on 2024-01-15 and summarize them." (Google Developers channel)
*   "Summarize the YouTube playlist: `https://www.youtube.com/playlist?list=PLIivdWyY5sqK5SRR9erGeAx_OTQpHy8cR`."
*   "Can you summarize this video? https://www.youtube.com/watch?v=VIDEO_ID"

The agent will use its tools to process your request and provide the relevant information or summaries.
