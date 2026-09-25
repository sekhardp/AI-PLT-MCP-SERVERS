---
name: weather-air-quality
description: Comprehensive real-time weather forecasts, air quality indices, and timezone intelligence guide powered by the Weather MCP Server and Open-Meteo.
---

# Weather & Air Quality Intelligence Skill Guide

This skill governs AI agent interactions with the Weather MCP Server (`weather-server`), providing live weather conditions, multi-day forecast analytics, air quality index evaluations, and timezone conversions.

---

## 1. Core Tool Reference

| Tool Name | Key Parameters | Description & Return Format |
| :--- | :--- | :--- |
| `get_current_weather` | `city` (string, required) | Natural language summary of current temperature, feels-like, humidity, dew point, wind speed/direction, gusts, UV index, and visibility. |
| `get_weather_by_datetime_range` | `city` (string), `start_date` (YYYY-MM-DD), `end_date` (YYYY-MM-DD) | Hourly forecast/historical weather analysis across a specified date window. |
| `get_weather_details` | `city` (string, required) | Complete raw JSON telemetry from Open-Meteo for structured data processing. |
| `get_air_quality` | `city` (string), `variables` (list[string], optional) | Air quality report with pollutant concentrations (PM2.5, PM10, O3, NO2, CO, SO2) and WHO/EPA health recommendations. |
| `get_air_quality_details` | `city` (string, required) | Detailed raw JSON air quality measurements. |
| `get_current_datetime` | `timezone_name` (string, required) | Current ISO timestamp for any timezone (e.g. `'America/New_York'`, `'UTC'`, `'Asia/Tokyo'`). |
| `get_timezone_info` | `timezone_name` (string, required) | Timezone metadata, local time, UTC time, and UTC offset hours. |
| `convert_time` | `datetime_str` (string), `from_timezone` (string), `to_timezone` (string) | Accurate cross-timezone timestamp conversion and time difference calculation. |

---

## 2. Tool Invocation Decision Tree

1. **"What's the weather in [City] right now?"**
   - Use `get_current_weather(city="<City>")`.
2. **"Will it rain in [City] this weekend / next 3 days?"**
   - Use `get_weather_by_datetime_range(city="<City>", start_date="<YYYY-MM-DD>", end_date="<YYYY-MM-DD>")`.
3. **"Is the air quality safe for running / sensitive groups in [City]?"**
   - Use `get_air_quality(city="<City>")` or specify pollutants `variables=["pm2_5", "pm10", "ozone"]`.
4. **"What time is it in Tokyo when it's 2 PM in New York?"**
   - Use `convert_time(datetime_str="YYYY-MM-DD 14:00:00", from_timezone="America/New_York", to_timezone="Asia/Tokyo")`.
5. **Programmatic / Multi-factor JSON Analysis**:
   - Use `get_weather_details` and `get_air_quality_details`.

---

## 3. Best Practices & Parameter Formatting

- **City Names**: Provide English city names (e.g. `"Tokyo"`, `"London"`, `"New York"`, `"San Francisco"`).
- **Date Formatting**: Always use ISO 8601 format: `YYYY-MM-DD`.
- **Timezone Strings**: Use standard IANA timezone identifiers (e.g. `'UTC'`, `'America/New_York'`, `'America/Chicago'`, `'Europe/London'`, `'Asia/Tokyo'`, `'Asia/Kolkata'`).
- **Zero API Key Required**: All weather tools run against open-access Open-Meteo APIs with automatic geocoding.

---

## 4. Executive Response Standard

When presenting weather and air quality intelligence to users, structure the response cleanly:

1. **Executive Summary**: 1–2 sentence overview of current conditions or upcoming weather patterns.
2. **Key Metrics Table**: Temperature, Humidity, Wind & Gusts, UV Index, and Air Quality Index (AQI/PM2.5).
3. **Actionable Insights / Advisories**: Recommendations regarding rain probability, outdoor activities, clothing, or air quality precautions.
