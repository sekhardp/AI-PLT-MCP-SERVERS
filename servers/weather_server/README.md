# Weather MCP Server

A Model Context Protocol (MCP) server providing real-time weather forecasts, air quality indices, and timezone utilities powered by Open-Meteo.

## Tools Included

### Weather Tools
- `get_current_weather`: Current temperature, feels like, humidity, wind speed, gusts, UV index, cloud cover, visibility.
- `get_weather_by_datetime_range`: Hourly and multi-day forecast analytics.
- `get_weather_details`: Comprehensive JSON structure of raw metrics.

### Air Quality Tools
- `get_air_quality`: Pollutant concentrations (PM2.5, PM10, O3, NO2, SO2, CO) and EPA/WHO health advisories.
- `get_air_quality_details`: Detailed raw JSON air quality telemetry.

### Time & Timezone Tools
- `get_current_datetime`: Current time in any timezone.
- `get_timezone_info`: Timezone details and offset.
- `convert_time`: Accurate timezone conversion.

## Transports
- **stdio**: Default mode for local CLI / agents.
- **sse**: Server-Sent Events mode for web / Cloud Run on port 8080 (`/sse` & `/messages/`).
- **streamable-http**: Modern Streamable HTTP endpoint on `/mcp`.
