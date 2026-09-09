# PPT MCP Server (`ppt-server`)

FastMCP Presentation Server providing tools to validate, construct, and compile structured SlideDeck schemas into native, editable 16:9 widescreen PowerPoint (`.pptx`) presentations with native charts, KPI cards, and custom themes.

## Tools Exposed

1. **`compile_deck_to_pptx_base64`**: Compiles structured `SlideDeck` JSON into base64-encoded `.pptx` presentation bytes with native charts, KPI cards, and custom themes.
2. **`validate_presentation_schema`**: Validates that a JSON payload adheres to the required `SlideDeck` schema for PPTX compilation.
