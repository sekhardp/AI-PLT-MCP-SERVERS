# Use an explicit, lightweight Python base
FROM python:3.12-slim

# Copy the modern uv package manager binary straight into the execution path
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Set working directory inside the container
WORKDIR /app

# Prevent Python from writing .pyc files to disk and ensure immediate logs
ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

# Expose default environment variables for config control
ENV MCP_PORT=4208
ENV MCP_HOST=0.0.0.0
ENV SERVICE_ACCOUNT_FILE=/app/credentials.json
ENV GOOGLE_APPLICATION_CREDENTIALS=/app/credentials.json
ENV BIGQUERY_PROJECT_ID=bsi-sftphub-dev

# 3. Copy ONLY the requirements file first to leverage Docker caching
COPY requirements.txt .

# 4. Install the specified packages
RUN pip install --no-cache-dir -r requirements.txt

# Copy dependency mappings first to optimize layer caching
COPY pyproject.toml /app/


# Install exact lock dependencies using uv sync
RUN uv sync --no-cache

# Copy project runtime source code
COPY server.py /app/

# Copy project skills
COPY SKILL.md /app/

# Copy service account credentials into the image
COPY credentials.json /app/

# Open the network allocation port
EXPOSE 4208

# Execute the application through uv's managed virtual environment wrapper
ENTRYPOINT ["uv", "run", "python", "server.py"]
