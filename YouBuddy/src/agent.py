import logging
import os
from contextlib import AsyncExitStack
from typing import List, Optional, Tuple

from google.adk.agents import Agent
from google.adk.tools import BaseTool

# Import Secret Manager client
try:
  from google.cloud import secretmanager
except ImportError:
  raise ImportError(
      "Please install google-cloud-secret-manager: pip install"
      " google-cloud-secret-manager"
  )

# Import MCPToolset and connection parameters
try:
  from google.adk.tools.mcp_tool import MCPToolset
  from google.adk.tools.mcp_tool.mcp_session_manager import SseServerParams

  # StdioServerParameters can be used if connecting to local command-line MCP servers
  # from mcp import StdioServerParameters
except ImportError as e:
  # Provide a helpful error message if MCP dependencies are missing
  raise ImportError(
      "MCP Toolset requires 'google-adk[mcp]' extras or Python 3.10+."
      " Please install dependencies and ensure you are using Python 3.10 or"
      " higher."
  ) from e

logger = logging.getLogger(__name__)

# --- Configuration ---
# Load MCP URLs from environment variables (defined in .env)
MCP_URL_GET_CHANNEL_VIDEOS = os.getenv("MCP_URL_GET_CHANNEL_VIDEOS")
MCP_URL_GET_PLAYLIST_VIDEOS = os.getenv("MCP_URL_GET_PLAYLIST_VIDEOS")
MCP_URL_SUMMARIZE_VIDEO = os.getenv("MCP_URL_SUMMARIZE_VIDEO")
MCP_URL_COMBINE_SUMMARIES = os.getenv("MCP_URL_COMBINE_SUMMARIES")

# Load Secret Manager resource name from environment
GOOGLE_API_KEY_SECRET_RESOURCE_NAME = os.getenv(
    "GOOGLE_API_KEY_SECRET_RESOURCE_NAME"
)

# --- Secret Manager Helper ---

def fetch_secret(secret_resource_name: str) -> Optional[str]:
  """Fetches a secret from Google Cloud Secret Manager."""
  if not secret_resource_name:
    logger.warning(
        "Secret resource name (GOOGLE_API_KEY_SECRET_RESOURCE_NAME) not"
        " provided in .env file."
    )
    return None
  try:
    client = secretmanager.SecretManagerServiceClient()
    response = client.access_secret_version(name=secret_resource_name)
    secret_value = response.payload.data.decode("UTF-8")
    logger.info(
        "Successfully fetched secret from %s", secret_resource_name
    )
    return secret_value
  except Exception as e:
    logger.error(
        "Failed to fetch secret '%s': %s", secret_resource_name, e, exc_info=True
    )
    # Depending on your requirements, you might want to raise the error
    # raise RuntimeError(f"Could not fetch secret: {e}") from e
    return None

# Ensure URLs are configured
if not all([
    MCP_URL_GET_CHANNEL_VIDEOS,
    MCP_URL_GET_PLAYLIST_VIDEOS,
    MCP_URL_SUMMARIZE_VIDEO,
    MCP_URL_COMBINE_SUMMARIES,
]):
  raise ValueError(
      "One or more MCP Tool URLs are missing. Please set them in the .env file."
  )

# --- Tool Loading (Asynchronous) ---

async def load_mcp_tools(
    exit_stack: AsyncExitStack,
) -> List[BaseTool]:
  """Loads tools from multiple MCP servers asynchronously."""
  all_tools = []
  mcp_connections = {
      "get_channel_videos": SseServerParams(url=MCP_URL_GET_CHANNEL_VIDEOS),
      "get_playlist_videos": SseServerParams(url=MCP_URL_GET_PLAYLIST_VIDEOS),
      "summarize_video": SseServerParams(url=MCP_URL_SUMMARIZE_VIDEO),
      "combine_summaries": SseServerParams(url=MCP_URL_COMBINE_SUMMARIES),
  }

  logger.info("Connecting to MCP servers and loading tools...")
  for name, params in mcp_connections.items():
    logger.info(f"Loading tools from {name} at {params.url}...")
    try:
      # Create a toolset for each connection, managed by the *same* exit_stack
      toolset = MCPToolset(connection_params=params, exit_stack=exit_stack)
      # Enter the context manager for the toolset
      await exit_stack.enter_async_context(toolset)
      # Load tools from this specific toolset
      tools = await toolset.load_tools()
      all_tools.extend(tools)
      logger.info(
          f"Successfully loaded {len(tools)} tools from {name}:"
          f" {[t.name for t in tools]}"
      )
    except Exception as e:
      logger.error(f"Failed to load tools from {name} ({params.url}): {e}")
      # Decide if you want to raise the error or continue loading other tools
      # raise  # Uncomment to stop if one connection fails

  if not all_tools:
    logger.warning(
        "No MCP tools were loaded. Check MCP server URLs and availability."
    )

  logger.info(f"Total MCP tools loaded: {len(all_tools)}")
  return all_tools


# --- Agent Definition (Asynchronous Loading Wrapper) ---

# ADK's `adk web` command can handle an awaitable root_agent.
# This awaitable should return a tuple: (agent_instance, async_exit_stack)
async def load_youbuddy_agent() -> Tuple[Agent, AsyncExitStack]:
  """Asynchronously loads MCP tools and creates the YouBuddy agent."""

  # AsyncExitStack manages the cleanup of MCP connections
  exit_stack = AsyncExitStack()
  try:

    logger.info("Attempting to fetch GOOGLE_API_KEY from Secret Manager...")
    secret_value = fetch_secret(GOOGLE_API_KEY_SECRET_RESOURCE_NAME)
    if secret_value:
      os.environ["GOOGLE_API_KEY"] = secret_value
      logger.info("GOOGLE_API_KEY environment variable set from Secret Manager.")
    else:
      # If fetching failed and no key exists, raise an error before agent creation
      raise ValueError(
          "Failed to get GOOGLE_API_KEY from Secret Manager and it's not set"
          " in the environment. Agent cannot initialize."
      )
      
    # Load all tools from the configured MCP servers
    mcp_tools = await load_mcp_tools(exit_stack)

    # Define the main agent
    youbuddy_agent = Agent(
        model="gemini-2.5-flash-preview-04-17", # Or your preferred model
        name="youbuddy_agent",
        description=(
            "An agent specializing in fetching and summarizing YouTube videos"
            " from channels or playlists using specialized tools."
        ),
        instruction=f"""You are YouBuddy, an expert YouTube assistant created by Amulya Bhatia. Your goal is to help users by fetching videos and creating summaries based on their requests.

You have access to the following tools:
{chr(10).join([f'- {tool.name}: {tool.description}' for tool in mcp_tools if tool.description])}

Based on the user's request:
1.  Determine if you need videos from a specific channel and date OR from a specific playlist. Use the appropriate tool (`get_channel_videos` or `get_playlist_videos`) to fetch the list of video URLs or IDs.
2.  For each relevant video identified in step 1, use the `summarize_video` tool to get its summary.
3.  If multiple summaries were generated, use the `combine_summaries` tool to create a final, consolidated summary.
4.  Present the final summary to the user. If only one video was summarized, present that summary directly.
5.  If a tool fails, inform the user you couldn't complete the request due to a tool issue.
""",
        tools=mcp_tools, # Pass the loaded MCP tools here
    )
    # Return the agent instance AND the exit_stack for lifecycle management
    return youbuddy_agent, exit_stack
  except Exception as e:
    # Ensure the exit_stack is closed even if agent creation fails
    await exit_stack.aclose()
    logger.exception("Failed to initialize YouBuddy agent.")
    raise RuntimeError("Failed to initialize YouBuddy agent") from e

# Assign the *awaitable function* to root_agent. ADK will handle awaiting it.
root_agent = load_youbuddy_agent()
