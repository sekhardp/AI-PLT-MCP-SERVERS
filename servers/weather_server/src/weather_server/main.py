import argparse
import httpx
from fastmcp import FastMCP
from fastmcp_docs import FastMCPDocs

# 1. Initialize the FastMCP server
mcp = FastMCP("weather-server")
docs = FastMCPDocs(mcp,title="Weather Server Tools")

# 2. Define a tool using the @mcp.tool decorator
@mcp.tool(tags=["weather"])
async def get_weather(latitude: float, longitude: float) -> str:
    """
    Get the current weather forecast for a given latitude and longitude.
    
    Args:
        latitude: Latitude coordinates (e.g. 37.7749 for San Francisco)
        longitude: Longitude coordinates (e.g. -122.4194 for San Francisco)
    """
    # The US National Weather Service (NWS) API is a free, public API.
    # It requires a custom User-Agent header to identify requests.
    url = f"https://api.weather.gov/points/{latitude},{longitude}"
    headers = {"User-Agent": "mcp-weather-server/1.0 (contact@example.com)"}
    
    async with httpx.AsyncClient() as client:
        try:
            # Step A: Get grid metadata for the coordinates
            response = await client.get(url, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            # Step B: Retrieve the forecast URL from grid metadata
            forecast_url = data["properties"]["forecast"]
            
            # Step C: Get the actual forecast periods
            forecast_response = await client.get(forecast_url, headers=headers)
            forecast_response.raise_for_status()
            forecast_data = forecast_response.json()
            
            # Step D: Format and return the next 3 forecast periods
            periods = forecast_data["properties"]["periods"]
            results = []
            for period in periods[:3]:
                results.append(
                    f"{period['name']}: {period['temperature']}°{period['temperatureUnit']} - {period['detailedForecast']}"
                )
            return "\n".join(results)
            
        except httpx.HTTPStatusError as e:
            return f"Error fetching weather data: HTTP status {e.response.status_code}"
        except Exception as e:
            return f"Error: Could not retrieve weather. details: {str(e)}"

# 3. CLI Argument Parser to support stdio (local) and SSE (Cloud Run/VM) transports
def main():
    parser = argparse.ArgumentParser(description="Run the weather MCP server")
    parser.add_argument(
        "--transport", 
        choices=["stdio", "sse"], 
        default="stdio", 
        help="Transport protocol: 'stdio' (default, local process) or 'sse' (network)"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=8000, 
        help="Port to run the HTTP/SSE server (only used for '--transport sse')"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host address to run the HTTP/SSE server (default: 0.0.0.0)"
    )
    args = parser.parse_args()

    # Set up Swagger/API documentation endpoints
    import asyncio
    asyncio.run(docs.setup())

    if args.transport == "sse":
        print(f"Starting weather-server on SSE transport at http://{args.host}:{args.port}")
        # FastMCP spins up an ASGI/Uvicorn HTTP server internally under the hood
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        # Runs using standard input/output for local IDE/client connections
        mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
