# Sales & Products BigQuery MCP Server (`sales-products-server`)

FastMCP Server providing high-precision, hallucination-free analytical tools over the `sales_products` dataset in GCP project `beam-suntory-gemini-llm-poc`.

## Dataset Overview

- **Project ID**: `beam-suntory-gemini-llm-poc`
- **Dataset ID**: `sales_products`
- **Tables**:
  1. `customer-purchase-history` (1,800 rows): Customer purchase history, review ratings, categories, and payment types.
  2. `inventory-tracker` (500 rows): Stock levels, reorder points, lead times, warehouse locations, and supplier unit costs.
  3. `online-store-orders` (1,200 rows): E-commerce digital storefront orders, fulfillment statuses, tracking numbers, and coupons.
  4. `product-sales-region` (1,500 rows): Regional geographic sales distribution, discounts, salesperson performance, and returns.
  5. `retail-store-transactions` (2,000 rows): Brick-and-mortar physical POS transactions across 10 store branches.

## Tools Exposed

1. **`get_dataset_metadata`**: Authoritative schemas, types, descriptions, and join relationships.
2. **`get_dimension_catalog`**: Exact distinct values for dimensions (products, regions, stores, order statuses, payment methods).
3. **`get_customer_purchases`**: Parameterized query over `customer-purchase-history`.
4. **`get_inventory_status`**: Stock levels and health metrics (`low_stock`, `healthy`) over `inventory-tracker`.
5. **`get_online_orders`**: Parameterized query over `online-store-orders`.
6. **`get_regional_sales`**: Parameterized query over `product-sales-region`.
7. **`get_retail_transactions`**: Parameterized query over `retail-store-transactions`.
8. **`get_executive_sales_summary`**: Omnichannel revenue, units, and return rate KPIs.
9. **`get_omnichannel_comparison`**: Side-by-side comparison of online vs physical retail channels.
10. **`get_inventory_restock_alerts`**: Low-stock alerts with supplier contact and lead times.
11. **`execute_custom_analytics_query`**: Safe read-only SQL with auto-backtick escaping.
