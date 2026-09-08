from google.auth import jwt
from google.cloud import bigquery

# 1. Define paths and targets
SERVICE_ACCOUNT_FILE = "credentials.json"
PROJECT_ID = "bsi-sftphub-dev"

# The target audience claim for the BigQuery API
# For BigQuery APIs, the audience value must be exactly this URL
AUDIENCE = "https://bigquery.googleapis.com/"

# 2. Generate the self-signed JWT credentials directly from the service account file
# This loads the private key, structures the claims (iss, sub, aud, exp), and signs it.
credentials = jwt.Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE, 
    audience=AUDIENCE
)

# 3. Initialize the BigQuery client using the JWT credentials
client = bigquery.Client(
    credentials=credentials, 
    project=PROJECT_ID
)

# 4. Invoke the BigQuery API (Execute a query)
query = "SELECT account_assignment_fact_id, spend_fact_id, po_number, po_item, po_date, company_code, purchasing_org, purchasing_group, plant, vendor_id, vendor_name_full, vendor_activity_class, vendor_family, material_id, material_group, assignment_sequence, cost_center, profit_center, gl_account, wbs_element, internal_order, allocation_percentage, allocation_amount, po_net_value, invoice_amount_doc_curr, history_amount_doc_curr, spend_amount_usd, allocated_spend_usd, delivery_completed, release_indicator, final_invoice_flag, latest_invoice_date, last_history_date, gold_load_ts, gold_as_of_date FROM `bsi-sftphub-dev.DNT_MCP_PILOT.gold_account_assignment_fact` LIMIT 10"

try:
    print("Submitting query job to BigQuery using JWT authentication...")
    query_job = client.query(query)  # Makes the authenticated API request
    
    # Fetch results
    results = query_job.result()

    rows = [dict(row) for row in results]
    print("\nQuery Results:")
    print(str(rows) )

except Exception as e:
    print(f"An error occurred: {e}")
