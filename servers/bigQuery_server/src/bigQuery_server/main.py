import os
import argparse
from typing import List, Optional
from google.cloud import bigquery
from fastmcp import FastMCP
from fastmcp_docs import FastMCPDocs

# Initialize FastMCP server
mcp = FastMCP("bigquery-server")
docs = FastMCPDocs(mcp, title="BigQuery Server Tools")

# Lazy client initialization variables
_client: Optional[bigquery.Client] = None
project_id: Optional[str] = None

def get_client() -> bigquery.Client:
    """
    Lazily initialize and return the BigQuery client.
    This prevents auth errors at import time.
    """
    global _client
    if _client is None:
        effective_project = project_id or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
        if effective_project:
            _client = bigquery.Client(project=effective_project)
        else:
            _client = bigquery.Client()
    return _client

@mcp.tool(tags=["bigquery", "query"])
async def run_query(query: str) -> str:
    """
    Execute a read-only SQL query against BigQuery and return results formatted as CSV.
    
    Args:
        query: The standard SQL query to execute.
    """
    try:
        client = get_client()
        query_job = client.query(query)
        results = query_job.result(max_results=2000)
        
        import csv
        import io
        output = io.StringIO()
        writer = csv.writer(output)
        
        # Write headers
        writer.writerow([field.name for field in results.schema])
        # Write rows
        for row in results:
            writer.writerow(list(row.values()))
            
        return output.getvalue()
        
    except Exception as e:
        return f"Error executing query: {str(e)}"

@mcp.tool(tags=["bigquery", "metadata"])
async def list_datasets(project: Optional[str] = None) -> List[str]:
    """
    List all datasets in a GCP project.
    """
    try:
        client = get_client()
        effective_project = project or client.project or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
        datasets = list(client.list_datasets(project=effective_project))
        return [d.dataset_id for d in datasets]
    except Exception as e:
        return [f"Error listing datasets: {str(e)}"]

@mcp.tool(tags=["bigquery", "metadata"])
async def list_tables(dataset_id: str, project: Optional[str] = None) -> List[str]:
    """
    List all tables within a given dataset.
    """
    try:
        client = get_client()
        target_project = project or client.project or os.getenv("GOOGLE_CLOUD_PROJECT") or os.getenv("GCP_PROJECT")
        dataset_ref = client.dataset(dataset_id, project=target_project)
        tables = list(client.list_tables(dataset_ref))
        return [t.table_id for t in tables]
    except Exception as e:
        return [f"Error listing tables: {str(e)}"]

def main():
    parser = argparse.ArgumentParser(description="Run the BigQuery MCP server")
    parser.add_argument(
        "--transport", 
        choices=["stdio", "sse"], 
        default="stdio", 
        help="Transport protocol: 'stdio' (default, local process) or 'sse' (network)"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=8000, 
        help="Port to run the HTTP/SSE server (only used for '--transport sse')"
    )
    parser.add_argument(
        "--host",
        default="0.0.0.0",
        help="Host address to run the HTTP/SSE server (default: 0.0.0.0)"
    )
    parser.add_argument(
        "--project",
        default=None,
        help="GCP Project ID to use for the BigQuery client"
    )
    args = parser.parse_args()

    global project_id
    project_id = args.project

    import asyncio
    asyncio.run(docs.setup())

    if args.transport == "sse":
        print(f"Starting bigquery-server on SSE transport at http://{args.host}:{args.port}")
        mcp.run(transport="sse", host=args.host, port=args.port)
    else:
        mcp.run(transport="stdio")

if __name__ == "__main__":
    main()
