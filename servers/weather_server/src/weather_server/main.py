from __future__ import annotations

import argparse
import logging
import os
from typing import Any, Optional

from fastmcp import FastMCP
from mcp_weather_server.tools.tools_weather import (
    GetCurrentWeatherToolHandler,
    GetWeatherByDateRangeToolHandler,
    GetWeatherDetailsToolHandler,
)
from mcp_weather_server.tools.tools_air_quality import (
    GetAirQualityToolHandler,
    GetAirQualityDetailsToolHandler,
)
from mcp_weather_server.tools.tools_time import (
    GetCurrentDateTimeToolHandler,
    GetTimeZoneInfoToolHandler,
    ConvertTimeToolHandler,
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("weather-server")

# FastMCP Server Instance (discovered automatically by FastMCP Inspector & MCP CLI)
mcp = FastMCP("weather-server")
server = mcp
app = mcp

HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("MCP_PORT", "8070")))
TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")


@mcp.tool(
    name="get_current_weather",
    description="Retrieves comprehensive current weather information for a given city including temperature, feels-like, humidity, dew point, wind speed/gusts, precipitation, UV index, and visibility.",
)
async def get_current_weather(city: str) -> str:
    """Get current weather information for a city."""
    handler = GetCurrentWeatherToolHandler()
    res = await handler.run_tool({"city": city})
    return res[0].text if res else "No weather data returned."


@mcp.tool(
    name="get_weather_by_datetime_range",
    description="Retrieves hourly weather information and analysis for a specified city between start and end dates (YYYY-MM-DD).",
)
async def get_weather_by_datetime_range(city: str, start_date: str, end_date: str) -> str:
    """Get hourly weather forecast and historical trends for a date range."""
    handler = GetWeatherByDateRangeToolHandler()
    res = await handler.run_tool({
        "city": city,
        "start_date": start_date,
        "end_date": end_date,
    })
    return res[0].text if res else "No forecast data returned."


@mcp.tool(
    name="get_weather_details",
    description="Retrieves detailed raw weather telemetry for a specified city formatted as a structured JSON string for programmatic consumption.",
)
async def get_weather_details(city: str) -> str:
    """Get detailed raw JSON weather metrics for a city."""
    handler = GetWeatherDetailsToolHandler()
    res = await handler.run_tool({"city": city})
    return res[0].text if res else "{}"


@mcp.tool(
    name="get_air_quality",
    description="Retrieves current air quality analysis with pollutant concentrations (PM2.5, PM10, O3, NO2, CO, SO2) and health advisories for a specified city.",
)
async def get_air_quality(city: str, variables: Optional[list[str]] = None) -> str:
    """Get current air quality report with health advisories."""
    handler = GetAirQualityToolHandler()
    args: dict[str, Any] = {"city": city}
    if variables:
        args["variables"] = variables
    res = await handler.run_tool(args)
    return res[0].text if res else "No air quality data returned."


@mcp.tool(
    name="get_air_quality_details",
    description="Retrieves detailed raw air quality metrics as a structured JSON string for a specified city.",
)
async def get_air_quality_details(city: str) -> str:
    """Get detailed raw JSON air quality measurements."""
    handler = GetAirQualityDetailsToolHandler()
    res = await handler.run_tool({"city": city})
    return res[0].text if res else "{}"


@mcp.tool(
    name="get_current_datetime",
    description="Retrieves the current date and time in any specified timezone (e.g. 'UTC', 'America/New_York', 'Asia/Tokyo').",
)
async def get_current_datetime(timezone_name: str) -> str:
    """Get current date and time for a given timezone."""
    handler = GetCurrentDateTimeToolHandler()
    res = await handler.run_tool({"timezone_name": timezone_name})
    return res[0].text if res else "{}"


@mcp.tool(
    name="get_timezone_info",
    description="Retrieves timezone information and UTC offset details for a given timezone name.",
)
async def get_timezone_info(timezone_name: str) -> str:
    """Get timezone offset and geographical information."""
    handler = GetTimeZoneInfoToolHandler()
    res = await handler.run_tool({"timezone_name": timezone_name})
    return res[0].text if res else "{}"


@mcp.tool(
    name="convert_time",
    description="Converts a datetime string from one timezone to another (e.g. '2026-09-25 14:30:00' from 'UTC' to 'Asia/Kolkata').",
)
async def convert_time(datetime_str: str, from_timezone: str, to_timezone: str) -> str:
    """Convert a datetime string between timezones."""
    handler = ConvertTimeToolHandler()
    res = await handler.run_tool({
        "datetime_str": datetime_str,
        "from_timezone": from_timezone,
        "to_timezone": to_timezone,
    })
    return res[0].text if res else "{}"


def main() -> None:
    parser = argparse.ArgumentParser(description="Weather & Air Quality FastMCP Server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default=TRANSPORT,
        help="Transport protocol: 'stdio' (default) or 'sse'",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=PORT,
        help=f"Port for SSE server (default: {PORT})",
    )
    parser.add_argument(
        "--host",
        default=HOST,
        help=f"Host address (default: {HOST})",
    )
    args = parser.parse_args()

    if args.transport == "sse":
        logger.info(f"Starting weather-server on SSE at http://{args.host}:{args.port}")
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        logger.info("Starting weather-server on stdio transport...")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
