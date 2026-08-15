import argparse
import asyncio
import json
import os
import logging
from typing import List, Dict, Any

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

import mcp.types as types
from mcp.server import Server
from mcp.server.lowlevel import NotificationOptions
from mcp.server.models import InitializationOptions
from mcp.server.sse import SseServerTransport
from mcp.server.stdio import stdio_server
from mcp.client.sse import sse_client
from mcp.client.session import ClientSession

# 1. Initialize Logging
logger = logging.getLogger("registry-gateway")
logging.basicConfig(level=logging.INFO)

# Config path resolver
CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")

def load_servers_config() -> List[Dict[str, str]]:
    """
    Loads downstream server URLs from config.json.
    Also supports dynamic environment variable overrides (highly useful for cloud deployments).
    Format: SERVER_WEATHER_SERVER_URL=http://weather-service:8000/sse
    """
    servers = []
    
    # Read config.json
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                servers = data.get("servers", [])
        except Exception as e:
            logger.error(f"Failed to read config file {CONFIG_PATH}: {e}")
            
    # Process Environment Overrides (e.g. for VMs/Cloud Run)
    for key, value in os.environ.items():
        if key.startswith("SERVER_") and key.endswith("_URL"):
            # Translate e.g., SERVER_WEATHER_SERVER_URL -> weather-server
            server_name = key[7:-4].lower().replace("_", "-")
            
            # Update existing, or append new
            found = False
            for srv in servers:
                if srv["name"] == server_name or srv["name"].replace("-", "_") == server_name:
                    srv["url"] = value
                    found = True
                    break
            if not found:
                servers.append({"name": server_name, "url": value})
                
    return servers

# 2. Create the low-level MCP server instance
server = Server("registry-gateway")

@server.list_tools()
async def handle_list_tools() -> types.ListToolsResult:
    """
    Called by the client (LLM). Queries all configured sub-servers over the network,
    namespaces their tools with a double-underscore ('__') to avoid name collisions,
    and returns the combined list of tools.
    """
    servers = load_servers_config()
    logger.info(f"Listing tools: aggregating {len(servers)} sub-servers...")
    
    all_tools = []
    for srv in servers:
        name = srv["name"]
        url = srv["url"]
        logger.info(f"Fetching tools from '{name}' at {url}...")
        try:
            # Dynamically connect to the sub-server using the SSE client
            async with sse_client(url=url) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    
                    for tool in tools_result.tools:
                        # Namespace prefix the tool name, e.g., weather_server__get_weather
                        prefixed_name = f"{name.replace('-', '_')}__{tool.name}"
                        
                        cloned_tool = types.Tool(
                            name=prefixed_name,
                            description=tool.description or "",
                            inputSchema=tool.inputSchema
                        )
                        all_tools.append(cloned_tool)
                        
                    logger.info(f"Loaded {len(tools_result.tools)} tools from '{name}'")
        except Exception as e:
            logger.error(f"Skipping offline server '{name}' at {url}: {e}")
            # We don't fail the whole listing request if one sub-server is down.
            
    return types.ListToolsResult(tools=all_tools)

@server.call_tool()
async def handle_call_tool(name: str, arguments: Dict[str, Any] | None) -> types.CallToolResult:
    """
    Called by the client to run a tool.
    Extracts the server name from the prefix, routes the execution to that specific
    server over HTTP/SSE, and returns the response.
    """
    logger.info(f"Call tool request received for '{name}' with arguments {arguments}")
    
    if "__" not in name:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Error: Invalid tool name format '{name}'. Expected 'server_name__tool_name'.")],
            isError=True
        )
        
    prefixed_server_name, original_tool_name = name.split("__", 1)
    
    # Find the target server config
    servers = load_servers_config()
    target_server = None
    for srv in servers:
        if srv["name"] == prefixed_server_name or srv["name"].replace("-", "_") == prefixed_server_name:
            target_server = srv
            break
            
    if not target_server:
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Error: Sub-server '{prefixed_server_name}' is not configured.")],
            isError=True
        )
        
    url = target_server["url"]
    logger.info(f"Routing call '{original_tool_name}' to sub-server '{target_server['name']}' at {url}...")
    
    try:
        # Establish connection to the target server and invoke the tool
        async with sse_client(url=url) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream) as session:
                await session.initialize()
                result = await session.call_tool(original_tool_name, arguments or {})
                return result
    except Exception as e:
        logger.error(f"Failed to execute tool on '{target_server['name']}': {e}")
        return types.CallToolResult(
            content=[types.TextContent(type="text", text=f"Error reaching sub-server '{target_server['name']}'. Details: {str(e)}")],
            isError=True
        )

# 3. FastAPI Web Application for hosting the SSE/HTTP endpoint
app = FastAPI(title="MCP Registry Gateway")

# Enable CORS (useful for development/debugging tools)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# SseServerTransport manages the connections and translates them into streams
sse = SseServerTransport("/messages")

@app.get("/sse")
async def sse_endpoint(request: Request):
    """Client initiates a persistent event stream connection here."""
    async with sse.connect_sse(request.scope, request.receive, request._send) as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="registry-gateway",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

from starlette.routing import Mount
app.router.routes.append(Mount("/messages", app=sse.handle_post_message))

async def run_stdio():
    """Runs the gateway in stdio mode (local pipe execution)."""
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="registry-gateway",
                server_version="0.1.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )

# 4. Gateway CLI Entrypoint
def main():
    parser = argparse.ArgumentParser(description="Run the MCP Registry Gateway")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport protocol: 'stdio' (default, local process) or 'sse' (network)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=8001,
        help="Port to run the HTTP/SSE server (only used for '--transport sse')"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host address to run the HTTP/SSE server (default: 0.0.0.0)"
    )
    args = parser.parse_args()

    if args.transport == "sse":
        logger.info(f"Starting Registry Gateway on SSE transport at http://{args.host}:{args.port}/sse")
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        logger.info("Starting Registry Gateway on stdio transport...")
        asyncio.run(run_stdio())

if __name__ == "__main__":
    main()
