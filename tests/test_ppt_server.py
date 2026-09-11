import base64
import io
from pptx import Presentation
from ppt_server.builder import PPTXBuilder, SlideDeck
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


def test_user_reported_payload_compiles_successfully():
    """Verify the exact user payload with delta_yoy, two_column content, bullets objects, and cards compiles without errors."""
    user_payload = {
        "slides": [
            {
                "slide_number": 1,
                "layout": "title_slide",
                "title": "Enterprise Procurement Spend Analysis",
                "subtitle": "Monthly Trends, Vendor Counts & Key KPIs",
                "date": "2023-10-01",
                "author": "AI Platform Orchestrator"
            },
            {
                "slide_number": 2,
                "layout": "kpi_grid",
                "kpi_cards": [
                    {
                        "title": "Total Enterprise Spend",
                        "value": "$4.2B",
                        "delta_yoy": "+10%",
                        "source": ["BigQuery: Gold_Executive_Dashboard"]
                    },
                    {
                        "title": "Active Suppliers",
                        "value": "1,200",
                        "delta_yoy": "+5%",
                        "source": ["BigQuery: Gold_Procurement_KPI"]
                    },
                    {
                        "title": "Savings Target",
                        "value": "$500M",
                        "delta_yoy": "+8%",
                        "source": ["BigQuery: Gold_Savings_Opportunity"]
                    },
                    {
                        "title": "Risk Index",
                        "value": "2.5",
                        "delta_yoy": "-2%",
                        "source": ["BigQuery: Gold_Supplier_Risk"]
                    }
                ]
            },
            {
                "slide_number": 3,
                "layout": "chart_and_bullets",
                "title": "Monthly Spend Trends",
                "chart": {
                    "type": "line",
                    "categories": ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct"],
                    "series": [
                        {"name": "Technology", "values": [200, 220, 230, 250, 260, 270, 280, 290, 300, 310]},
                        {"name": "Consulting", "values": [150, 160, 170, 180, 190, 200, 210, 220, 230, 240]}
                    ],
                    "labels": ["Month", "Spend ($M)"]
                },
                "bullets": [
                    {"content": "Technology spend shows steady growth throughout the year."},
                    {"content": "Consulting spend has fluctuated but remains consistent."}
                ]
            },
            {
                "slide_number": 4,
                "layout": "two_column_comparison",
                "title": "Quantitative vs Qualitative Insights",
                "left_column": {
                    "title": "Monthly Spend",
                    "content": "January: $200M<br>February: $220M<br>March: $230M<br>April: $250M<br>May: $260M<br>June: $270M<br>July: $280M<br>August: $290M<br>September: $300M<br>October: $310M"
                },
                "right_column": {
                    "title": "Vendor Risk Factors",
                    "content": "High spend on critical vendors.<br>Multiple suppliers for non-critical services."
                }
            },
            {
                "slide_number": 5,
                "layout": "bullet_cards",
                "title": "Strategic Action Pillars",
                "cards": [
                    {"title": "Improve Category Management", "content": "Optimize technology and consulting contracts for better pricing and terms."},
                    {"title": "Reduce Supplier Concentration", "content": "Diversify high-risk suppliers to mitigate financial impact."},
                    {"title": "Enhance Procurement Processes", "content": "Streamline procurement workflows to reduce cycle times and costs."}
                ]
            }
        ]
    }

    # Test when passed as direct kwargs (slides=[...])
    res1 = compile_deck_to_pptx_base64(**user_payload)
    assert res1["status"] == "success"
    assert res1["total_slides"] == 5

    # Test when passed as deck_json dict
    res2 = compile_deck_to_pptx_base64(deck_json=user_payload)
    assert res2["status"] == "success"
    assert res2["total_slides"] == 5

    # Verify binary integrity
    prs = Presentation(io.BytesIO(base64.b64decode(res1["base64_data"])))
    assert len(prs.slides) == 5
