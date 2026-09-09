from __future__ import annotations

import argparse
import base64
import json
import logging
import os
from typing import Any

from fastmcp import FastMCP
from ppt_server.builder import PPTXBuilder, SlideDeck

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ppt-server")

# Initialize FastMCP Server
mcp = FastMCP("ppt-server")

HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("MCP_PORT", "8050")))
TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")


@mcp.tool(
    name="compile_deck_to_pptx_base64",
    description="Compiles a structured SlideDeck JSON schema into a base64-encoded 16:9 widescreen PowerPoint (.pptx) presentation with native charts, KPI cards, and custom themes.",
)
def compile_deck_to_pptx_base64(deck_json: str) -> dict[str, Any]:
    """Compiles SlideDeck JSON into a base64-encoded .pptx file."""
    try:
        data = json.loads(deck_json) if isinstance(deck_json, str) else deck_json
        deck = SlideDeck.model_validate(data)
    except Exception as e:
        logger.error(f"Invalid slide deck JSON: {e}")
        return {
            "error": f"Invalid SlideDeck schema: {e}",
            "status": "failed",
        }

    builder = PPTXBuilder(theme_name=deck.theme)
    stream = builder.build_deck(deck)
    raw_bytes = stream.read()
    b64_content = base64.b64encode(raw_bytes).decode("utf-8")

    clean_title = "".join(c if c.isalnum() or c in ("-", "_") else "_" for c in deck.deck_title)
    filename = f"{clean_title or 'presentation'}.pptx"

    return {
        "status": "success",
        "filename": filename,
        "mime_type": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
        "size_bytes": len(raw_bytes),
        "base64_data": b64_content,
        "total_slides": len(deck.slides),
    }


@mcp.tool(
    name="validate_presentation_schema",
    description="Validates that a JSON payload adheres to the required SlideDeck schema for PPTX compilation.",
)
def validate_presentation_schema(deck_json: str) -> dict[str, Any]:
    """Validates SlideDeck JSON structure."""
    try:
        data = json.loads(deck_json) if isinstance(deck_json, str) else deck_json
        deck = SlideDeck.model_validate(data)
        return {
            "valid": True,
            "deck_title": deck.deck_title,
            "slide_count": len(deck.slides),
            "theme": deck.theme,
        }
    except Exception as e:
        return {
            "valid": False,
            "error": str(e),
        }


def main():
    parser = argparse.ArgumentParser(description="PPT FastMCP Server")
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
        logger.info(f"Starting ppt-server on SSE at http://{args.host}:{args.port}")
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
