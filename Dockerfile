# Multi-service container: runs 3 MCP SSE servers and Nginx reverse proxy
FROM python:3.11-slim

# Install system packages: nginx and curl (for healthcheck)
RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx curl \
    && rm -rf /var/lib/apt/lists/*

# Prepare nginx runtime dir
RUN mkdir -p /var/run/nginx

# Set workdir and copy app source
WORKDIR /app
COPY . /app

# Install Python dependencies from project
RUN pip install --no-cache-dir .

# Copy Nginx configuration (standalone version with localhost)
COPY nginx.conf /etc/nginx/nginx.conf
COPY start.sh /start.sh
RUN chmod +x /start.sh

# Expose Nginx port
EXPOSE 8080

# Healthcheck: ensure Nginx responds
HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 CMD curl -fsS http://localhost:8080/health || exit 1

# Run all services via start script (uvicorn x3 + nginx)
CMD ["/start.sh"]
