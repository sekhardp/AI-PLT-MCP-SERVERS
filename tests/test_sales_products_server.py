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
    # Default (no parameters passed)
    res_default = get_dimension_catalog()
    assert res_default["dimension"] == "products"
    assert len(res_default["values"]) > 0

    # Synonyms
    res_store = get_dimension_catalog(dim="store")
    assert res_store["dimension"] == "store_locations"

    res_wh = get_dimension_catalog(category="warehouse")
    assert res_wh["dimension"] == "storage_locations"

    # Unsupported dimension
    res_invalid = get_dimension_catalog("unsupported_dim")
    assert "error" in res_invalid


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
    assert res["status"] == "error"
    assert "Disallowed DDL/DML operation" in res["error"]

    res_delete = execute_custom_analytics_query(sql="DELETE FROM online_store_orders WHERE 1=1")
    assert res_delete["status"] == "error"
    assert "Disallowed DDL/DML operation" in res_delete["error"]


def test_live_dataset_queries_and_synonyms():
    """Verify live BigQuery queries and parameter resilience against beam-suntory-gemini-llm-poc."""
    # 1. Dimension catalog
    products = get_dimension_catalog("products")
    assert "values" in products
    assert len(products["values"]) > 0

    # 2. Executive sales summary with and without product filter
    summary = get_executive_sales_summary()
    assert "total_omnichannel_revenue" in summary
    assert "online_orders" in summary
    assert "retail_txns" in summary
    assert "product_performance_ranking" in summary

    summary_prod = get_executive_sales_summary(product_name="Phone")
    assert "product_performance_ranking" in summary_prod

    # 3. Omnichannel comparison with and without product filter
    omni = get_omnichannel_comparison()
    assert "comparison" in omni
    assert len(omni["comparison"]) > 0

    omni_desk = get_omnichannel_comparison(product="Desk")
    assert len(omni_desk["comparison"]) >= 1

    # 4. Restock alerts with warehouse filter
    alerts = get_inventory_restock_alerts(warehouse="WH-1", limit=5)
    assert "alert_count" in alerts
    assert "alerts" in alerts

    # 5. Customer purchases with synonyms (product_name, rating, max_results)
    cust = get_customer_purchases(product_name="Chair", rating=3, max_results=3)
    assert "records" in cust
    assert cust["count"] <= 3

    # 6. Inventory status with synonyms (product, warehouse, status)
    inv = get_inventory_status(product="Laptop", warehouse="WH-1", status="low", max_rows=3)
    assert "records" in inv

    # 7. Online orders with synonyms (product_name, status, promo_code)
    orders = get_online_orders(product_name="Phone", status="delivered", promo_code="SAVE10", max_results=3)
    assert "records" in orders

    # 8. Regional sales with synonyms (region, rep, returned)
    reg = get_regional_sales(region="central", returned="true", top_n=3)
    assert "records" in reg

    # 9. Retail transactions with synonyms (store, shift, payment)
    retail = get_retail_transactions(store="Store A", shift="morning", payment="credit", top_n=3)
    assert "records" in retail

    # 10. Custom analytics query with underscore table name and 'sql' parameter
    custom = execute_custom_analytics_query(sql="SELECT OrderID, TotalPrice FROM online_store_orders LIMIT 2")
    assert custom["status"] == "success"
    assert len(custom["data"]) == 2
