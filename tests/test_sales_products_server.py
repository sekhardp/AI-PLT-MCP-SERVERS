from __future__ import annotations

import pytest
from sales_products_server.main import (
    mcp,
    get_dataset_metadata,
    get_dimension_catalog,
    _build_filtered_query,
    execute_custom_analytics_query,
    get_customer_purchases,
    get_inventory_status,
    get_online_orders,
    get_regional_sales,
    get_retail_transactions,
    get_executive_sales_summary,
    get_omnichannel_comparison,
    get_inventory_restock_alerts,
)


@pytest.mark.asyncio
async def test_sales_products_tool_discovery():
    """Verify that all 11 sales & products analytics tools are registered with FastMCP."""
    tools = await mcp.list_tools()
    tool_names = [t.name for t in tools]
    expected_tools = [
        "get_dataset_metadata",
        "get_dimension_catalog",
        "get_customer_purchases",
        "get_inventory_status",
        "get_online_orders",
        "get_regional_sales",
        "get_retail_transactions",
        "get_executive_sales_summary",
        "get_omnichannel_comparison",
        "get_inventory_restock_alerts",
        "execute_custom_analytics_query",
    ]
    for expected in expected_tools:
        assert expected in tool_names, f"Tool '{expected}' not found in registered FastMCP tools"


def test_get_dataset_metadata():
    """Verify dataset metadata provides ground truth for all 5 tables and join keys."""
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


def test_get_dimension_catalog_invalid():
    """Verify error returned for unsupported dimension."""
    res = get_dimension_catalog("unsupported_dim")  # type: ignore
    assert "error" in res


def test_build_filtered_query_construction():
    """Verify WHERE clause and limit parameter binding."""
    base_sql = "SELECT * FROM `my_project.sales_products.inventory-tracker`"
    filters = [
        ("lower(ProductName)", "LIKE", "phone", "STRING"),
        ("StorageLocation", "=", "WH-1", "STRING"),
    ]
    query, params = _build_filtered_query(base_sql, limit=25, filters=filters, order_by="QuantityInStock ASC")
    assert "WHERE lower(ProductName) LIKE @f_0 AND StorageLocation = @f_1" in query
    assert "ORDER BY QuantityInStock ASC" in query
    assert "LIMIT @limit" in query
    assert ("f_0", "STRING", "%phone%") in params
    assert ("f_1", "STRING", "WH-1") in params
    assert ("limit", "INT64", 25) in params


def test_execute_custom_analytics_query_ddl_guard():
    """Verify that dangerous DDL/DML statements are blocked."""
    res = execute_custom_analytics_query("DROP TABLE `beam-suntory-gemini-llm-poc.sales_products.inventory-tracker`")
    assert "error" in res
    assert "Disallowed DDL/DML operation" in res["error"]

    res_delete = execute_custom_analytics_query("DELETE FROM `beam-suntory-gemini-llm-poc.sales_products.online-store-orders` WHERE 1=1")
    assert "error" in res_delete
    assert "Disallowed DDL/DML operation" in res_delete["error"]


def test_live_dataset_queries():
    """Verify live BigQuery queries against beam-suntory-gemini-llm-poc."""
    # 1. Dimension catalog
    products = get_dimension_catalog("products")
    assert "values" in products
    assert len(products["values"]) > 0

    # 2. Executive sales summary
    summary = get_executive_sales_summary()
    assert "total_omnichannel_revenue" in summary
    assert "online_orders" in summary
    assert "retail_txns" in summary
    assert "product_performance_ranking" in summary

    # 3. Omnichannel comparison
    omni = get_omnichannel_comparison()
    assert "comparison" in omni
    assert len(omni["comparison"]) > 0

    # 4. Restock alerts
    alerts = get_inventory_restock_alerts()
    assert "alert_count" in alerts
    assert "alerts" in alerts

    # 5. Customer purchases
    cust = get_customer_purchases(limit=5)
    assert cust["count"] <= 5

    # 6. Inventory status
    inv = get_inventory_status(stock_status="low_stock", limit=5)
    assert "records" in inv

    # 7. Online orders
    orders = get_online_orders(order_status="Delivered", limit=5)
    assert "records" in orders

    # 8. Regional sales
    reg = get_regional_sales(region="Central", limit=5)
    assert "records" in reg

    # 9. Retail transactions
    retail = get_retail_transactions(location="Store A", limit=5)
    assert "records" in retail
