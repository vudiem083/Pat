# BAT — Bedrock Agent Toolkit
#
# This image packages BAT itself (REST API / MCP server). It does NOT contain
# Minecraft Bedrock Dedicated Server binaries or assets: mount your own server
# under /app/runtime/server and set BAT_BEDROCK_SERVER to use runtime tests.
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    BAT_WORKSPACE=/app/data \
    BAT_RUNTIME_ROOT=/app/runtime \
    BAT_HOST=0.0.0.0 \
    BAT_PORT=8000

WORKDIR /app

# Install dependencies first so source edits do not invalidate the layer cache.
COPY pyproject.toml README.md ./
COPY src ./src
RUN pip install --no-cache-dir .

# Run as an unprivileged user; the mounted volumes must be writable by it.
RUN useradd --create-home --uid 10001 bat \
    && mkdir -p /app/data /app/runtime \
    && chown -R bat:bat /app
USER bat

# Declared for documentation; bind them to persist state and supply server files.
VOLUME ["/app/data", "/app/runtime"]

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=5s --start-period=10s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://127.0.0.1:8000/api/v1/health', timeout=4).status==200 else 1)"

CMD ["bat", "serve-api", "--host", "0.0.0.0", "--port", "8000"]
