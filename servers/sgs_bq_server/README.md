# Suntory GCP Productivity MCP (BigQuery Client)

This server exposes procurement, spend analytics, and productivity tools through FastMCP, connecting to BigQuery via the official Google Cloud BigQuery client library (`google-cloud-bigquery`) and JWT / service account authentication.

## Features

- **18 Analytical Tools**: Comprehensive tools backed by BigQuery Gold tables/views in `bsi-sftphub-dev.DNT_MCP_PILOT`.
- **Dual Transport Support**: Run seamlessly over `stdio` (local agent pipe) or `sse` / `http` (network endpoint).
- **FastMCP Documentation & Skill Integration**: Integrated `FastMCPDocs` and skill definitions (`SKILL.md`) for AI agents.
- **Robust Multi-mode Auth**: Automatically resolves service account credentials via `credentials.json`, `SERVICE_ACCOUNT_FILE`, `GOOGLE_APPLICATION_CREDENTIALS`, or GCP Application Default Credentials (ADC).
- **Health Check**: Dedicated `/health` endpoint reporting connection and authentication status.

## Runtime Details

- Default host: `0.0.0.0`
- Default port: `8040`
- Supported Transports: `stdio`, `sse`, `http`, `streamable-http`
- Primary SSE Endpoint: `http://localhost:8040/sse`
- Health Endpoint: `http://localhost:8040/health`

## Local Usage

### 1. Sync Dependencies
```bash
uv sync
```

### 2. Run via Justfile Recipes
```bash
# Run locally using stdio transport
just run-bigquery-sgs-stdio

# Run locally using SSE transport on port 8040
just run-bigquery-sgs-sse 8040
```

### 3. Run Directly with UV CLI
```bash
# Run on SSE
uv run --package sgs-bq-server sgs-bq-server --transport sse --port 8040

# Run on stdio
uv run --package sgs-bq-server sgs-bq-server --transport stdio
```

## Running with Docker & Docker Compose

### Using Docker Compose (Monorepo)
```bash
just docker-up
```

### Using Container Run Script
```bash
./servers/sgs_bq_server/container_run.sh
```

## Available Tools

1. **`Gold_Account_Assignment_Fact`**: Procurement account assignments (cost centers, internal orders, WBS elements, GL accounts).
2. **`Gold_Content_Brand_Investment`**: Marketing, branding, agency, and media spend data.
3. **`Gold_Cost_Center_Intelligence`**: Cost-center spend benchmarking and peer comparisons.
4. **`Gold_Enterprise_Spend_Fact`**: Canonical enterprise spend fact table at spend-line level.
5. **`Gold_Executive_Dashboard`**: High-level curated KPIs and summary metrics for leadership.
6. **`Gold_Financial_Attribution`**: Financial ownership after FI/CO reallocations.
7. **`Gold_GL_Account_Intelligence`**: General Ledger classifications and reporting structures.
8. **`Gold_Invoice_Fact`**: Canonical invoice-level data linked to POs and vendors.
9. **`Gold_Material_Intelligence`**: Material-centric procurement intelligence.
10. **`Gold_Monthly_Spend_Trend`**: Pre-aggregated monthly spend trends.
11. **`Gold_Procurement_KPI`**: Key procurement KPIs and operational metrics.
12. **`Gold_Savings_Opportunity`**: Algorithmic savings opportunities and recommendations.
13. **`Gold_Shadow_IT`**: Detects software/hardware purchases made outside central IT governance.
14. **`Gold_Supplier_Risk`**: Supplier concentration and dependency risk scores.
15. **`Gold_Supply_Chain_Intelligence`**: Logistics, warehousing, packaging, and supply chain spend.
16. **`Gold_Vendor_Intelligence`**: Supplier classifications (technology, consulting, agency, HR, etc.).
17. **`Gold_Vendor_Similarity`**: Identifies suppliers providing overlapping capabilities for rationalization.
18. **`Gold_Vendor_Spend_Classification`**: Supplier business capabilities and classification confidence.
