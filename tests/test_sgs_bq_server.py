import json
import pytest
from sgs_bq_server.main import (
    mcp,
    _build_filtered_query,
    _health_payload,
    resolve_service_account_path,
    Gold_Account_Assignment_Fact,
    Gold_Enterprise_Spend_Fact,
    Gold_Executive_Dashboard,
    Gold_Supply_Chain_Intelligence,
    Gold_Vendor_Similarity,
)


@pytest.mark.asyncio
async def test_sgs_tool_discovery():
    """Verify that all 18 SGS procurement analytics tools are registered with FastMCP."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    expected_tools = [
        "Gold_Account_Assignment_Fact",
        "Gold_Content_Brand_Investment",
        "Gold_Cost_Center_Intelligence",
        "Gold_Enterprise_Spend_Fact",
        "Gold_Executive_Dashboard",
        "Gold_Financial_Attribution",
        "Gold_GL_Account_Intelligence",
        "Gold_Invoice_Fact",
        "Gold_Material_Intelligence",
        "Gold_Monthly_Spend_Trend",
        "Gold_Procurement_KPI",
        "Gold_Savings_Opportunity",
        "Gold_Shadow_IT",
        "Gold_Supplier_Risk",
        "Gold_Supply_Chain_Intelligence",
        "Gold_Vendor_Intelligence",
        "Gold_Vendor_Similarity",
        "Gold_Vendor_Spend_Classification",
    ]
    for expected in expected_tools:
        assert expected in tool_names, f"Tool {expected} not found in registered FastMCP tools"


def test_health_payload():
    """Verify healthcheck payload structure."""
    payload = _health_payload()
    assert payload["service"] == "sgs-bq-server"
    assert payload["status"] == "ok"
    assert "project_id" in payload
    assert "auth_mode" in payload


def test_build_filtered_query_no_filters():
    """Verify query construction without filters."""
    base_sql = "SELECT * FROM `my_project.my_dataset.my_table`"
    query, params = _build_filtered_query(base_sql, limit=5)
    assert query == "SELECT * FROM `my_project.my_dataset.my_table` LIMIT @limit"
    assert params == [("limit", "INT64", 5)]


def test_build_filtered_query_with_filters():
    """Verify query construction with string and comparison filters."""
    base_sql = "SELECT * FROM `my_project.my_dataset.my_table`"
    filters = [
        ("lower(company_code)", "LIKE", "1000", "STRING"),
        ("total_spend_usd", ">=", 50000.0, "FLOAT64"),
    ]
    query, params = _build_filtered_query(base_sql, limit=10, filters=filters)
    assert "WHERE lower(company_code) LIKE @f_0 AND total_spend_usd >= @f_1" in query
    assert "LIMIT @limit" in query
    assert ("f_0", "STRING", "%1000%") in params
    assert ("f_1", "FLOAT64", 50000.0) in params
    assert ("limit", "INT64", 10) in params


def test_build_filtered_query_strips_semicolon():
    """Verify query construction safely handles and removes trailing semicolons."""
    base_sql = "SELECT * FROM `my_project.my_dataset.my_table`;"
    query, params = _build_filtered_query(base_sql, limit=10)
    assert not query.endswith(";")
    assert query.endswith("LIMIT @limit")


def test_supply_chain_intelligence_filter_syntax():
    """Verify supply chain tool builds valid query parameters."""
    result = Gold_Supply_Chain_Intelligence(limit=1, company_code="AU60", purchasing_group="AU2")
    # Should execute without SQL syntax errors
    assert isinstance(result, str)
