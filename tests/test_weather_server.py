import pytest
from weather_server.main import (
    get_current_weather,
    get_weather_by_datetime_range,
    get_weather_details,
    get_air_quality,
    get_air_quality_details,
    get_current_datetime,
    get_timezone_info,
    convert_time,
    mcp,
)


@pytest.mark.asyncio
async def test_weather_fastmcp_tools_registered() -> None:
    expected_tools = [
        "get_current_weather",
        "get_weather_by_datetime_range",
        "get_weather_details",
        "get_air_quality",
        "get_air_quality_details",
        "get_current_datetime",
        "get_timezone_info",
        "convert_time",
    ]
    tools = await mcp.list_tools()
    registered_tool_names = [t.name for t in tools]
    for tool_name in expected_tools:
        assert tool_name in registered_tool_names, f"Missing tool: {tool_name}"


@pytest.mark.asyncio
async def test_fastmcp_time_tools() -> None:
    res_dt = await get_current_datetime(timezone_name="UTC")
    assert "UTC" in res_dt

    res_tz = await get_timezone_info(timezone_name="America/New_York")
    assert "America/New_York" in res_tz

    res_conv = await convert_time(
        datetime_str="2026-09-25 12:00:00",
        from_timezone="UTC",
        to_timezone="Asia/Tokyo",
    )
    assert "Asia/Tokyo" in res_conv


@pytest.mark.asyncio
async def test_fastmcp_weather_and_air_quality_tools() -> None:
    res_weather = await get_current_weather(city="Tokyo")
    assert "Tokyo" in res_weather or "temperature" in res_weather.lower()

    res_weather_json = await get_weather_details(city="Paris")
    assert "Paris" in res_weather_json

    res_aq = await get_air_quality(city="London")
    assert "London" in res_aq
