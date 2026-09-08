# Suntory GCP Productivity MCP (BigQuery Client)

This server exposes the same procurement and productivity analytics tools through FastMCP, but it reaches BigQuery through the official Google Python BigQuery client library rather than direct REST calls. It is intended for validating BigQuery access via the `google-cloud-bigquery` SDK and service-account JWT credentials.

## What this server provides

- FastMCP HTTP endpoint for tool-based access
- Procurement and productivity analytics tools backed by BigQuery views/tables in the `bsi-sftphub-dev.DNT_MCP_PILOT` dataset
- BigQuery access through the `google-cloud-bigquery` client library

## Runtime details

- Default host: `0.0.0.0`
- Default port: `4208`
- Transport: HTTP
- Primary MCP endpoint: `http://localhost:4208/mcp`

> The server uses the HTTP transport and exposes the MCP endpoint at `/mcp`. Older `/sse` and `/messages` paths are not the recommended entry points for this server.

## Prerequisites

- Python 3.11+
- A Google Cloud service account JSON file with BigQuery access
- The service account should have BigQuery permissions such as `roles/bigquery.dataViewer` or equivalent

## Environment variables

Set these before starting the server:

- `MCP_HOST` – host interface to bind to (default `0.0.0.0`)
- `MCP_PORT` – port to expose (default `4208`)
- `MCP_TRANSPORT` – transport mode (default `http`)
- `SERVICE_ACCOUNT_FILE` or `GOOGLE_APPLICATION_CREDENTIALS` – path to the service-account JSON file
- `BIGQUERY_PROJECT_ID` – target Google Cloud project (default `bsi-sftphub-dev`)
- `BIGQUERY_AUDIENCE` – BigQuery audience used by the JWT credentials (default `https://bigquery.googleapis.com/`)

## Local setup

1. Copy the example environment file and adjust values if needed:

```bash
copy .env.example .env
```

2. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

3. Run the startup smoke check:

```bash
python smoke_test.py
```

4. Start the server:

```bash
python server.py
```

Or with uv:

```bash
uv sync
uv run server.py
```

## Health checks and access URLs

After startup, verify the following endpoints:

- Health: `http://localhost:4208/health`
- MCP endpoint: `http://localhost:4208/mcp`

The server should respond with a JSON payload including the service name, status, and transport information.

## Docker

```bash
docker build -t suntory-gcp-productivity-bqclient-mcp .
docker run --rm -p 4208:4208 \
  -e MCP_HOST=0.0.0.0 \
  -e MCP_PORT=4208 \
  -e SERVICE_ACCOUNT_FILE=/app/credentials.json \
  -v $(pwd)/credentials.json:/app/credentials.json:ro \
  suntory-gcp-productivity-bqclient-mcp
```

## Authentication model

This variant loads the service account JSON file and creates JWT-based BigQuery credentials through the Google auth helper library. It is useful when you want the same tool surface as the API variant but through the official client SDK. The authentication material is loaded from the service account file and environment variables rather than being embedded in code.

## Saved query / query management strategy

To keep repeated analytics work manageable:

- Store reusable SQL in a separate `queries/` folder or a management table if you later evolve this into a multi-user service.
- Keep a small catalog of common query templates such as spend by company, vendor concentration, and savings opportunities.
- Externalize the most important filters (company code, purchasing org, date range) as tool parameters rather than embedding them in hard-coded SQL.
- When moving to production, prefer a persisted saved-query registry or a versioned SQL template repository.

## End-to-end startup order

1. Ensure the service account JSON file exists and is referenced by `SERVICE_ACCOUNT_FILE` or `GOOGLE_APPLICATION_CREDENTIALS`.
2. Start the server with the environment file or exported variables.
3. Confirm the health endpoint responds on `/health`.
4. Verify the MCP endpoint is reachable at `/mcp`.
5. Connect an MCP client and call a tool such as `Gold_Enterprise_Spend_Fact(limit=5, company_code="1000")`.

## Example tools

The server exposes tools such as:

- `Gold_Account_Assignment_Fact`
- `Gold_Content_Brand_Investment`
- `Gold_Cost_Center_Intelligence`
- `Gold_Enterprise_Spend_Fact`
- `Gold_Executive_Dashboard`
- `Gold_Financial_Attribution`
- `Gold_GL_Account_Intelligence`
- `Gold_Invoice_Fact`
- `Gold_Material_Intelligence`
- `Gold_Monthly_Spend_Trend`
- `Gold_Procurement_KPI`
- `Gold_Savings_Opportunity`
- `Gold_Shadow_IT`
- `Gold_Supplier_Risk`
- `Gold_Supply_Chain_Intelligence`
- `Gold_Vendor_Intelligence`
- `Gold_Vendor_Similarity`
- `Gold_Vendor_Spend_Classification`

Example usage from an MCP client can target a tool like `Gold_Enterprise_Spend_Fact(limit=5, company_code="1000")`.
