# Single-stage Dockerfile for MCP remote server using uv
FROM python:3.11-slim

# Install uv
RUN pip install uv

WORKDIR /app

# Copy only necessary files first for better caching
COPY pyproject.toml README.md ./
COPY pdbe_mcp_server/py.typed ./pdbe_mcp_server/py.typed

# Create a virtual environment
RUN uv venv

# Install dependencies using uv pip install
RUN uv pip install --no-cache-dir .

# Copy application source
COPY pdbe_mcp_server/ ./pdbe_mcp_server/

# Expose port
EXPOSE 8000

# Run with uv
CMD ["uv", "run", "pdbe-mcp-remote-server", "--host", "0.0.0.0", "--port", "8000"]
