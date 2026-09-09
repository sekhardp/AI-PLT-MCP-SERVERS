import base64
import io
from pptx import Presentation
from ppt_server.builder import PPTXBuilder, SlideDeck, Slide, KPICard, ChartConfig, ChartSeries
from ppt_server.main import compile_deck_to_pptx_base64, validate_presentation_schema


def get_sample_deck_dict() -> dict:
    return {
        "deck_title": "Q3 Procurement Spend & Supplier Risk Review",
        "deck_subtitle": "Executive Analytics Briefing",
        "theme": "dark",
        "author": "AI Procurement Agent",
        "slides": [
            {
                "slide_number": 1,
                "layout": "title_slide",
                "title": "Q3 Procurement Spend & Supplier Risk Review",
                "subtitle": "Executive Analytics Briefing",
            },
            {
                "slide_number": 2,
                "layout": "kpi_grid",
                "title": "Procurement KPI Dashboard",
                "subtitle": "Q3 Core Benchmarks",
                "kpi_cards": [
                    {"label": "Total Spend", "value": "$84.2M", "change": "-4.1% YoY", "trend": "up"},
                    {"label": "Active Vendors", "value": "1,420", "change": "-8% YoY", "trend": "up"},
                    {"label": "Identified Savings", "value": "$6.4M", "change": "+22% QoQ", "trend": "up"},
                ],
                "bullet_points": [
                    "Vendor consolidation reduced active tail suppliers by 8%.",
                    "Early payment discounts delivered $1.2M in annualized savings.",
                ],
                "sources": ["BigQuery: Gold_Procurement_KPI"],
            },
            {
                "slide_number": 3,
                "layout": "chart_and_bullets",
                "title": "Monthly Spend Distribution by Category",
                "subtitle": "Category-level volume trends",
                "chart": {
                    "chart_type": "bar",
                    "title": "Spend ($M)",
                    "categories": ["Technology", "Consulting", "Logistics", "Marketing"],
                    "series": [
                        {"name": "Actual Spend", "values": [28.4, 18.2, 22.1, 15.5]},
                        {"name": "Budgeted", "values": [30.0, 16.0, 24.0, 18.0]},
                    ],
                },
                "bullet_points": [
                    "Technology spend stayed below budget due to SaaS rationalization.",
                    "Consulting overage driven by enterprise ERP migration project.",
                ],
                "sources": ["BigQuery: Gold_Monthly_Spend_Trend"],
            },
        ],
    }


def test_validate_presentation_schema():
    payload = get_sample_deck_dict()
    res = validate_presentation_schema(payload)
    assert res["valid"] is True
    assert res["deck_title"] == "Q3 Procurement Spend & Supplier Risk Review"
    assert res["slide_count"] == 3


def test_compile_deck_to_pptx_base64():
    payload = get_sample_deck_dict()
    res = compile_deck_to_pptx_base64(payload)
    assert res["status"] == "success"
    assert res["filename"].endswith(".pptx")
    assert res["size_bytes"] > 0
    assert "base64_data" in res

    # Decode and verify with python-pptx
    file_bytes = io.BytesIO(base64.b64decode(res["base64_data"]))
    prs = Presentation(file_bytes)
    assert len(prs.slides) == 3


def test_validate_presentation_schema_invalid():
    res = validate_presentation_schema("not-valid-json")
    assert res["valid"] is False
    assert "error" in res


def test_compile_deck_invalid_schema():
    res = compile_deck_to_pptx_base64({"bad": "data"})
    assert res["status"] == "failed"
    assert "error" in res

