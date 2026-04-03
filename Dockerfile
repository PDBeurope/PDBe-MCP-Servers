# Multi-service container: runs MCP remote server with uvicorn
FROM python:3.11-slim

# Install system packages: curl (for healthcheck)
RUN apt-get update \
    && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

# Set workdir and copy app source
WORKDIR /app
COPY . /app

# Install Python dependencies from project
RUN pip install --no-cache-dir .

# Expose port for MCP server
EXPOSE 8000

# Healthcheck: ensure server responds
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD curl -fsS http://localhost:8000/health || exit 1

# Run MCP remote server with uvicorn
CMD ["python", "-m", "pdbe_mcp_server.remote_server", "--host", "0.0.0.0", "--port", "8000"]
