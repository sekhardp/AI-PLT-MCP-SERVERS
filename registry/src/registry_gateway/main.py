import argparse
import asyncio
import json
import os
import logging
from typing import List, Dict, Any, Optional

import httpx

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
from mcp.shared._httpx_utils import create_mcp_http_client

# 1. Initialize Logging
logger = logging.getLogger("registry-gateway")
logging.basicConfig(level=logging.INFO)


def _create_mcp_http_client(**kwargs) -> Any:
    """Create MCP-compatible AsyncClient that forces HTTPS on redirects for cloud-hosted services."""
    async def force_https_redirect_hook(request: Any) -> None:
        if request.url.scheme == "http" and request.url.host not in ("localhost", "127.0.0.1"):
            request.url = request.url.copy_with(scheme="https")

    client = create_mcp_http_client(
        headers=kwargs.get("headers"),
        timeout=kwargs.get("timeout") or 60.0,
        auth=kwargs.get("auth"),
    )
    client.event_hooks["request"].append(force_https_redirect_hook)
    return client

# Config path resolver (configurable via env var)
CONFIG_PATH = os.environ.get("REGISTRY_CONFIG_PATH", os.path.join(os.path.dirname(__file__), "config.json"))

def load_servers_config() -> List[Dict[str, str]]:
    """
    Loads downstream server URLs from config.json or environment variables.
    Environment variables override or supply downstream servers:
    Format: SERVER_<NAME>_URL=http://<host>:<port>/sse
    e.g. SERVER_RAG_SERVER_URL=https://rag-mcp-xyz.a.run.app/sse
    """
    servers: List[Dict[str, str]] = []
    
    # Read config.json if present
    if os.path.exists(CONFIG_PATH):
        try:
            with open(CONFIG_PATH, "r") as f:
                data = json.load(f)
                servers = data.get("servers", [])
        except Exception as e:
            logger.error(f"Failed to read config file {CONFIG_PATH}: {e}")
            
    # Process Environment Overrides / Additions (e.g. for Cloud Run / Docker)
    for key, value in os.environ.items():
        if key.startswith("SERVER_") and key.endswith("_URL"):
            # Translate e.g., SERVER_RAG_SERVER_URL -> rag-server
            server_name = key[7:-4].lower().replace("_", "-")
            
            # Update existing, or append new
            found = False
            for srv in servers:
                if srv["name"] == server_name or srv["name"].replace("-", "_") == server_name.replace("-", "_"):
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
            async with sse_client(url=url, httpx_client_factory=_create_mcp_http_client) as (read_stream, write_stream):
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
        async with sse_client(url=url, httpx_client_factory=_create_mcp_http_client) as (read_stream, write_stream):
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

@app.get("/health")
async def health_check():
    """
    Gateway health check endpoint.
    """
    return {"status": "ok", "service": "registry-gateway"}

@app.get("/servers")
async def get_servers():
    """
    List all configured downstream servers.
    """
    try:
        servers = load_servers_config()
        return {"servers": servers, "count": len(servers)}
    except Exception as e:
        return {"error": f"Failed to load servers: {str(e)}"}

@app.get("/servers/status")
async def get_servers_status():
    """
    Ping each registered server's SSE endpoint and report connection status.
    """
    servers = load_servers_config()
    results = []
    
    async with httpx.AsyncClient(timeout=3.0) as client:
        for srv in servers:
            name = srv["name"]
            url = srv["url"]
            try:
                # Test connection by streaming the GET request.
                # This retrieves headers and returns immediately without reading the infinite SSE stream body.
                start_time = asyncio.get_event_loop().time()
                async with client.stream("GET", url) as response:
                    status = "online" if response.status_code == 200 else f"offline (HTTP {response.status_code})"
                    latency = asyncio.get_event_loop().time() - start_time
            except Exception as e:
                status = f"offline ({type(e).__name__})"
                latency = None
            
            results.append({
                "name": name,
                "url": url,
                "status": status,
                "latency_seconds": latency
            })
            
    return {"servers": results, "count": len(results)}

@app.get("/tools")
async def get_tools(tag: Optional[str] = None):
    """
    List all aggregated tools from downstream servers, optionally filtered by tag.
    """
    servers = load_servers_config()
    all_tools = []
    
    for srv in servers:
        name = srv["name"]
        url = srv["url"]
        try:
            async with sse_client(url=url, httpx_client_factory=_create_mcp_http_client) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools_result = await session.list_tools()
                    
                    for tool in tools_result.tools:
                        prefixed_name = f"{name.replace('-', '_')}__{tool.name}"
                        tool_dict = tool.model_dump()
                        tool_dict["name"] = prefixed_name
                        
                        # Extract tags from meta or _meta
                        tags = []
                        meta = tool_dict.get("meta") or tool_dict.get("_meta")
                        if isinstance(meta, dict):
                            fastmcp = meta.get("fastmcp", {})
                            if isinstance(fastmcp, dict):
                                tags = fastmcp.get("tags", [])
                                
                        tool_dict["tags"] = tags
                        all_tools.append(tool_dict)
        except Exception as e:
            logger.error(f"Error fetching tools from '{name}' at {url}: {e}")
            
    if tag:
        all_tools = [t for t in all_tools if tag.lower() in [tg.lower() for tg in t.get("tags", [])]]
        
    return {"tools": all_tools, "count": len(all_tools)}

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
