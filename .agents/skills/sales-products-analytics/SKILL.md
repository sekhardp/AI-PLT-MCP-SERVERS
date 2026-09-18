---
name: sales-products-analytics
description: Authoritative analytics, KPI reporting, and omnichannel synthesis guide for the BigQuery sales_products dataset in beam-suntory-gemini-llm-poc.
---

# Sales & Products BigQuery Analytics Skill Guide

This skill governs all agent interactions with the `sales_products` BigQuery dataset hosted in project `beam-suntory-gemini-llm-poc`.

## 1. Zero-Hallucination Ground Truth

The dataset contains **5 core tables** with exact column definitions and categorical dimensions:

### Table 1: `customer-purchase-history`
- **Columns**: `CustomerID` (STRING), `CustomerName` (STRING), `Product` (STRING), `ProductCategory` (STRING: 'Electronics', 'Furniture'), `PurchaseDate` (DATE: 2023-01-01 to 2025-06-30), `Quantity` (INT), `UnitPrice` (FLOAT), `TotalPrice` (FLOAT), `PaymentMethod` (STRING: 'Cash', 'Credit Card', 'Debit Card', 'Online'), `ReviewRating` (INT: 1 to 5).
- **Use Case**: Customer lifetime value, review satisfaction, and category buying preferences.

### Table 2: `inventory-tracker`
- **Columns**: `ProductID` (STRING), `ProductName` (STRING: 'Chair', 'Desk', 'Laptop', 'Monitor', 'Phone', 'Printer', 'Tablet'), `QuantityInStock` (INT), `ReorderPoint` (INT), `Supplier` (STRING: 'DirectGoods'), `SupplierContact` (STRING), `LeadTime` (INT days), `StorageLocation` (STRING: 'WH-1' to 'WH-5'), `UnitCost` (FLOAT).
- **Use Case**: Stock health, inventory replenishment, deficit alerts, and supplier contact routing.

### Table 3: `online-store-orders`
- **Columns**: `OrderID` (STRING), `Date` (DATE), `CustomerID` (STRING), `Product` (STRING), `Quantity` (INT), `UnitPrice` (FLOAT), `TotalPrice` (FLOAT), `ItemsInCart` (INT), `ShippingAddress` (STRING), `PaymentMethod` (STRING), `OrderStatus` (STRING: 'Cancelled', 'Delivered', 'Pending', 'Returned', 'Shipped'), `TrackingNumber` (STRING), `CouponCode` (STRING: 'SAVE10', 'FREESHIP'), `ReferralSource` (STRING: 'Email', 'Social', 'Direct', 'Organic').
- **Use Case**: E-commerce funnel, digital promotions, courier tracking, and order fulfillment status.

### Table 4: `product-sales-region`
- **Columns**: `OrderID` (STRING), `OrderDate` (DATE), `DeliveryDate` (DATE), `Date` (DATE), `Region` (STRING: 'Central', 'East', 'North', 'South', 'West'), `RegionManager` (STRING), `StoreLocation` (STRING: 'Store A', 'Store B', 'Store C', 'Store D'), `Salesperson` (STRING), `Product` (STRING), `Quantity` (INT), `UnitPrice` (FLOAT), `Discount` (FLOAT: 0.05, 0.10), `ShippingCost` (FLOAT), `TotalPrice` (FLOAT), `CustomerType` (STRING: 'Retail', 'Wholesale'), `CustomerName` (STRING), `PaymentMethod` (STRING), `Promotion` (STRING: 'WINTER15', 'FREESHIP'), `Returned` (INT: 0 or 1).
- **Use Case**: Territorial sales performance, representative benchmarking, and wholesale vs retail split.

### Table 5: `retail-store-transactions`
- **Columns**: `TransactionID` (STRING), `Date` (DATE), `Time` (STRING: HH:MM), `TimeOfDay` (STRING: 'Morning', 'Afternoon', 'Evening'), `DayOfWeek` (STRING: 'Monday'..'Sunday'), `StoreID` (STRING: 'S1' to 'S10'), `Location` (STRING: 'Store A', 'Store B', 'Store C', 'Store D'), `StoreManager` (STRING), `Cashier` (STRING: 'C1' to 'C4'), `Product` (STRING), `Quantity` (INT), `UnitPrice` (FLOAT), `TotalPrice` (FLOAT), `PaymentType` (STRING: 'Cash', 'Credit Card', 'Gift Card').
- **Use Case**: POS brick-and-mortar store operations, shift scheduling, and physical store revenue.

---

## 2. Tool Invocation Decision Tree

1. **Executive Summaries & Omnichannel Insights**:
   - Total sales, return rates, top products -> Use `get_executive_sales_summary`.
   - Online vs Retail channel comparison -> Use `get_omnichannel_comparison`.
2. **Supply Chain & Inventory Management**:
   - Urgent low-stock alerts -> Use `get_inventory_restock_alerts`.
   - Warehouse query by location or supplier -> Use `get_inventory_status`.
3. **Channel-Specific Queries**:
   - Digital orders & fulfillment -> Use `get_online_orders`.
   - Physical store POS logs -> Use `get_retail_transactions`.
   - Geographic / territorial sales -> Use `get_regional_sales`.
   - Customer feedback & satisfaction -> Use `get_customer_purchases`.
4. **Ad-Hoc / Custom SQL Analytics**:
   - For bespoke SQL calculations -> Use `execute_custom_analytics_query`. Hyphenated table names are automatically resolved!

---

## 3. Executive 4-Part Response Standard

When presenting analytics responses to users, format output in the executive 4-part structure:

1. **Governed Source Attribution**: Explicitly state table names and filter criteria queried.
2. **KPI Summary Table**: Key metric figures with clear units ($USD, Units, %).
3. **Distribution Breakdown**: Structured breakdown by dimension (Product, Region, Store, Channel).
4. **Analytical Insights & Recommended Actions**: 2-3 actionable operational conclusions.
