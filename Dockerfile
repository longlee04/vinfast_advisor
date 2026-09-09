# ---- Stage 1: Build ----
FROM python:3.11-slim AS builder

# uv binary (pinned)
COPY --from=ghcr.io/astral-sh/uv:0.11.21 /uv /bin/uv

WORKDIR /app

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/app/.venv

# Install runtime deps only (no dev group), cached separately from app code
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project

# ---- Stage 2: Production ----
FROM python:3.11-slim

WORKDIR /app

# Copy the resolved virtualenv from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH=/app/.venv/bin:$PATH

# Security: run as non-root user
RUN useradd -m appuser

# Copy application code
COPY . .

# Create data directory with correct ownership
RUN mkdir -p /app/data \
    && chmod +x /app/docker-entrypoint.sh /app/scripts/seed_all.sh \
    && chown -R appuser:appuser /app

USER appuser

EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health')" || exit 1

ENTRYPOINT ["/app/docker-entrypoint.sh"]

# KHONG them --workers: TurnEventBroker dang la ban in-memory, chi dung voi mot
# tien trinh. Xem src/agents/services/operations/turn_events.py truoc khi doi.
CMD ["uvicorn", "src.main:app", "--host", "0.0.0.0", "--port", "8000"]
