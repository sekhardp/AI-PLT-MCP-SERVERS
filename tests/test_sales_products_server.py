from __future__ import annotations

import pytest
from sales_products_server.main import (
    mcp,
    get_dataset_metadata,
    get_dimension_catalog,
    get_executive_sales_summary,
    get_inventory_restock_alerts,
    execute_sql_query,
    execute_custom_analytics_query,
    _rewrite_and_guard_sql,
)


@pytest.mark.asyncio
async def test_sales_products_tool_discovery():
    """Verify that the Golden Hybrid sales & products analytics tools are registered with FastMCP."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    expected_tools = [
        "get_dataset_metadata",
        "get_dimension_catalog",
        "get_executive_sales_summary",
        "get_inventory_restock_alerts",
        "execute_sql_query",
        "execute_custom_analytics_query",
    ]
    for expected in expected_tools:
        assert expected in tool_names, f"Tool '{expected}' not found in registered FastMCP tools"


def test_get_dataset_metadata():
    """Verify dataset metadata provides ground truth for all 5 tables and join keys, plus table filtering."""
    # Full dataset metadata
    meta = get_dataset_metadata()
    assert meta["project_id"] == "beam-suntory-gemini-llm-poc"
    assert meta["dataset_id"] == "sales_products"
    assert len(meta["tables"]) == 5
    assert "customer-purchase-history" in meta["tables"]
    assert "inventory-tracker" in meta["tables"]
    assert "online-store-orders" in meta["tables"]
    assert "product-sales-region" in meta["tables"]
    assert "retail-store-transactions" in meta["tables"]
    assert len(meta["join_relationships"]) >= 3

    # Table-specific metadata with synonyms
    inv_meta = get_dataset_metadata(table="inventory")
    assert inv_meta["table_name"] == "inventory-tracker"
    assert "columns" in inv_meta["table_metadata"]


def test_get_dimension_catalog_resilience():
    """Verify default values, synonyms, and error cases for dimension catalog."""
    # Default (no parameters passed) returns all dimensions summary
    res_default = get_dimension_catalog()
    assert res_default["dimension"] == "products"
    assert len(res_default["values"]) > 0
    assert "all_dimensions_summary" in res_default

    # Synonyms
    res_store = get_dimension_catalog(dim="store")
    assert res_store["dimension"] == "store_locations"

    res_wh = get_dimension_catalog(category="warehouse")
    assert res_wh["dimension"] == "storage_locations"

    res_supp = get_dimension_catalog(dimension="suppliers")
    assert res_supp["dimension"] == "suppliers"
    assert len(res_supp["values"]) > 0

    # Unsupported dimension
    res_invalid = get_dimension_catalog("unsupported_dim")
    assert "error" in res_invalid


def test_rewrite_and_guard_sql():
    """Verify SQL rewriting, alias resolution, plural fixes, and DDL guards."""
    # 1. Alias & Hyphen resolution
    q, err = _rewrite_and_guard_sql("SELECT * FROM online_orders WHERE TotalPrice > 100")
    assert err is None
    assert "`beam-suntory-gemini-llm-poc.sales_products.online-store-orders`" in q

    # 2. Plural string correction
    q2, err2 = _rewrite_and_guard_sql("SELECT * FROM product-sales-region WHERE Product = 'Laptops'")
    assert err2 is None
    assert "Product = 'Laptop'" in q2

    # 3. Store location correction
    q3, err3 = _rewrite_and_guard_sql("SELECT * FROM retail_store_transactions WHERE StoreID = 'C'")
    assert err3 is None
    assert "Location = 'Store C'" in q3

    # 4. DDL Guard
    q_drop, err_drop = _rewrite_and_guard_sql("DROP TABLE `inventory-tracker`")
    assert q_drop is None
    assert "Disallowed DDL/DML" in err_drop


def test_execute_sql_query_guards():
    """Verify that dangerous DDL/DML statements are blocked via the tool."""
    res = execute_sql_query("DROP TABLE `beam-suntory-gemini-llm-poc.sales_products.inventory-tracker`")
    assert res["status"] == "error"
    assert "Disallowed DDL/DML operation" in res["error"]

    res_delete = execute_custom_analytics_query(sql="DELETE FROM online_store_orders WHERE 1=1")
    assert res_delete["status"] == "error"
    assert "Disallowed DDL/DML operation" in res_delete["error"]


def test_live_dataset_queries():
    """Verify live BigQuery queries for the Golden Hybrid tools."""
    # 1. Dimension catalog
    products = get_dimension_catalog("products")
    assert "values" in products
    assert len(products["values"]) > 0

    # 2. Executive sales summary
    summary = get_executive_sales_summary()
    assert "total_omnichannel_revenue" in summary
    assert summary["total_omnichannel_revenue"] > 1000000
    assert "online_orders" in summary
    assert "retail_store_pos" in summary
    assert "product_performance_ranking" in summary

    # 3. Restock alerts
    alerts = get_inventory_restock_alerts(warehouse="WH-1", limit=5)
    assert "alert_count" in alerts
    assert "alerts" in alerts
    assert "total_deficit_units" in alerts

    # 4. Universal SQL query executor
    sql_res = execute_sql_query("SELECT Product, SUM(Quantity) as units FROM online_store_orders GROUP BY Product ORDER BY units DESC LIMIT 3")
    assert sql_res["status"] == "success"
    assert len(sql_res["data"]) == 3
