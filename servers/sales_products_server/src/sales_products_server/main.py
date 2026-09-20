from __future__ import annotations

import argparse
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

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
    """Lazily initialize BigQuery client with service account or ADC."""
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


def _clean_str(val: Any) -> str | None:
    if val is None:
        return None
    s = str(val).strip()
    return s if s else None


def _normalize_product_name(product: str | None) -> str | None:
    if not product:
        return None
    p = str(product).strip().lower()
    mapping = {
        "laptops": "Laptop",
        "laptop": "Laptop",
        "notebook": "Laptop",
        "notebooks": "Laptop",
        "chairs": "Chair",
        "chair": "Chair",
        "desks": "Desk",
        "desk": "Desk",
        "monitors": "Monitor",
        "monitor": "Monitor",
        "screens": "Monitor",
        "screen": "Monitor",
        "phones": "Phone",
        "phone": "Phone",
        "smartphones": "Phone",
        "smartphone": "Phone",
        "printers": "Printer",
        "printer": "Printer",
        "tablets": "Tablet",
        "tablet": "Tablet",
        "ipads": "Tablet",
        "ipad": "Tablet",
    }
    return mapping.get(p, product.strip())


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
# Ground Truth & Metadata Tool
# ==============================================================================

_DATASET_METADATA: dict[str, Any] = {
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
                "Supplier": "STRING - Primary vendor/supplier name (DirectGoods, Global Parts, SupplyCo, WarePlus)",
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
                "CouponCode": "STRING - Discount code applied (SAVE10, FREESHIP)",
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
                "Promotion": "STRING - Campaign tag (WINTER15, FREESHIP, Promo A, Promo B)",
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
                "DayOfWeek": "STRING - Day of the week (Monday..Sunday)",
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


def _normalize_table_name(name: str | None) -> str | None:
    if not name:
        return None
    cleaned = name.lower().strip().replace("_", "-").replace(" ", "-")
    mapping = {
        "customer": "customer-purchase-history",
        "customers": "customer-purchase-history",
        "purchase": "customer-purchase-history",
        "purchases": "customer-purchase-history",
        "customer-purchase": "customer-purchase-history",
        "customer-purchase-history": "customer-purchase-history",
        "inventory": "inventory-tracker",
        "stock": "inventory-tracker",
        "inventory-tracker": "inventory-tracker",
        "online": "online-store-orders",
        "order": "online-store-orders",
        "orders": "online-store-orders",
        "online-store-orders": "online-store-orders",
        "region": "product-sales-region",
        "regional": "product-sales-region",
        "regional-sales": "product-sales-region",
        "product-sales-region": "product-sales-region",
        "retail": "retail-store-transactions",
        "pos": "retail-store-transactions",
        "transaction": "retail-store-transactions",
        "transactions": "retail-store-transactions",
        "retail-store-transactions": "retail-store-transactions",
    }
    return mapping.get(cleaned, cleaned)


@mcp.tool(
    name="get_dataset_metadata",
    description="Inspect schemas, column descriptions, record counts, and cross-table join relationships for all tables in the sales_products BigQuery dataset.",
)
def get_dataset_metadata(
    table_name: str | None = None,
    table: str | None = None,
) -> dict[str, Any]:
    """Returns schemas and join graphs for the dataset to eliminate model hallucinations."""
    req_table = _normalize_table_name(table_name or table)
    if req_table and req_table in _DATASET_METADATA["tables"]:
        return {
            "project_id": PROJECT_ID,
            "dataset_id": DATASET_ID,
            "table_name": req_table,
            "table_metadata": _DATASET_METADATA["tables"][req_table],
            "join_relationships": _DATASET_METADATA["join_relationships"],
        }
    return _DATASET_METADATA


# ==============================================================================
# Dimension & Catalog Lookup Tool
# ==============================================================================

@mcp.tool(
    name="get_dimension_catalog",
    description="List distinct values of categorical dimensions: 'store_locations' (physical retail stores), 'products' (product catalog), 'regions' (sales territories), 'storage_locations' (warehouses), 'suppliers' (inventory vendors), 'order_statuses', 'payment_methods', 'customer_types', 'promotions'. Set dimension='store_locations' for physical retail stores.",
)
def get_dimension_catalog(
    dimension: str | None = None,
    dim: str | None = None,
    category: str | None = None,
) -> dict[str, Any]:
    """Returns authoritative distinct values for key dimensions with alias normalization."""
    table_dataset = f"`{PROJECT_ID}.{DATASET_ID}`"
    
    # Resolve parameter synonyms
    dim_raw = dimension or dim or category
    has_explicit_dim = bool(dim_raw)
    dim_key = str(dim_raw or "products").lower().strip().replace("-", "_").replace(" ", "_")
    
    aliases = {
        "product": "products",
        "products": "products",
        "category": "products",
        "categories": "products",
        "item": "products",
        "items": "products",
        "sku": "products",
        "skus": "products",
        "product_name": "products",
        "region": "regions",
        "regions": "regions",
        "territory": "regions",
        "territories": "regions",
        "store": "store_locations",
        "stores": "store_locations",
        "store_location": "store_locations",
        "store_locations": "store_locations",
        "location": "store_locations",
        "locations": "store_locations",
        "retail_store": "store_locations",
        "retail_stores": "store_locations",
        "physical_store": "store_locations",
        "physical_stores": "store_locations",
        "branch": "store_locations",
        "branches": "store_locations",
        "store_id": "store_ids",
        "store_ids": "store_ids",
        "storeid": "store_ids",
        "storeids": "store_ids",
        "status": "order_statuses",
        "statuses": "order_statuses",
        "order_status": "order_statuses",
        "order_statuses": "order_statuses",
        "fulfillment": "order_statuses",
        "payment": "payment_methods",
        "payments": "payment_methods",
        "payment_method": "payment_methods",
        "payment_methods": "payment_methods",
        "payment_type": "payment_methods",
        "payment_types": "payment_methods",
        "storage": "storage_locations",
        "storage_location": "storage_locations",
        "storage_locations": "storage_locations",
        "warehouse": "storage_locations",
        "warehouses": "storage_locations",
        "wh": "storage_locations",
        "supplier": "suppliers",
        "suppliers": "suppliers",
        "vendor": "suppliers",
        "vendors": "suppliers",
        "customer_type": "customer_types",
        "customer_types": "customer_types",
        "customertype": "customer_types",
        "account_type": "customer_types",
        "promotion": "promotions",
        "promotions": "promotions",
        "promo": "promotions",
        "promos": "promotions",
        "campaign": "promotions",
        "campaigns": "promotions",
        "discount": "promotions",
    }
    dim_key = aliases.get(dim_key, dim_key)

    dimension_queries = {
        "products": f"SELECT DISTINCT ProductName as val FROM {table_dataset}.`inventory-tracker` ORDER BY 1",
        "regions": f"SELECT DISTINCT Region as val FROM {table_dataset}.`product-sales-region` ORDER BY 1",
        "store_locations": f"SELECT DISTINCT Location as val FROM {table_dataset}.`retail-store-transactions` ORDER BY 1",
        "store_ids": f"SELECT DISTINCT StoreID as val FROM {table_dataset}.`retail-store-transactions` ORDER BY 1",
        "order_statuses": f"SELECT DISTINCT OrderStatus as val FROM {table_dataset}.`online-store-orders` ORDER BY 1",
        "payment_methods": f"SELECT DISTINCT PaymentMethod as val FROM {table_dataset}.`customer-purchase-history` ORDER BY 1",
        "storage_locations": f"SELECT DISTINCT StorageLocation as val FROM {table_dataset}.`inventory-tracker` ORDER BY 1",
        "suppliers": f"SELECT DISTINCT Supplier as val FROM {table_dataset}.`inventory-tracker` ORDER BY 1",
        "customer_types": f"SELECT DISTINCT CustomerType as val FROM {table_dataset}.`product-sales-region` ORDER BY 1",
        "promotions": f"SELECT DISTINCT Promotion as val FROM {table_dataset}.`product-sales-region` WHERE Promotion IS NOT NULL ORDER BY 1",
    }
    q = dimension_queries.get(dim_key)
    if not q:
        return {
            "error": f"Unknown dimension '{dim_raw}'. Supported dimensions: {list(dimension_queries.keys())}",
            "supported_dimensions": list(dimension_queries.keys()),
        }

    rows = _execute_query(q)
    values = [r["val"] for r in rows if r.get("val") is not None]
    result: dict[str, Any] = {
        "dimension": dim_key,
        "count": len(values),
        "values": values,
    }

    # If called with no arguments, include a summary of all dimensions to prevent extra round trips
    if not has_explicit_dim:
        result["all_dimensions_summary"] = {
            "products": ["Chair", "Desk", "Laptop", "Monitor", "Phone", "Printer", "Tablet"],
            "store_locations": ["Store A", "Store B", "Store C", "Store D"],
            "regions": ["Central", "East", "North", "South", "West"],
            "storage_locations": ["WH-1", "WH-2", "WH-3", "WH-4", "WH-5"],
            "suppliers": ["DirectGoods", "Global Parts", "SupplyCo", "WarePlus"],
            "order_statuses": ["Cancelled", "Delivered", "Pending", "Returned", "Shipped"],
        }
    return result


# ==============================================================================
# Executive Top-Line Omnichannel Synthesis Tool
# ==============================================================================

@mcp.tool(
    name="get_executive_sales_summary",
    description="Calculate top-line executive KPIs across all channels: total revenue, online vs retail vs regional channel mix, order counts, and top-selling products ranking.",
)
def get_executive_sales_summary(
    product: str | None = None,
    product_name: str | None = None,
) -> dict[str, Any]:
    """Calculates top-line executive KPIs across all sales channels."""
    table_dataset = f"`{PROJECT_ID}.{DATASET_ID}`"
    target_product = _normalize_product_name(_clean_str(product or product_name))

    product_filter_clause = ""
    params: list[tuple[str, str, Any]] = []

    if target_product:
        product_filter_clause = "WHERE lower(Product) = @target_prod"
        params.append(("target_prod", "STRING", target_product.lower()))

    sql = f"""
    WITH online AS (
      SELECT
        COUNT(*) as online_orders,
        COALESCE(SUM(Quantity), 0) as online_units,
        COALESCE(SUM(TotalPrice), 0) as online_revenue,
        COUNTIF(OrderStatus = 'Returned') as online_returns,
        COUNTIF(OrderStatus = 'Cancelled') as online_cancelled
      FROM {table_dataset}.`online-store-orders`
      {product_filter_clause}
    ),
    retail AS (
      SELECT
        COUNT(*) as retail_txns,
        COALESCE(SUM(Quantity), 0) as retail_units,
        COALESCE(SUM(TotalPrice), 0) as retail_revenue
      FROM {table_dataset}.`retail-store-transactions`
      {product_filter_clause}
    ),
    regional AS (
      SELECT
        COUNT(*) as regional_orders,
        COALESCE(SUM(Quantity), 0) as regional_units,
        COALESCE(SUM(TotalPrice), 0) as regional_revenue,
        COALESCE(SUM(Returned), 0) as regional_returns
      FROM {table_dataset}.`product-sales-region`
      {product_filter_clause}
    ),
    inventory AS (
      SELECT
        COUNT(*) as total_skus,
        COALESCE(SUM(QuantityInStock), 0) as total_units_in_stock,
        COUNTIF(QuantityInStock <= ReorderPoint) as skus_at_reorder_risk
      FROM {table_dataset}.`inventory-tracker`
      {product_filter_clause.replace('Product', 'ProductName')}
    )
    SELECT
      online.*,
      retail.*,
      regional.*,
      inventory.*
    FROM online
    CROSS JOIN retail
    CROSS JOIN regional
    CROSS JOIN inventory
    """
    rows = _execute_query(sql, params)
    data = rows[0] if rows else {}

    # Rank products by omnichannel revenue
    top_products_sql = f"""
    WITH combined_products AS (
      SELECT Product, TotalPrice, Quantity FROM {table_dataset}.`online-store-orders`
      UNION ALL
      SELECT Product, TotalPrice, Quantity FROM {table_dataset}.`retail-store-transactions`
    )
    SELECT
      Product,
      ROUND(SUM(TotalPrice), 2) as total_revenue,
      SUM(Quantity) as total_units_sold,
      COUNT(*) as transaction_count
    FROM combined_products
    GROUP BY Product
    ORDER BY total_revenue DESC
    """
    top_products = _execute_query(top_products_sql)

    online_rev = float(data.get("online_revenue", 0.0))
    retail_rev = float(data.get("retail_revenue", 0.0))
    regional_rev = float(data.get("regional_revenue", 0.0))
    total_omni_rev = round(online_rev + retail_rev + regional_rev, 2)

    online_units = int(data.get("online_units", 0))
    retail_units = int(data.get("retail_units", 0))
    regional_units = int(data.get("regional_units", 0))
    total_units_sold = online_units + retail_units + regional_units

    online_orders_count = int(data.get("online_orders", 0))
    online_returns = int(data.get("online_returns", 0))
    online_return_rate = round((online_returns / max(online_orders_count, 1)) * 100, 2)

    return {
        "filtered_product": target_product,
        "total_omnichannel_revenue": total_omni_rev,
        "total_units_sold_all_channels": total_units_sold,
        "online_orders": {
            "total_orders": online_orders_count,
            "units_sold": online_units,
            "revenue_usd": online_rev,
            "return_count": online_returns,
            "return_rate_percentage": online_return_rate,
            "cancelled_count": int(data.get("online_cancelled", 0)),
        },
        "retail_store_pos": {
            "total_transactions": int(data.get("retail_txns", 0)),
            "units_sold": retail_units,
            "revenue_usd": retail_rev,
        },
        "regional_sales": {
            "total_orders": int(data.get("regional_orders", 0)),
            "units_sold": regional_units,
            "revenue_usd": regional_rev,
            "returns": int(data.get("regional_returns", 0)),
        },
        "inventory_snapshot": {
            "total_skus": int(data.get("total_skus", 0)),
            "total_units_in_stock": int(data.get("total_units_in_stock", 0)),
            "skus_at_reorder_risk": int(data.get("skus_at_reorder_risk", 0)),
        },
        "product_performance_ranking": top_products,
    }


# ==============================================================================
# Supply Chain Restock Alerts Tool
# ==============================================================================

@mcp.tool(
    name="get_inventory_restock_alerts",
    description="Retrieve inventory restock alerts for supply chain: SKUs at or below reorder threshold with deficit units and estimated restock cost.",
)
def get_inventory_restock_alerts(
    warehouse: str | None = None,
    supplier: str | None = None,
    product: str | None = None,
    limit: int = 25,
) -> dict[str, Any]:
    """Provides actionable restock alerts for supply chain and procurement managers."""
    table_dataset = f"`{PROJECT_ID}.{DATASET_ID}`"
    wh = _clean_str(warehouse)
    supp = _clean_str(supplier)
    prod = _normalize_product_name(_clean_str(product))

    filters = ["QuantityInStock <= ReorderPoint"]
    params: list[tuple[str, str, Any]] = []

    if wh:
        filters.append("lower(StorageLocation) LIKE @wh")
        params.append(("wh", "STRING", f"%{wh.lower()}%"))
    if supp:
        filters.append("lower(Supplier) LIKE @supp")
        params.append(("supp", "STRING", f"%{supp.lower()}%"))
    if prod:
        filters.append("lower(ProductName) LIKE @prod")
        params.append(("prod", "STRING", f"%{prod.lower()}%"))

    where_clause = " WHERE " + " AND ".join(filters)

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
    {where_clause}
    ORDER BY DeficitUnits DESC, LeadTimeDays DESC
    LIMIT @limit
    """
    params.append(("limit", "INT64", min(limit, 500)))
    rows = _execute_query(sql, params)
    total_deficit = sum(r.get("DeficitUnits", 0) for r in rows)
    total_cost = round(sum(r.get("EstimatedRestockCostUsd", 0.0) for r in rows), 2)
    return {
        "alert_count": len(rows),
        "total_deficit_units": total_deficit,
        "total_estimated_restock_cost_usd": total_cost,
        "alerts": rows[:25],
    }


# ==============================================================================
# Universal SQL Query Engine with Guardrails & Normalization
# ==============================================================================

_SQL_TABLE_ALIAS_MAP: dict[str, str] = {
    "customer-purchase-history": "customer-purchase-history",
    "customer_purchase_history": "customer-purchase-history",
    "customer_purchases": "customer-purchase-history",
    "customer_history": "customer-purchase-history",
    "customer_orders": "customer-purchase-history",
    "purchases": "customer-purchase-history",
    "customers": "customer-purchase-history",
    
    "inventory-tracker": "inventory-tracker",
    "inventory_tracker": "inventory-tracker",
    "inventory": "inventory-tracker",
    "inventory_tracking": "inventory-tracker",
    "stock": "inventory-tracker",
    
    "online-store-orders": "online-store-orders",
    "online_store_orders": "online-store-orders",
    "online_orders": "online-store-orders",
    "online_store": "online-store-orders",
    "store_orders": "online-store-orders",
    "online": "online-store-orders",
    "orders": "online-store-orders",
    
    "product-sales-region": "product-sales-region",
    "product_sales_region": "product-sales-region",
    "product_sales_regions": "product-sales-region",
    "regional_sales": "product-sales-region",
    "sales_region": "product-sales-region",
    "sales_regions": "product-sales-region",
    
    "retail-store-transactions": "retail-store-transactions",
    "retail_store_transactions": "retail-store-transactions",
    "retail_transactions": "retail-store-transactions",
    "retail_store": "retail-store-transactions",
    "store_transactions": "retail-store-transactions",
    "retail": "retail-store-transactions",
    "transactions": "retail-store-transactions",
}


def _rewrite_and_guard_sql(raw_query: str) -> tuple[str | None, str | None]:
    """Rewrites custom SQL queries safely, auto-resolving table aliases, missing backticks, and column typos."""
    disallowed = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "CREATE", "TRUNCATE", "MERGE", "GRANT", "REVOKE"]
    cleaned_query = raw_query.strip()
    upper_query = cleaned_query.upper()

    for word in disallowed:
        if re.search(rf"\b{word}\b", upper_query):
            return None, f"Disallowed DDL/DML operation: {word}. Only read-only SELECT queries are permitted."

    # Strip existing backticks to avoid double-escaping
    q = cleaned_query.replace("`", "")

    # Replace table tokens with temporary placeholders (longest alias first)
    placeholder_map: dict[str, str] = {}
    for idx, (alias, real_table) in enumerate(sorted(_SQL_TABLE_ALIAS_MAP.items(), key=lambda x: len(x[0]), reverse=True)):
        target_token = f"__TBL_{idx}__"
        pattern = rf"(?i)(?:{re.escape(PROJECT_ID)}\.)?(?:{re.escape(DATASET_ID)}\.)?(?<![a-zA-Z0-9_\-]){re.escape(alias)}(?![a-zA-Z0-9_\-])"
        if re.search(pattern, q):
            q = re.sub(pattern, target_token, q)
            placeholder_map[target_token] = f"`{PROJECT_ID}.{DATASET_ID}.{real_table}`"

    for token, full_table in placeholder_map.items():
        q = q.replace(token, full_table)

    # Automatically correct common column name hallucinations and snake_case aliases
    q = re.sub(r"(?i)\btotal_amount\b", "TotalPrice", q)
    q = re.sub(r"(?i)\bsales_amount\b", "TotalPrice", q)
    q = re.sub(r"(?i)\border_amount\b", "TotalPrice", q)
    q = re.sub(r"(?i)\bunit_price\b", "UnitPrice", q)
    q = re.sub(r"(?i)\btotal_price\b", "TotalPrice", q)
    q = re.sub(r"(?i)\bproduct_category\b", "ProductCategory", q)
    q = re.sub(r"(?i)\border_status\b", "OrderStatus", q)
    q = re.sub(r"(?i)\bpayment_method\b", "PaymentMethod", q)
    q = re.sub(r"(?i)\bpayment_type\b", "PaymentType", q)
    q = re.sub(r"(?i)\bstore_location\b", "StoreLocation", q)
    q = re.sub(r"(?i)\btime_of_day\b", "TimeOfDay", q)
    q = re.sub(r"(?i)\bday_of_week\b", "DayOfWeek", q)
    q = re.sub(r"(?i)\breview_rating\b", "ReviewRating", q)
    q = re.sub(r"(?i)\bquantity_in_stock\b", "QuantityInStock", q)
    q = re.sub(r"(?i)\breorder_point\b", "ReorderPoint", q)
    q = re.sub(r"(?i)\bstorage_location\b", "StorageLocation", q)
    q = re.sub(r"(?i)\bsupplier_contact\b", "SupplierContact", q)

    # Plural product corrections in literal strings (e.g., 'Laptops' -> 'Laptop')
    q = re.sub(r"(?i)'(laptops|phones|monitors|printers|desks|chairs|tablets)'", lambda m: f"'{m.group(1)[:-1].title()}'", q)
    # Store ID vs Location corrections (e.g., StoreID = 'C' -> Location = 'Store C')
    q = re.sub(r"(?i)\bStoreID\s*=\s*'([A-D])'", r"Location = 'Store \1'", q)
    q = re.sub(r"(?i)\bStoreID\s*=\s*'Store\s*([A-D])'", r"Location = 'Store \1'", q)

    return q, None


@mcp.tool(
    name="execute_sql_query",
    description="Execute a read-only GoogleSQL query against beam-suntory-gemini-llm-poc.sales_products dataset. Handles table aliases, snake_case columns, and hyphenated tables automatically.",
)
def execute_sql_query(
    query: str | None = None,
    sql: str | None = None,
    max_rows: int = 100,
) -> dict[str, Any]:
    """Execute standard GoogleSQL query with guardrails and auto-normalization."""
    return execute_custom_analytics_query(query=query, sql=sql, max_rows=max_rows)


@mcp.tool(
    name="execute_custom_analytics_query",
    description="Fallback tool for custom read-only SQL queries against beam-suntory-gemini-llm-poc.sales_products. Handles table name aliases and hyphenated names automatically.",
)
def execute_custom_analytics_query(
    query: str | None = None,
    sql: str | None = None,
    max_rows: int = 100,
) -> dict[str, Any]:
    """Safe read-only BigQuery query runner with automatic quoting of hyphenated tables and alias resolution."""
    raw_query = _clean_str(query or sql)
    if not raw_query:
        return {
            "status": "error",
            "error": "Query string cannot be empty. Please provide a SQL query using the 'query' or 'sql' parameter.",
        }

    formatted_query, error_msg = _rewrite_and_guard_sql(raw_query)
    if error_msg:
        return {"status": "error", "error": error_msg}

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
