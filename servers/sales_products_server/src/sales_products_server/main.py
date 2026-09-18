from __future__ import annotations

import argparse
import json
import logging
import os
import re
from pathlib import Path
from typing import Any, Literal

from fastmcp import FastMCP
from fastmcp_docs import FastMCPDocs
from google.cloud import bigquery
from starlette.requests import Request
from starlette.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sales-products-server")

mcp = FastMCP("sales-products-server")
docs = FastMCPDocs(mcp, title="Sales & Products BigQuery Analytics Tools")

PROJECT_ID = os.getenv("BIGQUERY_PROJECT_ID", "beam-suntory-gemini-llm-poc")
DATASET_ID = os.getenv("BIGQUERY_DATASET_ID", "sales_products")
HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("MCP_PORT", "8060")))
TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")

_client: bigquery.Client | None = None
_service_account_path: str | None = None


def resolve_service_account_path(explicit_path: str | None = None) -> Path | None:
    """Hierarchically resolve service account JSON file from arguments, env vars, or standard paths."""
    candidates = [
        explicit_path,
        os.getenv("SERVICE_ACCOUNT_FILE"),
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        Path("/secrets/credentials.json"),
        Path("/secrets/sales-products-credentials"),
        Path(__file__).resolve().parent.parent.parent / "credentials.json",
        Path.cwd() / "credentials.json",
    ]
    for c in candidates:
        if c:
            p = Path(c).expanduser().resolve()
            if p.exists() and p.is_file():
                return p
    return None


def get_bigquery_client() -> bigquery.Client:
    """Lazily initialize BigQuery client."""
    global _client
    if _client is None:
        sa_json = os.getenv("SERVICE_ACCOUNT_JSON") or os.getenv("SERVICE_ACCOUNT_INFO")
        if sa_json:
            try:
                from google.oauth2 import service_account
                info = json.loads(sa_json)
                creds = service_account.Credentials.from_service_account_info(info)
                _client = bigquery.Client(credentials=creds, project=PROJECT_ID)
                logger.info(f"Initialized BigQuery client with env JSON for project {PROJECT_ID}")
                return _client
            except Exception as e:
                logger.warning(f"Failed to load SERVICE_ACCOUNT_JSON: {e}")

        sa_path = resolve_service_account_path(_service_account_path)
        if sa_path:
            try:
                from google.oauth2 import service_account
                creds = service_account.Credentials.from_service_account_file(str(sa_path))
                _client = bigquery.Client(credentials=creds, project=PROJECT_ID)
                logger.info(f"Initialized BigQuery client with file {sa_path} for project {PROJECT_ID}")
                return _client
            except Exception as e:
                logger.warning(f"Failed to load service account file {sa_path}: {e}")

        _client = bigquery.Client(project=PROJECT_ID)
        logger.info(f"Initialized BigQuery client with ADC for project {PROJECT_ID}")
    return _client


def _execute_query(query: str, parameters: list[tuple[str, str, Any]] | None = None) -> list[dict[str, Any]]:
    """Execute a parameterized BigQuery query and return results as a list of dicts."""
    client = get_bigquery_client()
    job_config = bigquery.QueryJobConfig()
    if parameters:
        job_config.query_parameters = [
            bigquery.ScalarQueryParameter(name, dtype, value)
            for name, dtype, value in parameters
        ]
    query_job = client.query(query, job_config=job_config)
    results = query_job.result()
    return [dict(row) for row in results]


def _build_filtered_query(
    base_sql: str,
    limit: int = 100,
    filters: list[tuple[str, str, Any, str]] | None = None,
    order_by: str | None = None,
) -> tuple[str, list[tuple[str, str, Any]]]:
    """Appends WHERE clauses, ORDER BY, and LIMIT safely to a base SQL query."""
    query = base_sql.rstrip().rstrip(";")
    clauses: list[str] = []
    parameters: list[tuple[str, str, Any]] = []

    for idx, (col, op, val, dtype) in enumerate(filters or []):
        if val is None:
            continue
        param_name = f"f_{idx}"
        norm_val = f"%{val}%" if op.upper() == "LIKE" and isinstance(val, str) else val
        clauses.append(f"{col} {op} @{param_name}")
        parameters.append((param_name, dtype, norm_val))

    if clauses:
        query = f"{query} WHERE {' AND '.join(clauses)}"

    if order_by:
        query = f"{query} ORDER BY {order_by}"

    query = f"{query} LIMIT @limit"
    parameters.append(("limit", "INT64", min(limit, 2000)))
    return query, parameters


@mcp.custom_route("/health", methods=["GET"])
async def healthcheck(request: Request) -> JSONResponse:
    return JSONResponse({
        "service": "sales-products-server",
        "status": "ok",
        "project_id": PROJECT_ID,
        "dataset_id": DATASET_ID,
        "transport": TRANSPORT,
    })


# ==============================================================================
# Ground Truth & Metadata Tools
# ==============================================================================

@mcp.tool(
    name="get_dataset_metadata",
    description="Returns the authoritative schemas, column descriptions, record counts, and cross-table join relationships for all 5 tables in the sales_products BigQuery dataset.",
)
def get_dataset_metadata() -> dict[str, Any]:
    """Returns schemas and join graphs for the dataset to eliminate model hallucinations."""
    return {
        "project_id": PROJECT_ID,
        "dataset_id": DATASET_ID,
        "tables": {
            "customer-purchase-history": {
                "description": "Customer purchase transaction history with review ratings and categories.",
                "total_rows": 1800,
                "primary_keys": ["CustomerID", "PurchaseDate", "Product"],
                "columns": {
                    "CustomerID": "STRING - Unique customer identifier (e.g. C4020, C8133)",
                    "CustomerName": "STRING - Customer name label",
                    "Product": "STRING - Product name (e.g. Chair, Desk, Laptop, Monitor, Phone, Printer, Tablet)",
                    "ProductCategory": "STRING - Category classification (e.g. Electronics, Furniture)",
                    "PurchaseDate": "DATE - Date of purchase (2023-01-01 to 2025-06-30)",
                    "Quantity": "INTEGER - Units purchased",
                    "UnitPrice": "FLOAT - Price per unit in USD",
                    "TotalPrice": "FLOAT - Total transaction price in USD",
                    "PaymentMethod": "STRING - Payment method used (Cash, Credit Card, Debit Card, Online)",
                    "ReviewRating": "INTEGER - Product customer satisfaction review score (1 to 5)",
                },
            },
            "inventory-tracker": {
                "description": "Warehouse inventory levels, reorder thresholds, unit costs, and supplier lead times.",
                "total_rows": 500,
                "primary_keys": ["ProductID"],
                "columns": {
                    "ProductID": "STRING - Unique stock keeping product ID (e.g. P76449)",
                    "ProductName": "STRING - Name of product",
                    "QuantityInStock": "INTEGER - Current units on hand in warehouse",
                    "ReorderPoint": "INTEGER - Inventory threshold level triggering restock",
                    "Supplier": "STRING - Primary vendor/supplier name (e.g. DirectGoods)",
                    "SupplierContact": "STRING - Supplier email contact",
                    "LeadTime": "INTEGER - Restock delivery lead time in days",
                    "StorageLocation": "STRING - Warehouse location code (WH-1, WH-2, WH-3, WH-4, WH-5)",
                    "UnitCost": "FLOAT - Supplier unit purchase cost in USD",
                },
            },
            "online-store-orders": {
                "description": "E-commerce digital storefront orders, fulfillment statuses, tracking, and promotions.",
                "total_rows": 1200,
                "primary_keys": ["OrderID"],
                "columns": {
                    "OrderID": "STRING - Unique e-commerce order ID (e.g. ORD200049)",
                    "Date": "DATE - Order placement date",
                    "CustomerID": "STRING - Customer ID",
                    "Product": "STRING - Product ordered",
                    "Quantity": "INTEGER - Units ordered",
                    "UnitPrice": "FLOAT - Unit selling price in USD",
                    "TotalPrice": "FLOAT - Total order price in USD",
                    "ItemsInCart": "INTEGER - Total distinct items in shopping cart",
                    "ShippingAddress": "STRING - Delivery address",
                    "PaymentMethod": "STRING - Payment method",
                    "OrderStatus": "STRING - Fulfillment status (Cancelled, Delivered, Pending, Returned, Shipped)",
                    "TrackingNumber": "STRING - Courier package tracking ID",
                    "CouponCode": "STRING - Discount code applied (e.g. SAVE10, FREESHIP, null)",
                    "ReferralSource": "STRING - Acquisition channel (Email, Social, Direct, Organic)",
                },
            },
            "product-sales-region": {
                "description": "Regional sales distribution across geographic territories, customer types, and promotions.",
                "total_rows": 1500,
                "primary_keys": ["OrderID"],
                "columns": {
                    "OrderID": "STRING - Regional sales order ID (e.g. REG100012)",
                    "OrderDate": "DATE - Order date",
                    "DeliveryDate": "DATE - Fulfillment date",
                    "Date": "DATE - Transaction date",
                    "Region": "STRING - Geographic territory (Central, East, North, South, West)",
                    "RegionManager": "STRING - Executive territory manager",
                    "StoreLocation": "STRING - Regional retail branch (Store A, Store B, Store C, Store D)",
                    "Salesperson": "STRING - Assigned account representative",
                    "Product": "STRING - Product name",
                    "Quantity": "INTEGER - Quantity sold",
                    "UnitPrice": "FLOAT - Unit price in USD",
                    "Discount": "FLOAT - Percentage discount applied (e.g. 0.05, 0.10)",
                    "ShippingCost": "FLOAT - Freight cost in USD",
                    "TotalPrice": "FLOAT - Final invoice total in USD",
                    "CustomerType": "STRING - Account type (Retail, Wholesale)",
                    "CustomerName": "STRING - Customer name",
                    "PaymentMethod": "STRING - Payment method",
                    "Promotion": "STRING - Campaign tag (e.g. WINTER15, FREESHIP)",
                    "Returned": "INTEGER - Return flag (1 = returned, 0 = kept)",
                },
            },
            "retail-store-transactions": {
                "description": "Point-of-Sale (POS) brick-and-mortar physical store checkout logs.",
                "total_rows": 2000,
                "primary_keys": ["TransactionID"],
                "columns": {
                    "TransactionID": "STRING - Unique POS transaction ID (e.g. TX301518)",
                    "Date": "DATE - Transaction date",
                    "Time": "STRING - Local transaction timestamp (HH:MM)",
                    "TimeOfDay": "STRING - Time classification (Morning, Afternoon, Evening)",
                    "DayOfWeek": "STRING - Day of the week",
                    "StoreID": "STRING - Store branch code (S1 through S10)",
                    "Location": "STRING - Physical store branch (Store A, Store B, Store C, Store D)",
                    "StoreManager": "STRING - Branch manager on duty",
                    "Cashier": "STRING - Cashier employee code (C1, C2, C3, C4)",
                    "Product": "STRING - Product purchased",
                    "Quantity": "INTEGER - Units purchased",
                    "UnitPrice": "FLOAT - Unit selling price in USD",
                    "TotalPrice": "FLOAT - Total checkout price in USD",
                    "PaymentType": "STRING - Payment method (Cash, Credit Card, Gift Card)",
                },
            },
        },
        "join_relationships": [
            "customer-purchase-history.CustomerID <-> online-store-orders.CustomerID",
            "inventory-tracker.ProductName <-> customer-purchase-history.Product <-> online-store-orders.Product <-> product-sales-region.Product <-> retail-store-transactions.Product",
            "retail-store-transactions.Location <-> product-sales-region.StoreLocation",
        ],
    }


@mcp.tool(
    name="get_dimension_catalog",
    description="Returns the exact distinct values for any categorical dimension (products, regions, stores, order statuses, payment methods, warehouse locations) across the dataset.",
)
def get_dimension_catalog(
    dimension: Literal[
        "products",
        "regions",
        "store_locations",
        "store_ids",
        "order_statuses",
        "payment_methods",
        "storage_locations",
        "customer_types",
        "promotions",
    ]
) -> dict[str, Any]:
    """Returns authoritative distinct values for key dimensions."""
    table_dataset = f"`{PROJECT_ID}.{DATASET_ID}`"
    dimension_queries = {
        "products": f"SELECT DISTINCT ProductName as val FROM {table_dataset}.`inventory-tracker` ORDER BY 1",
        "regions": f"SELECT DISTINCT Region as val FROM {table_dataset}.`product-sales-region` ORDER BY 1",
        "store_locations": f"SELECT DISTINCT Location as val FROM {table_dataset}.`retail-store-transactions` ORDER BY 1",
        "store_ids": f"SELECT DISTINCT StoreID as val FROM {table_dataset}.`retail-store-transactions` ORDER BY 1",
        "order_statuses": f"SELECT DISTINCT OrderStatus as val FROM {table_dataset}.`online-store-orders` ORDER BY 1",
        "payment_methods": f"SELECT DISTINCT PaymentMethod as val FROM {table_dataset}.`customer-purchase-history` ORDER BY 1",
        "storage_locations": f"SELECT DISTINCT StorageLocation as val FROM {table_dataset}.`inventory-tracker` ORDER BY 1",
        "customer_types": f"SELECT DISTINCT CustomerType as val FROM {table_dataset}.`product-sales-region` ORDER BY 1",
        "promotions": f"SELECT DISTINCT Promotion as val FROM {table_dataset}.`product-sales-region` WHERE Promotion IS NOT NULL ORDER BY 1",
    }
    q = dimension_queries.get(dimension)
    if not q:
        return {"error": f"Unsupported dimension: {dimension}"}
    rows = _execute_query(q)
    return {
        "dimension": dimension,
        "values": [r["val"] for r in rows if r["val"] is not None],
    }


# ==============================================================================
# Domain-Specific Parameterized Analytical Tools
# ==============================================================================

@mcp.tool(
    name="get_customer_purchases",
    description="Query customer purchase history with parameterized filters for customer ID, product, category, payment method, rating, and dates.",
)
def get_customer_purchases(
    customer_id: str | None = None,
    product: str | None = None,
    product_category: str | None = None,
    payment_method: str | None = None,
    min_review_rating: int | None = None,
    purchase_date_from: str | None = None,
    purchase_date_to: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Retrieves customer purchase history with parameterized filtering."""
    base_sql = f"""
    SELECT CustomerID, CustomerName, Product, ProductCategory, PurchaseDate, Quantity, UnitPrice, TotalPrice, PaymentMethod, ReviewRating
    FROM `{PROJECT_ID}.{DATASET_ID}.customer-purchase-history`
    """
    filters: list[tuple[str, str, Any, str]] = []
    if customer_id:
        filters.append(("CustomerID", "=", customer_id, "STRING"))
    if product:
        filters.append(("lower(Product)", "LIKE", product.lower(), "STRING"))
    if product_category:
        filters.append(("lower(ProductCategory)", "LIKE", product_category.lower(), "STRING"))
    if payment_method:
        filters.append(("lower(PaymentMethod)", "LIKE", payment_method.lower(), "STRING"))
    if min_review_rating is not None:
        filters.append(("ReviewRating", ">=", min_review_rating, "INT64"))
    if purchase_date_from:
        filters.append(("PurchaseDate", ">=", purchase_date_from, "DATE"))
    if purchase_date_to:
        filters.append(("PurchaseDate", "<=", purchase_date_to, "DATE"))

    query, params = _build_filtered_query(base_sql, limit=limit, filters=filters, order_by="PurchaseDate DESC")
    rows = _execute_query(query, params)
    return {"count": len(rows), "records": rows}


@mcp.tool(
    name="get_inventory_status",
    description="Query warehouse inventory stock levels, unit costs, lead times, and restock thresholds with stock health filtering.",
)
def get_inventory_status(
    product_name: str | None = None,
    storage_location: str | None = None,
    supplier: str | None = None,
    stock_status: Literal["all", "low_stock", "out_of_stock", "healthy"] = "all",
    limit: int = 50,
) -> dict[str, Any]:
    """Retrieves inventory levels and health status."""
    base_sql = f"""
    SELECT ProductID, ProductName, QuantityInStock, ReorderPoint, Supplier, SupplierContact, LeadTime, StorageLocation, UnitCost,
           (QuantityInStock - ReorderPoint) as StockSurplus,
           CASE
             WHEN QuantityInStock = 0 THEN 'OUT_OF_STOCK'
             WHEN QuantityInStock <= ReorderPoint THEN 'LOW_STOCK'
             ELSE 'HEALTHY'
           END as HealthStatus
    FROM `{PROJECT_ID}.{DATASET_ID}.inventory-tracker`
    """
    filters: list[tuple[str, str, Any, str]] = []
    if product_name:
        filters.append(("lower(ProductName)", "LIKE", product_name.lower(), "STRING"))
    if storage_location:
        filters.append(("StorageLocation", "=", storage_location, "STRING"))
    if supplier:
        filters.append(("lower(Supplier)", "LIKE", supplier.lower(), "STRING"))

    if stock_status == "low_stock":
        filters.append(("QuantityInStock", "<=", "ReorderPoint", "EXPR"))  # Handled below
    elif stock_status == "out_of_stock":
        filters.append(("QuantityInStock", "=", 0, "INT64"))
    elif stock_status == "healthy":
        filters.append(("QuantityInStock", ">", "ReorderPoint", "EXPR"))

    # Custom handling for expressions
    clean_filters: list[tuple[str, str, Any, str]] = []
    extra_clauses: list[str] = []
    for col, op, val, dtype in filters:
        if dtype == "EXPR":
            extra_clauses.append(f"{col} {op} {val}")
        else:
            clean_filters.append((col, op, val, dtype))

    query, params = _build_filtered_query(base_sql, limit=limit, filters=clean_filters, order_by="StockSurplus ASC")
    if extra_clauses:
        kw = "AND" if "WHERE" in query else "WHERE"
        parts = query.split("ORDER BY")
        query = f"{parts[0]} {kw} {' AND '.join(extra_clauses)} ORDER BY {parts[1]}"

    rows = _execute_query(query, params)
    return {"count": len(rows), "records": rows}


@mcp.tool(
    name="get_online_orders",
    description="Query e-commerce online store orders with filters for order status (Delivered, Shipped, Pending, Returned, Cancelled), coupon code, product, customer, and date.",
)
def get_online_orders(
    order_id: str | None = None,
    customer_id: str | None = None,
    product: str | None = None,
    order_status: Literal["Delivered", "Shipped", "Pending", "Returned", "Cancelled"] | None = None,
    coupon_code: str | None = None,
    referral_source: str | None = None,
    order_date_from: str | None = None,
    order_date_to: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Retrieves online store orders with parameterized filtering."""
    base_sql = f"""
    SELECT OrderID, Date, CustomerID, Product, Quantity, UnitPrice, TotalPrice, ItemsInCart, ShippingAddress, PaymentMethod, OrderStatus, TrackingNumber, CouponCode, ReferralSource
    FROM `{PROJECT_ID}.{DATASET_ID}.online-store-orders`
    """
    filters: list[tuple[str, str, Any, str]] = []
    if order_id:
        filters.append(("OrderID", "=", order_id, "STRING"))
    if customer_id:
        filters.append(("CustomerID", "=", customer_id, "STRING"))
    if product:
        filters.append(("lower(Product)", "LIKE", product.lower(), "STRING"))
    if order_status:
        filters.append(("OrderStatus", "=", order_status, "STRING"))
    if coupon_code:
        filters.append(("CouponCode", "=", coupon_code, "STRING"))
    if referral_source:
        filters.append(("lower(ReferralSource)", "LIKE", referral_source.lower(), "STRING"))
    if order_date_from:
        filters.append(("Date", ">=", order_date_from, "DATE"))
    if order_date_to:
        filters.append(("Date", "<=", order_date_to, "DATE"))

    query, params = _build_filtered_query(base_sql, limit=limit, filters=filters, order_by="Date DESC")
    rows = _execute_query(query, params)
    return {"count": len(rows), "records": rows}


@mcp.tool(
    name="get_regional_sales",
    description="Query regional sales performance across geographic regions (Central, East, North, South, West), customer types (Retail, Wholesale), salesperson, discounts, and return flags.",
)
def get_regional_sales(
    region: Literal["Central", "East", "North", "South", "West"] | None = None,
    product: str | None = None,
    customer_type: Literal["Retail", "Wholesale"] | None = None,
    salesperson: str | None = None,
    region_manager: str | None = None,
    store_location: str | None = None,
    promotion: str | None = None,
    returned_only: bool = False,
    order_date_from: str | None = None,
    order_date_to: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Retrieves regional sales data with parameterized filtering."""
    base_sql = f"""
    SELECT OrderID, OrderDate, DeliveryDate, Date, Region, RegionManager, StoreLocation, Salesperson, Product, Quantity, UnitPrice, Discount, ShippingCost, TotalPrice, CustomerType, CustomerName, PaymentMethod, Promotion, Returned
    FROM `{PROJECT_ID}.{DATASET_ID}.product-sales-region`
    """
    filters: list[tuple[str, str, Any, str]] = []
    if region:
        filters.append(("Region", "=", region, "STRING"))
    if product:
        filters.append(("lower(Product)", "LIKE", product.lower(), "STRING"))
    if customer_type:
        filters.append(("CustomerType", "=", customer_type, "STRING"))
    if salesperson:
        filters.append(("lower(Salesperson)", "LIKE", salesperson.lower(), "STRING"))
    if region_manager:
        filters.append(("lower(RegionManager)", "LIKE", region_manager.lower(), "STRING"))
    if store_location:
        filters.append(("StoreLocation", "=", store_location, "STRING"))
    if promotion:
        filters.append(("Promotion", "=", promotion, "STRING"))
    if returned_only:
        filters.append(("Returned", "=", 1, "INT64"))
    if order_date_from:
        filters.append(("OrderDate", ">=", order_date_from, "DATE"))
    if order_date_to:
        filters.append(("OrderDate", "<=", order_date_to, "DATE"))

    query, params = _build_filtered_query(base_sql, limit=limit, filters=filters, order_by="OrderDate DESC")
    rows = _execute_query(query, params)
    return {"count": len(rows), "records": rows}


@mcp.tool(
    name="get_retail_transactions",
    description="Query physical retail store point-of-sale (POS) transactions by store ID (S1-S10), location (Store A-D), product, cashier, manager, time of day, day of week, and payment type.",
)
def get_retail_transactions(
    store_id: str | None = None,
    location: str | None = None,
    product: str | None = None,
    store_manager: str | None = None,
    cashier: str | None = None,
    time_of_day: Literal["Morning", "Afternoon", "Evening"] | None = None,
    day_of_week: str | None = None,
    payment_type: Literal["Cash", "Credit Card", "Gift Card"] | None = None,
    date_from: str | None = None,
    date_to: str | None = None,
    limit: int = 50,
) -> dict[str, Any]:
    """Retrieves physical retail transactions with parameterized filtering."""
    base_sql = f"""
    SELECT TransactionID, Date, Time, StoreID, Location, Product, Quantity, UnitPrice, PaymentType, Cashier, StoreManager, TimeOfDay, DayOfWeek, TotalPrice
    FROM `{PROJECT_ID}.{DATASET_ID}.retail-store-transactions`
    """
    filters: list[tuple[str, str, Any, str]] = []
    if store_id:
        filters.append(("StoreID", "=", store_id, "STRING"))
    if location:
        filters.append(("Location", "=", location, "STRING"))
    if product:
        filters.append(("lower(Product)", "LIKE", product.lower(), "STRING"))
    if store_manager:
        filters.append(("lower(StoreManager)", "LIKE", store_manager.lower(), "STRING"))
    if cashier:
        filters.append(("Cashier", "=", cashier, "STRING"))
    if time_of_day:
        filters.append(("TimeOfDay", "=", time_of_day, "STRING"))
    if day_of_week:
        filters.append(("lower(DayOfWeek)", "=", day_of_week.lower(), "STRING"))
    if payment_type:
        filters.append(("PaymentType", "=", payment_type, "STRING"))
    if date_from:
        filters.append(("Date", ">=", date_from, "DATE"))
    if date_to:
        filters.append(("Date", "<=", date_to, "DATE"))

    query, params = _build_filtered_query(base_sql, limit=limit, filters=filters, order_by="Date DESC")
    rows = _execute_query(query, params)
    return {"count": len(rows), "records": rows}


# ==============================================================================
# Cross-Channel & Executive Aggregation Tools
# ==============================================================================

@mcp.tool(
    name="get_executive_sales_summary",
    description="Calculates enterprise-wide aggregated executive KPIs across online store, retail stores, and regional sales channels (total gross revenue, channel revenue mix, units sold, return rates, and top products).",
)
def get_executive_sales_summary() -> dict[str, Any]:
    """Calculates top-line executive KPIs across all sales channels."""
    table_dataset = f"`{PROJECT_ID}.{DATASET_ID}`"
    sql = f"""
    WITH online AS (
      SELECT
        COUNT(*) as online_orders,
        SUM(Quantity) as online_units,
        SUM(TotalPrice) as online_revenue,
        COUNTIF(OrderStatus = 'Returned') as online_returns,
        COUNTIF(OrderStatus = 'Cancelled') as online_cancelled
      FROM {table_dataset}.`online-store-orders`
    ),
    retail AS (
      SELECT
        COUNT(*) as retail_txns,
        SUM(Quantity) as retail_units,
        SUM(TotalPrice) as retail_revenue
      FROM {table_dataset}.`retail-store-transactions`
    ),
    regional AS (
      SELECT
        COUNT(*) as regional_orders,
        SUM(Quantity) as regional_units,
        SUM(TotalPrice) as regional_revenue,
        SUM(Returned) as regional_returns
      FROM {table_dataset}.`product-sales-region`
    ),
    inventory AS (
      SELECT
        COUNT(*) as total_skus,
        SUM(QuantityInStock) as total_units_in_stock,
        COUNTIF(QuantityInStock <= ReorderPoint) as skus_at_reorder_risk
      FROM {table_dataset}.`inventory-tracker`
    ),
    top_products AS (
      SELECT
        Product,
        SUM(Quantity) as units_sold,
        ROUND(SUM(TotalPrice), 2) as revenue
      FROM (
        SELECT Product, Quantity, TotalPrice FROM {table_dataset}.`online-store-orders`
        UNION ALL
        SELECT Product, Quantity, TotalPrice FROM {table_dataset}.`retail-store-transactions`
      )
      GROUP BY Product
      ORDER BY revenue DESC
      LIMIT 5
    )
    SELECT
      o.online_orders,
      ROUND(o.online_revenue, 2) as online_revenue,
      o.online_units,
      o.online_returns,
      ROUND(o.online_returns / NULLIF(o.online_orders, 0) * 100, 2) as online_return_rate_pct,
      r.retail_txns,
      ROUND(r.retail_revenue, 2) as retail_revenue,
      r.retail_units,
      reg.regional_orders,
      ROUND(reg.regional_revenue, 2) as regional_revenue,
      ROUND(o.online_revenue + r.retail_revenue, 2) as total_omnichannel_revenue,
      o.online_units + r.retail_units as total_omnichannel_units,
      inv.total_skus,
      inv.total_units_in_stock,
      inv.skus_at_reorder_risk
    FROM online o
    CROSS JOIN retail r
    CROSS JOIN regional reg
    CROSS JOIN inventory inv
    """
    rows = _execute_query(sql)
    top_prods_sql = f"""
    SELECT Product, SUM(Quantity) as units_sold, ROUND(SUM(TotalPrice), 2) as revenue
    FROM (
      SELECT Product, Quantity, TotalPrice FROM {table_dataset}.`online-store-orders`
      UNION ALL
      SELECT Product, Quantity, TotalPrice FROM {table_dataset}.`retail-store-transactions`
    )
    GROUP BY Product
    ORDER BY revenue DESC
    """
    top_rows = _execute_query(top_prods_sql)

    summary = rows[0] if rows else {}
    summary["product_performance_ranking"] = top_rows
    return summary


@mcp.tool(
    name="get_omnichannel_comparison",
    description="Compares product performance side-by-side between Online E-Commerce Store and Physical Retail Stores (volume, revenue, unit prices).",
)
def get_omnichannel_comparison() -> dict[str, Any]:
    """Provides side-by-side omnichannel channel performance breakdown per product."""
    table_dataset = f"`{PROJECT_ID}.{DATASET_ID}`"
    sql = f"""
    WITH online AS (
      SELECT
        Product,
        COUNT(*) as online_orders,
        SUM(Quantity) as online_units,
        ROUND(SUM(TotalPrice), 2) as online_revenue,
        ROUND(AVG(UnitPrice), 2) as online_avg_unit_price
      FROM {table_dataset}.`online-store-orders`
      GROUP BY Product
    ),
    retail AS (
      SELECT
        Product,
        COUNT(*) as retail_txns,
        SUM(Quantity) as retail_units,
        ROUND(SUM(TotalPrice), 2) as retail_revenue,
        ROUND(AVG(UnitPrice), 2) as retail_avg_unit_price
      FROM {table_dataset}.`retail-store-transactions`
      GROUP BY Product
    )
    SELECT
      COALESCE(o.Product, r.Product) as product,
      COALESCE(o.online_units, 0) as online_units,
      COALESCE(o.online_revenue, 0) as online_revenue,
      COALESCE(o.online_avg_unit_price, 0) as online_avg_unit_price,
      COALESCE(r.retail_units, 0) as retail_units,
      COALESCE(r.retail_revenue, 0) as retail_revenue,
      COALESCE(r.retail_avg_unit_price, 0) as retail_avg_unit_price,
      COALESCE(o.online_units, 0) + COALESCE(r.retail_units, 0) as total_units,
      ROUND(COALESCE(o.online_revenue, 0) + COALESCE(r.retail_revenue, 0), 2) as total_revenue,
      ROUND(COALESCE(o.online_revenue, 0) / NULLIF(COALESCE(o.online_revenue, 0) + COALESCE(r.retail_revenue, 0), 0) * 100, 2) as online_revenue_share_pct
    FROM online o
    FULL OUTER JOIN retail r ON o.Product = r.Product
    ORDER BY total_revenue DESC
    """
    rows = _execute_query(sql)
    return {"comparison": rows}


@mcp.tool(
    name="get_inventory_restock_alerts",
    description="Identifies all SKUs currently at or below their reorder threshold, calculates supply deficits, lead time risk, and restock purchase cost estimates.",
)
def get_inventory_restock_alerts() -> dict[str, Any]:
    """Provides actionable restock alerts for supply chain and procurement managers."""
    table_dataset = f"`{PROJECT_ID}.{DATASET_ID}`"
    sql = f"""
    SELECT
      ProductID,
      ProductName,
      QuantityInStock,
      ReorderPoint,
      (ReorderPoint - QuantityInStock) as DeficitUnits,
      Supplier,
      SupplierContact,
      LeadTime as LeadTimeDays,
      StorageLocation,
      UnitCost,
      ROUND((ReorderPoint - QuantityInStock + 50) * UnitCost, 2) as EstimatedRestockCostUsd,
      CASE
        WHEN QuantityInStock = 0 THEN 'CRITICAL_OUT_OF_STOCK'
        WHEN QuantityInStock <= (ReorderPoint / 2) THEN 'HIGH_PRIORITY'
        ELSE 'REORDER_POINT_REACHED'
      END as AlertLevel
    FROM {table_dataset}.`inventory-tracker`
    WHERE QuantityInStock <= ReorderPoint
    ORDER BY DeficitUnits DESC, LeadTimeDays DESC
    """
    rows = _execute_query(sql)
    return {
        "alert_count": len(rows),
        "alerts": rows,
    }


# ==============================================================================
# Safe SQL Runner with Guardrails
# ==============================================================================

@mcp.tool(
    name="execute_custom_analytics_query",
    description="Executes a safe, read-only analytical SQL query against beam-suntory-gemini-llm-poc.sales_products. Automatically handles backticks for hyphenated table names and prevents mutations.",
)
def execute_custom_analytics_query(query: str, max_rows: int = 100) -> dict[str, Any]:
    """Safe read-only BigQuery query runner with automatic quoting of hyphenated tables."""
    # Guard against non-read-only keywords
    disallowed = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE", "MERGE", "GRANT", "REVOKE"]
    cleaned_query = query.strip()
    upper_query = cleaned_query.upper()

    for word in disallowed:
        if re.search(rf"\b{word}\b", upper_query):
            return {"error": f"Disallowed DDL/DML operation: {word}. Only read-only SELECT queries are permitted."}

    # Automatically fix missing backticks around hyphenated tables
    known_tables = [
        "customer-purchase-history",
        "inventory-tracker",
        "online-store-orders",
        "product-sales-region",
        "retail-store-transactions",
    ]
    formatted_query = cleaned_query
    for tbl in known_tables:
        pattern = rf"(?<![`\w]){re.escape(tbl)}(?![`\w])"
        formatted_query = re.sub(pattern, f"`{PROJECT_ID}.{DATASET_ID}.{tbl}`", formatted_query)

    try:
        client = get_bigquery_client()
        query_job = client.query(formatted_query)
        results = query_job.result(max_results=min(max_rows, 1000))
        rows = [dict(row) for row in results]
        return {
            "status": "success",
            "row_count": len(rows),
            "executed_query": formatted_query,
            "data": rows,
        }
    except Exception as e:
        logger.error(f"Error executing custom query: {e}")
        return {
            "status": "error",
            "error": str(e),
            "attempted_query": formatted_query,
        }


# ==============================================================================
# CLI Entrypoint
# ==============================================================================

def main():
    global HOST, PORT, TRANSPORT, PROJECT_ID, DATASET_ID, _service_account_path
    parser = argparse.ArgumentParser(description="Sales & Products BigQuery MCP Server")
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
    parser.add_argument(
        "--project",
        default=PROJECT_ID,
        help=f"GCP Project ID (default: {PROJECT_ID})",
    )
    parser.add_argument(
        "--dataset",
        default=DATASET_ID,
        help=f"BigQuery Dataset ID (default: {DATASET_ID})",
    )
    parser.add_argument(
        "--service-account",
        default=None,
        help="Path to service account JSON file",
    )
    args = parser.parse_args()

    HOST = args.host
    PORT = args.port
    TRANSPORT = args.transport
    PROJECT_ID = args.project
    DATASET_ID = args.dataset
    if args.service_account:
        _service_account_path = args.service_account

    try:
        import asyncio
        asyncio.run(docs.setup())
    except Exception as e:
        logger.debug(f"Docs setup skipped: {e}")

    if args.transport == "sse":
        logger.info(f"Starting sales-products-server on SSE at http://{args.host}:{args.port}")
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        logger.info("Starting sales-products-server on stdio transport...")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
