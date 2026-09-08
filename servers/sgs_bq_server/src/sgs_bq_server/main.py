import argparse
import json
import logging
import os
from pathlib import Path
from typing import Optional

from fastmcp import FastMCP
from fastmcp_docs import FastMCPDocs
from google.auth import jwt
from google.cloud import bigquery
from starlette.requests import Request
from starlette.responses import JSONResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("sgs-bq-server")

# Initialize the FastMCP server and documentation
mcp = FastMCP("sgs-bq-server")
docs = FastMCPDocs(mcp, title="Suntory GCP BigQuery Procurement Analytics Tools")

# Default configuration
HOST = os.getenv("MCP_HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", os.getenv("MCP_PORT", "8040")))
TRANSPORT = os.getenv("MCP_TRANSPORT", "stdio")
PROJECT_ID = os.getenv("BIGQUERY_PROJECT_ID", "bsi-sftphub-dev")
AUDIENCE = os.getenv("BIGQUERY_AUDIENCE", "https://bigquery.googleapis.com/")

service_account_override: Optional[str] = None
credentials = None
client: Optional[bigquery.Client] = None


def resolve_service_account_path(explicit_path: Optional[str] = None) -> Optional[Path]:
    """Hierarchically resolve service account JSON file from arguments, env vars, Secret Manager, or standard paths."""
    candidates = [
        explicit_path,
        os.getenv("SERVICE_ACCOUNT_FILE"),
        os.getenv("GOOGLE_APPLICATION_CREDENTIALS"),
        Path("/secrets/credentials.json"),
        Path("/secrets/sgs-bq-credentials"),
        Path(__file__).resolve().parent.parent.parent / "credentials.json",
        Path.cwd() / "credentials.json",
        Path.cwd() / "servers" / "sgs_bq_server" / "credentials.json",
    ]
    for c in candidates:
        if c:
            p = Path(c).expanduser().resolve()
            if p.exists() and p.is_file():
                return p
    return None


def get_bigquery_credentials() -> tuple[Optional[object], str]:
    """Resolve credentials from env JSON, Secret Manager files, or ADC."""
    # 1. Direct JSON string from environment variable (Secret Manager env var)
    sa_json = os.getenv("SERVICE_ACCOUNT_JSON") or os.getenv("SERVICE_ACCOUNT_INFO")
    if sa_json:
        try:
            info = json.loads(sa_json)
            creds = jwt.Credentials.from_service_account_info(info, audience=AUDIENCE)
            return creds, "env_json_jwt"
        except Exception as e:
            try:
                from google.oauth2 import service_account
                creds = service_account.Credentials.from_service_account_info(json.loads(sa_json))
                return creds, "env_json_standard"
            except Exception:
                pass

    # 2. Base64-encoded JSON from environment variable
    sa_b64 = os.getenv("SERVICE_ACCOUNT_BASE64")
    if sa_b64:
        try:
            import base64
            decoded = base64.b64decode(sa_b64).decode("utf-8")
            info = json.loads(decoded)
            creds = jwt.Credentials.from_service_account_info(info, audience=AUDIENCE)
            return creds, "env_base64_jwt"
        except Exception:
            pass

    # 3. File path (Secret Manager volume mount or local credentials.json)
    sa_path = resolve_service_account_path(service_account_override)
    if sa_path:
        try:
            creds = jwt.Credentials.from_service_account_file(str(sa_path), audience=AUDIENCE)
            return creds, f"file_jwt:{sa_path}"
        except Exception as e:
            try:
                from google.oauth2 import service_account
                creds = service_account.Credentials.from_service_account_file(str(sa_path))
                return creds, f"file_standard:{sa_path}"
            except Exception:
                pass

    return None, "adc"


def _health_payload() -> dict[str, object]:
    sa_path = resolve_service_account_path(service_account_override)
    _, auth_mode = get_bigquery_credentials()
    return {
        "service": "sgs-bq-server",
        "status": "ok",
        "transport": TRANSPORT,
        "host": HOST,
        "port": PORT,
        "project_id": PROJECT_ID,
        "service_account_file": str(sa_path) if sa_path else None,
        "auth_mode": auth_mode,
    }


@mcp.custom_route("/health", methods=["GET"])
async def healthcheck(request: Request) -> JSONResponse:
    return JSONResponse(_health_payload())


def startup_smoke_check() -> None:
    """Smoke check to verify server configuration."""
    _, auth_mode = get_bigquery_credentials()
    logger.info(f"Server initialized with authentication mode: {auth_mode}")


def get_bigquery_client() -> bigquery.Client:
    """Lazily initialize BigQuery client with JWT credentials or Application Default Credentials."""
    global credentials, client
    if client is None:
        creds, mode = get_bigquery_credentials()
        if creds:
            client = bigquery.Client(credentials=creds, project=PROJECT_ID)
            logger.info(f"Initialized BigQuery client with {mode} for project {PROJECT_ID}")
        else:
            client = bigquery.Client(project=PROJECT_ID)
            logger.info(f"Initialized BigQuery client with ADC for project {PROJECT_ID}")
    return client


def query_bigquery(query: str, parameters: list[tuple[str, str, object]]) -> str:
    """Execute a BigQuery SQL query and return rows formatted as JSON."""
    try:
        job_config = bigquery.QueryJobConfig(
            query_parameters=[
                bigquery.ScalarQueryParameter(name, dtype, value)
                for name, dtype, value in parameters
            ]
        )
        logger.debug(f"Submitting query: {query} with parameters: {parameters}")
        query_job = get_bigquery_client().query(query, job_config=job_config)
        results = query_job.result()
        rows = [dict(row) for row in results]
        return json.dumps(rows, default=str, indent=2)
    except Exception as e:
        logger.error(f"Error executing query: {e}")
        return f"Error executing query: {str(e)}"


def _build_filtered_query(
    base_query: str,
    limit: int,
    filters: list[tuple[str, str, object, str]] | None = None,
) -> tuple[str, list[tuple[str, str, object]]]:
    """Append optional WHERE clauses and a LIMIT parameter to a SQL query."""
    query = base_query.rstrip().rstrip(";")
    clauses: list[str] = []
    parameters: list[tuple[str, str, object]] = []

    for index, (column, operator, value, dtype) in enumerate(filters or []):
        if value is None:
            continue

        normalized_value = value
        if operator.upper() == "LIKE" and isinstance(value, str):
            normalized_value = f"%{value}%"

        param_name = f"f_{index}"
        clauses.append(f"{column} {operator} @{param_name}")
        parameters.append((param_name, dtype, normalized_value))

    if clauses:
        query = f"{query} WHERE {' AND '.join(clauses)}"

    query = f"{query} LIMIT @limit"
    parameters.append(("limit", "INT64", limit))
    return query, parameters


# ==============================================================================
# MCP Tools (18 Analytical Tools for Suntory GCP BigQuery Procurement Pilot)
# ==============================================================================

@mcp.tool(tags=["procurement", "account_assignment"])
def Gold_Account_Assignment_Fact(
    limit: int = 10,
    company_code: str | None = None,
    purchasing_org: str | None = None,
    purchasing_group: str | None = None,
    material_group: str | None = None,
    cost_center: str | None = None,
    gl_account: str | None = None,
) -> str:
    """Use this tool to retrieve procurement account assignment information linking spend to cost centers, internal orders, WBS elements and financial ownership.

    Business purpose: Provides detailed procurement account assignment information linking spend to cost centers, internal orders, WBS elements and financial ownership.
    Primary business questions answered:
    - How is spend allocated?
    - Which cost centers receive the cost?
    - Which projects or WBS elements consume procurement spend?
    """
    QUERY = r"""
    SELECT account_assignment_fact_id, spend_fact_id, po_number, po_item, po_date, company_code, purchasing_org, purchasing_group, plant, vendor_id, vendor_name_full, vendor_activity_class, vendor_family, material_id, material_group, assignment_sequence, cost_center, profit_center, gl_account, wbs_element, internal_order, allocation_percentage, allocation_amount, po_net_value, invoice_amount_doc_curr, history_amount_doc_curr, spend_amount_usd, allocated_spend_usd, delivery_completed, release_indicator, final_invoice_flag, latest_invoice_date, last_history_date, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_account_assignment_fact`
    """
    filters: list[tuple[str, str, object, str]] = []
    if company_code is not None:
        filters.append(("lower(company_code)", "LIKE", company_code.lower(), "STRING"))
    if purchasing_org is not None:
        filters.append(("lower(purchasing_org)", "LIKE", purchasing_org.lower(), "STRING"))
    if purchasing_group is not None:
        filters.append(("lower(purchasing_group)", "LIKE", purchasing_group.lower(), "STRING"))
    if material_group is not None:
        filters.append(("lower(material_group)", "LIKE", material_group.lower(), "STRING"))
    if cost_center is not None:
        filters.append(("lower(cost_center)", "LIKE", cost_center.lower(), "STRING"))
    if gl_account is not None:
        filters.append(("lower(gl_account)", "LIKE", gl_account.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "marketing", "brand"])
def Gold_Content_Brand_Investment(
    limit: int = 10,
    company_code: str | None = None,
    purchasing_org: str | None = None,
    vendor_name_full: str | None = None,
    material_group: str | None = None,
) -> str:
    """Use this tool to retrieve marketing, content, branding, agency and media-related spend data across the enterprise.

    Business purpose: Identifies marketing, content, branding, agency and media-related spend across the enterprise. Supports marketing investment optimization.
    Primary business questions answered:
    - How much is spent on Content?
    - How much on Brand Investment?
    - Which agencies perform similar work?
    - Which brands spend the most on agencies?
    """
    QUERY = r"""
    SELECT spend_fact_id, company_code, purchasing_org, purchasing_group, plant, vendor_id, invoice_vendor_id, vendor_name_full, vendor_activity_class, vendor_family, po_number, po_item, po_document_type, po_date, latest_invoice_date, material_id, material_group, item_text, spend_amount_usd, po_net_value_usd, invoice_amount_usd, net_price_usd, content_flag, brand_flag, investment_type, spend_band, recommendation, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_content_brand_investment`
    """
    filters: list[tuple[str, str, object, str]] = []
    if company_code is not None:
        filters.append(("lower(company_code)", "LIKE", company_code.lower(), "STRING"))
    if purchasing_org is not None:
        filters.append(("lower(purchasing_org)", "LIKE", purchasing_org.lower(), "STRING"))
    if vendor_name_full is not None:
        filters.append(("lower(vendor_name_full)", "LIKE", vendor_name_full.lower(), "STRING"))
    if material_group is not None:
        filters.append(("lower(material_group)", "LIKE", material_group.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "cost_center"])
def Gold_Cost_Center_Intelligence(limit: int = 10) -> str:
    """Use this tool to retrieve cost-center spending intelligence, peer comparisons and purchasing behaviour patterns.

    Business purpose: Provides benchmarking and intelligence for cost center spending patterns, peer comparisons and purchasing behaviour.
    Primary business questions answered:
    - Which cost centers overspend?
    - Which cost centers have the greatest savings potential?
    - Which departments buy the same services from different suppliers?
    """
    QUERY = r"""
    SELECT cost_center, company_code, assignment_count, spend_line_count, vendor_count, material_count, material_group_count, purchasing_org_count, plant_count, gl_account_count, profit_center_count, internal_order_count, wbs_count, total_po_value, total_invoice_value, total_history_value, total_spend_usd, average_spend_usd, average_line_spend_usd, average_vendor_spend_usd, spend_band, fragmented_vendor_flag, diversified_spend_flag, multi_procurement_flag, diversified_gl_flag, multi_profit_center_flag, internal_order_intensive_flag, project_driven_flag, first_po_date, last_po_date, first_invoice_date, last_invoice_date, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_cost_center_intelligence`
    """
    query, parameters = _build_filtered_query(QUERY, limit)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "spend_fact"])
def Gold_Enterprise_Spend_Fact(
    limit: int = 10,
    company_code: str | None = None,
    purchasing_org: str | None = None,
    vendor_name_full: str | None = None,
) -> str:
    """Use this tool to retrieve the canonical enterprise spend fact table at spend-line level for procurement and vendor analysis.

    Business purpose: Central enterprise spend fact table at spend-line level. Provides the canonical source for procurement, invoice, vendor, cost center, company, category and time analysis. This is the primary analytical dataset used by all downstream intelligence layers.
    Primary business questions answered:
    - What is the total spend?
    - Which vendors have the highest spend?
    - How much do we spend by company, business unit, cost center, category, market or period?
    - How has spend evolved over time?
    """
    QUERY = r"""
    SELECT spend_fact_id, po_number, po_item, po_document_type, po_date, company_code, purchasing_org, purchasing_group, plant, vendor_id, invoice_vendor_id, vendor_name_full, vendor_activity_class, vendor_family, technology_flag, consulting_flag, content_flag, brand_flag, supply_chain_flag, hr_flag, shadow_it_candidate_flag, material_id, material_group, item_text, po_quantity, po_uom, net_price, price_unit, po_net_value, po_gross_value, po_currency, item_currency, invoice_amount_doc_curr, invoice_quantity, invoice_count, latest_invoice_date, invoice_currency, history_amount_doc_curr, history_quantity, history_record_count, last_history_date, account_assignment_category, delivery_completed, item_deletion_flag, header_deletion_flag, release_indicator, release_strategy_group, gr_based_invoice_verification, final_invoice_flag, fx_to_usd, fx_from_factor, fx_to_factor, spend_amount_usd, po_net_value_usd, invoice_amount_usd, net_price_usd, silver_load_ts, gold_load_ts, gold_as_of_date, source_table FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_enterprise_spend_fact`
    """
    filters: list[tuple[str, str, object, str]] = []
    if company_code is not None:
        filters.append(("lower(company_code)", "LIKE", company_code.lower(), "STRING"))
    if purchasing_org is not None:
        filters.append(("lower(purchasing_org)", "LIKE", purchasing_org.lower(), "STRING"))
    if vendor_name_full is not None:
        filters.append(("lower(vendor_name_full)", "LIKE", vendor_name_full.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "executive", "dashboard"])
def Gold_Executive_Dashboard(
    limit: int = 10,
    min_total_spend_usd: float | None = None,
    min_spend_line_count: int | None = None,
    min_vendor_count: int | None = None,
    first_po_date_from: str | None = None,
    first_po_date_to: str | None = None,
    last_po_date_from: str | None = None,
    last_po_date_to: str | None = None,
) -> str:
    """Use this tool to retrieve executive-ready aggregated KPIs and summary metrics for leadership reporting.

    Business purpose: Executive-ready aggregated dataset optimized for dashboards and high-level business reporting. Provides curated KPIs and summary metrics for leadership.
    Primary business questions answered:
    - What are the key procurement KPIs?
    - What is total enterprise spend?
    - What are the highest savings opportunities?
    - How is spend distributed across the enterprise?
    """
    QUERY = r"""
    SELECT total_spend_usd, total_po_value, total_invoice_value, spend_line_count, po_count, vendor_count, material_count, material_group_count, company_count, purchasing_org_count, purchasing_group_count, plant_count, cost_center_count, gl_account_count, technology_spend_usd, consulting_spend_usd, content_spend_usd, supply_chain_spend_usd, hr_spend_usd, strategic_vendors, high_vendors, fragmented_cost_centers, single_source_materials, savings_opportunity_count, estimated_savings_usd, average_vendor_spend_usd, average_po_spend_usd, first_po_date, last_po_date, first_invoice_date, last_invoice_date, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_executive_dashboard`
    """
    filters: list[tuple[str, str, object, str]] = []
    if min_total_spend_usd is not None:
        filters.append(("total_spend_usd", ">=", min_total_spend_usd, "FLOAT64"))
    if min_spend_line_count is not None:
        filters.append(("spend_line_count", ">=", min_spend_line_count, "INT64"))
    if min_vendor_count is not None:
        filters.append(("vendor_count", ">=", min_vendor_count, "INT64"))
    if first_po_date_from is not None:
        filters.append(("first_po_date", ">=", first_po_date_from, "STRING"))
    if first_po_date_to is not None:
        filters.append(("first_po_date", "<=", first_po_date_to, "STRING"))
    if last_po_date_from is not None:
        filters.append(("last_po_date", ">=", last_po_date_from, "STRING"))
    if last_po_date_to is not None:
        filters.append(("last_po_date", "<=", last_po_date_to, "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "financial_attribution"])
def Gold_Financial_Attribution(
    limit: int = 10,
    company_code: str | None = None,
    cost_center: str | None = None,
    profit_center: str | None = None,
    gl_account: str | None = None,
) -> str:
    """Use this tool to retrieve financial ownership information after FI/CO reallocations and internal repostings.

    Business purpose: Explains financial ownership after FI/CO reallocations and internal repostings, providing the final business owner of each expense.
    Primary business questions answered:
    - Where was spend finally allocated?
    - Which reclassifications occurred?
    - Who is the final owner of the expense?
    """
    QUERY = r"""
    SELECT company_code, cost_center, profit_center, gl_account, internal_order, wbs_element, assignment_count, spend_line_count, vendor_count, material_count, plant_count, total_po_value, total_invoice_value, total_history_value, allocated_spend_usd, average_spend_usd, average_line_spend_usd, average_vendor_spend_usd, spend_band, first_po_date, last_po_date, first_invoice_date, last_invoice_date, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_financial_attribution`
    """
    filters: list[tuple[str, str, object, str]] = []
    if company_code is not None:
        filters.append(("lower(company_code)", "LIKE", company_code.lower(), "STRING"))
    if cost_center is not None:
        filters.append(("lower(cost_center)", "LIKE", cost_center.lower(), "STRING"))
    if profit_center is not None:
        filters.append(("lower(profit_center)", "LIKE", profit_center.lower(), "STRING"))
    if gl_account is not None:
        filters.append(("lower(gl_account)", "LIKE", gl_account.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "gl_account"])
def Gold_GL_Account_Intelligence(
    limit: int = 10,
    gl_account: str | None = None,
    company_code: str | None = None,
) -> str:
    """Use this tool to retrieve General Ledger account classifications and financial reporting structures that enrich spend data.

    Business purpose: Enriches spend using General Ledger account classifications and financial reporting structures.
    Primary business questions answered:
    - Which GL accounts generate the highest spend?
    - Which expense types are increasing?
    - Which financial categories should be optimized?
    """
    QUERY = r"""
    SELECT gl_account, company_code, assignment_count, spend_line_count, vendor_count, cost_center_count, profit_center_count, internal_order_count, wbs_count, material_group_count, plant_count, total_po_value, total_invoice_value, total_history_value, total_spend_usd, average_spend_usd, average_line_spend_usd, average_vendor_spend_usd, spend_band, fragmented_vendor_flag, highly_shared_gl_flag, multi_profit_center_flag, internal_order_intensive_flag, project_account_flag, first_po_date, last_po_date, first_invoice_date, last_invoice_date, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_gl_account_intelligence`
    """
    filters: list[tuple[str, str, object, str]] = []
    if gl_account is not None:
        filters.append(("lower(gl_account)", "LIKE", gl_account.lower(), "STRING"))
    if company_code is not None:
        filters.append(("lower(company_code)", "LIKE", company_code.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "invoice"])
def Gold_Invoice_Fact(
    limit: int = 10,
    invoice_number: str | None = None,
    company_code: str | None = None,
    vendor_id: str | None = None,
) -> str:
    """Use this tool to retrieve canonical invoice-level analytical data that links invoices with purchase orders, vendors and accounting information.

    Business purpose: Canonical invoice-level analytical dataset linking invoices with purchase orders, vendors and accounting information.
    Primary business questions answered:
    - Which invoices belong to a PO?
    - Which invoices are duplicated?
    - Which invoices are blocked?
    - Which vendors generated the highest invoice volume?
    """
    QUERY = r"""
    SELECT invoice_fact_id, invoice_number, invoice_item, fiscal_year, posting_date, document_date, created_date, created_time, company_code, vendor_id, po_number, po_item, material_id, plant, account_assignment_category, item_category, tax_code, valuation_type, valuation_class, invoice_currency, invoice_amount_doc_curr, invoice_quantity, invoice_uom, invoice_status, transaction_type, payment_terms, reversal_document, reversal_year, final_invoice_flag, created_by, transaction_code, document_header_text, silver_load_ts, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_invoice_fact`
    """
    filters: list[tuple[str, str, object, str]] = []
    if invoice_number is not None:
        filters.append(("lower(invoice_number)", "LIKE", invoice_number.lower(), "STRING"))
    if company_code is not None:
        filters.append(("lower(company_code)", "LIKE", company_code.lower(), "STRING"))
    if vendor_id is not None:
        filters.append(("lower(vendor_id)", "LIKE", vendor_id.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "material"])
def Gold_Material_Intelligence(
    limit: int = 10,
    material_id: str | None = None,
    material_group: str | None = None,
) -> str:
    """Use this tool to retrieve material-centric procurement intelligence for materials, commodities and categories.

    Business purpose: Material-centric analytical dataset used to analyse procurement by materials, commodities and procurement categories.
    Primary business questions answered:
    - Which materials generate the highest spend?
    - Which commodities could be consolidated?
    - Which products are purchased from multiple suppliers?
    """
    QUERY = r"""
    SELECT material_id, material_group, spend_line_count, vendor_count, company_count, purchasing_org_count, plant_count, po_count, total_po_quantity, total_invoice_quantity, total_history_quantity, total_po_value, total_invoice_value, total_history_value, total_spend_usd, average_spend_usd, average_net_price_usd, average_po_value_usd, spend_band, single_source_material_flag, fragmented_vendor_flag, enterprise_material_flag, first_po_date, last_po_date, first_invoice_date, last_invoice_date, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_material_intelligence`
    """
    filters: list[tuple[str, str, object, str]] = []
    if material_id is not None:
        filters.append(("lower(material_id)", "LIKE", material_id.lower(), "STRING"))
    if material_group is not None:
        filters.append(("lower(material_group)", "LIKE", material_group.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "trend"])
def Gold_Monthly_Spend_Trend(
    limit: int = 10,
    fiscal_year: str | None = None,
    company_code: str | None = None,
    purchasing_org: str | None = None,
) -> str:
    """Use this tool to retrieve pre-aggregated monthly spend trends optimized for executive reporting and time-series analysis.

    Business purpose: Pre-aggregated monthly spend trends optimized for executive reporting and time-series analysis.
    Primary business questions answered:
    - How has enterprise spend evolved month by month?
    - Which categories show increasing trends?
    - Which vendors have growing spend?
    """
    QUERY = r"""
    SELECT fiscal_year, fiscal_month, month_start, company_code, purchasing_org, vendor_id, vendor_name_full, vendor_family, vendor_activity_class, material_group, spend_line_count, po_count, material_count, total_po_quantity, total_invoice_quantity, total_spend_usd, average_spend_usd, technology_spend_usd, consulting_spend_usd, content_spend_usd, supply_chain_spend_usd, hr_spend_usd, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_monthly_spend_trend`
    """
    filters: list[tuple[str, str, object, str]] = []
    if fiscal_year is not None:
        filters.append(("fiscal_year", "LIKE", fiscal_year, "STRING"))
    if company_code is not None:
        filters.append(("lower(company_code)", "LIKE", company_code.lower(), "STRING"))
    if purchasing_org is not None:
        filters.append(("lower(purchasing_org)", "LIKE", purchasing_org.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "kpi"])
def Gold_Procurement_KPI(
    limit: int = 10,
    first_po_date_from: str | None = None,
    first_po_date_to: str | None = None,
    last_po_date_from: str | None = None,
    last_po_date_to: str | None = None,
) -> str:
    """Use this tool to retrieve procurement KPIs including purchasing performance, supplier counts, savings indicators and operational procurement metrics.

    Business purpose: Central repository of procurement KPIs including purchasing performance, supplier counts, savings indicators and operational procurement metrics.
    Primary business questions answered:
    - What are the procurement KPIs?
    - How many active suppliers exist?
    - What is the average spend per supplier?
    - How is procurement performance evolving?
    """
    QUERY = r"""
    SELECT total_spend_usd, total_po_value, total_invoice_value, total_history_value, average_spend_line_usd, spend_line_count, purchase_order_count, purchase_order_item_count, invoice_count, vendor_count, company_count, purchasing_org_count, purchasing_group_count, plant_count, material_count, material_group_count, cost_center_count, profit_center_count, gl_account_count, technology_spend_usd, consulting_spend_usd, content_spend_usd, supply_chain_spend_usd, hr_spend_usd, average_vendor_spend_usd, average_po_spend_usd, average_material_spend_usd, first_po_date, last_po_date, first_invoice_date, last_invoice_date, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_procurement_kpi`
    """
    filters: list[tuple[str, str, object, str]] = []
    if first_po_date_from is not None:
        filters.append(("first_po_date", ">=", first_po_date_from, "STRING"))
    if first_po_date_to is not None:
        filters.append(("first_po_date", "<=", first_po_date_to, "STRING"))
    if last_po_date_from is not None:
        filters.append(("last_po_date", ">=", last_po_date_from, "STRING"))
    if last_po_date_to is not None:
        filters.append(("last_po_date", "<=", last_po_date_to, "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "savings"])
def Gold_Savings_Opportunity(
    limit: int = 10,
    company_code: str | None = None,
    cost_center: str | None = None,
    gl_account: str | None = None,
) -> str:
    """Use this tool to get savings opportunity rows from the Doge MCP pilot dataset."""
    QUERY = r"""
    SELECT opportunity_id, opportunity_type, vendor_id_a, vendor_id_b, vendor_name_a, vendor_name_b, confidence, company_code, cost_center, gl_account, material_group, current_spend_usd, estimated_savings_usd, recommendation, gold_load_ts FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_savings_opportunity`
    """
    filters: list[tuple[str, str, object, str]] = []
    if company_code is not None:
        filters.append(("lower(company_code)", "LIKE", company_code.lower(), "STRING"))
    if cost_center is not None:
        filters.append(("lower(cost_center)", "LIKE", cost_center.lower(), "STRING"))
    if gl_account is not None:
        filters.append(("lower(gl_account)", "LIKE", gl_account.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "shadow_it"])
def Gold_Shadow_IT(
    limit: int = 10,
    vendor_name_full: str | None = None,
    company_code: str | None = None,
    purchasing_org: str | None = None,
    purchasing_group: str | None = None,
) -> str:
    """Use this tool to detect technology-related purchases performed outside central IT governance using vendor classification, cost center ownership and technology indicators.

    Business purpose: Detects technology-related purchases performed outside central IT governance using vendor classification, cost center ownership and technology indicators.
    Primary business questions answered:
    - Where does Shadow IT exist?
    - Which non-IT departments purchase software?
    - Which technology vendors bypass central IT?
    """
    QUERY = r"""
    SELECT spend_fact_id, vendor_id, vendor_name_full, vendor_activity_class, vendor_family, company_code, purchasing_org, purchasing_group, plant, po_number, po_item, po_date, latest_invoice_date, material_id, material_group, item_text, spend_amount_usd, po_net_value_usd, invoice_amount_usd, account_assignment_category, technology_flag, consulting_flag, shadow_it_candidate_flag, technology_category, spend_band, recommendation, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_shadow_it`
    """
    filters: list[tuple[str, str, object, str]] = []
    if vendor_name_full is not None:
        filters.append(("lower(vendor_name_full)", "LIKE", vendor_name_full.lower(), "STRING"))
    if company_code is not None:
        filters.append(("lower(company_code)", "LIKE", company_code.lower(), "STRING"))
    if purchasing_org is not None:
        filters.append(("lower(purchasing_org)", "LIKE", purchasing_org.lower(), "STRING"))
    if purchasing_group is not None:
        filters.append(("lower(purchasing_group)", "LIKE", purchasing_group.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "supplier_risk"])
def Gold_Supplier_Risk(
    limit: int = 10,
    vendor_name: str | None = None,
    vendor_family: str | None = None,
    vendor_tier: str | None = None,
) -> str:
    """Use this tool to assess supplier dependency, concentration and procurement risk across the enterprise.

    Business purpose: Measures supplier dependency, concentration and procurement risk across the enterprise using spend concentration and organizational distribution.
    Primary business questions answered:
    - Which vendors represent concentration risk?
    - Which suppliers are critical?
    - Which vendors are used across the largest number of cost centers?
    """
    QUERY = r"""
    SELECT vendor_id, vendor_name, vendor_activity_class, vendor_family, vendor_tier, total_spend_usd, company_count, material_group_count, technology_flag, consulting_flag, content_flag, supply_chain_flag, hr_flag, shadow_it_candidate_flag, max_similarity, similar_vendor_count, saving_opportunities, estimated_savings_usd, supplier_risk_score, supplier_risk_level, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_supplier_risk`
    """
    filters: list[tuple[str, str, object, str]] = []
    if vendor_name is not None:
        filters.append(("lower(vendor_name)", "LIKE", vendor_name.lower(), "STRING"))
    if vendor_family is not None:
        filters.append(("lower(vendor_family)", "LIKE", vendor_family.lower(), "STRING"))
    if vendor_tier is not None:
        filters.append(("lower(vendor_tier)", "LIKE", vendor_tier.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "supply_chain"])
def Gold_Supply_Chain_Intelligence(
    limit: int = 10,
    company_code: str | None = None,
    purchasing_org: str | None = None,
    purchasing_group: str | None = None,
) -> str:
    """Use this tool to retrieve logistics, warehousing, packaging, manufacturing and operational procurement intelligence.

    Business purpose: Consolidates logistics, warehousing, packaging, manufacturing and operational procurement intelligence.
    Primary business questions answered:
    - Which logistics providers are most expensive?
    - Which suppliers could be consolidated?
    - Which supply chain categories generate the highest spend?
    """
    QUERY = r"""
    SELECT spend_fact_id, company_code, purchasing_org, purchasing_group, plant, vendor_id, invoice_vendor_id, vendor_name_full, vendor_activity_class, vendor_family, po_number, po_item, po_document_type, po_date, latest_invoice_date, material_id, material_group, item_text, po_quantity, invoice_quantity, history_quantity, po_uom, spend_amount_usd, po_net_value_usd, invoice_amount_usd, net_price_usd, delivery_completed, release_indicator, final_invoice_flag, supply_chain_flag, supply_chain_category, spend_band, logistics_material_flag, delivered_flag, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_supply_chain_intelligence`
    """
    filters: list[tuple[str, str, object, str]] = []
    if company_code is not None:
        filters.append(("lower(company_code)", "LIKE", company_code.lower(), "STRING"))
    if purchasing_org is not None:
        filters.append(("lower(purchasing_org)", "LIKE", purchasing_org.lower(), "STRING"))
    if purchasing_group is not None:
        filters.append(("lower(purchasing_group)", "LIKE", purchasing_group.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "vendor"])
def Gold_Vendor_Intelligence(
    limit: int = 10,
    vendor_name: str | None = None,
    vendor_activity_class: str | None = None,
    vendor_family: str | None = None,
) -> str:
    """Use this tool to retrieve business classifications of suppliers, including activity type, vendor family, technology indicators and business capability.

    Business purpose: Provides a business classification of suppliers, including activity type, vendor family, technology indicators and business capability. Used to enrich spend with supplier intelligence.
    Primary business questions answered:
    - Which vendors are technology providers?
    - Which vendors provide consulting?
    - Which agencies provide marketing services?
    - Which suppliers belong to the same business capability?
    """
    QUERY = r"""
    SELECT vendor_id, vendor_name, vendor_activity_class, vendor_family, technology_flag, consulting_flag, content_flag, brand_flag, supply_chain_flag, hr_flag, shadow_it_candidate_flag, intercompany_flag, spend_line_count, po_count, invoice_vendor_count, company_count, purchasing_org_count, plant_count, material_count, material_group_count, total_po_value, total_invoice_value, total_history_value, total_spend_usd, average_spend_usd, first_po_date, last_po_date, first_invoice_date, last_invoice_date, vendor_tier, multi_company_vendor_flag, multi_purchasing_org_flag, multi_plant_vendor_flag, diversified_vendor_flag, mixed_service_flag, average_po_value_usd, average_line_value_usd, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_vendor_intelligence`
    """
    filters: list[tuple[str, str, object, str]] = []
    if vendor_name is not None:
        filters.append(("lower(vendor_name)", "LIKE", vendor_name.lower(), "STRING"))
    if vendor_activity_class is not None:
        filters.append(("lower(vendor_activity_class)", "LIKE", vendor_activity_class.lower(), "STRING"))
    if vendor_family is not None:
        filters.append(("lower(vendor_family)", "LIKE", vendor_family.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "vendor", "similarity"])
def Gold_Vendor_Similarity(limit: int = 10) -> str:
    """Use this tool to identify vendors providing similar or overlapping products or services by comparing classifications, purchasing patterns and business capabilities.

    Business purpose: Identifies vendors providing similar or overlapping products or services by comparing classifications, purchasing patterns and business capabilities. Supports supplier rationalization initiatives.
    Primary business questions answered:
    - Which vendors provide similar services?
    - Which suppliers could be consolidated?
    - Which vendors overlap in functionality?
    """
    QUERY = r"""
    SELECT vendor_id_a, vendor_id_b, vendor_name_a, vendor_name_b, activity_a, activity_b, family_a, family_b, spend_a, spend_b, company_count_a, company_count_b, material_group_count_a, material_group_count_b, tier_a, tier_b, same_activity, same_family, same_technology, same_consulting, same_content, same_supply_chain, same_hr, similarity_score, similarity_level, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_vendor_similarity`
    """
    query, parameters = _build_filtered_query(QUERY, limit)
    return query_bigquery(query, parameters)


@mcp.tool(tags=["procurement", "vendor", "classification"])
def Gold_Vendor_Spend_Classification(
    limit: int = 10,
    vendor_id: str | None = None,
    vendor_name_full: str | None = None,
) -> str:
    """Use this tool to get vendor spend classification rows from the Doge MCP pilot dataset."""
    QUERY = r"""
    SELECT vendor_id, vendor_name_full, primary_business_capability, secondary_business_capability, confidence_pct, review_flag, capability_count, classified_line_count, vendor_line_count, classified_spend_usd, vendor_total_spend_usd, avg_line_confidence, gold_load_ts FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_vendor_spend_classification`
    """
    filters: list[tuple[str, str, object, str]] = []
    if vendor_id is not None:
        filters.append(("lower(vendor_id)", "LIKE", vendor_id.lower(), "STRING"))
    if vendor_name_full is not None:
        filters.append(("lower(vendor_name_full)", "LIKE", vendor_name_full.lower(), "STRING"))

    query, parameters = _build_filtered_query(QUERY, limit, filters)
    return query_bigquery(query, parameters)


# ==============================================================================
# CLI Entrypoint
# ==============================================================================

def main():
    """Run the SGS BigQuery MCP server with CLI argument support."""
    global HOST, PORT, TRANSPORT, PROJECT_ID, service_account_override
    parser = argparse.ArgumentParser(description="Run the SGS BigQuery MCP server")
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse", "http", "streamable-http"],
        default=os.getenv("MCP_TRANSPORT", "stdio"),
        help="Transport protocol: 'stdio' (default, local process), 'sse', 'http', or 'streamable-http'",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=int(os.getenv("PORT", os.getenv("MCP_PORT", "8040"))),
        help="Port to run the HTTP/SSE server (default: 8040)",
    )
    parser.add_argument(
        "--host",
        default=os.getenv("MCP_HOST", "0.0.0.0"),
        help="Host address to bind to (default: 0.0.0.0)",
    )
    parser.add_argument(
        "--project",
        default=os.getenv("BIGQUERY_PROJECT_ID", "bsi-sftphub-dev"),
        help="GCP Project ID to use for the BigQuery client (default: bsi-sftphub-dev)",
    )
    parser.add_argument(
        "--service-account",
        default=None,
        help="Path to the service-account JSON file",
    )
    args = parser.parse_args()

    HOST = args.host
    PORT = args.port
    TRANSPORT = args.transport
    PROJECT_ID = args.project
    if args.service_account:
        service_account_override = args.service_account

    startup_smoke_check()

    try:
        import asyncio
        asyncio.run(docs.setup())
    except Exception as e:
        logger.debug(f"Docs setup skipped: {e}")

    if args.transport in ("sse", "http", "streamable-http"):
        logger.info(f"Starting sgs-bq-server on {args.transport} transport at http://{args.host}:{args.port}")
        mcp.run(transport=args.transport, host=args.host, port=args.port)
    else:
        logger.info("Starting sgs-bq-server on stdio transport...")
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()