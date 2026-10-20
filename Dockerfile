# Build the app resources from source, independently of local generated files.
FROM node:22-slim AS apps-build

WORKDIR /build/apps/structure-explorer
COPY apps/structure-explorer/package.json apps/structure-explorer/package-lock.json ./
RUN npm ci
COPY apps/structure-explorer/ ./
RUN npm run build

FROM python:3.11-slim

# Install uv
RUN pip install uv

WORKDIR /app

# Install the complete package, including the freshly built app resources.
COPY pyproject.toml README.md ./
COPY pdbe_mcp_server/ ./pdbe_mcp_server/
COPY --from=apps-build /build/pdbe_mcp_server/ui/ ./pdbe_mcp_server/ui/
COPY scripts/check_app_artifacts.py ./scripts/check_app_artifacts.py

# Create a virtual environment
RUN uv venv

RUN uv build --wheel --out-dir /tmp/pdbe-dist \
    && python scripts/check_app_artifacts.py /tmp/pdbe-dist \
    && uv pip install --no-cache-dir /tmp/pdbe-dist/*.whl

# Expose port
EXPOSE 8000

# Use the installed package without a dependency sync at container startup.
CMD ["/app/.venv/bin/pdbe-mcp-remote-server", "--host", "0.0.0.0", "--port", "8000", "--all"]
