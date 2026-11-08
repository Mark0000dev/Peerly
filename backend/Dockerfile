# Context: backend/. Immutable refs reviewed 2026-11-07; refresh deliberately.
FROM ghcr.io/astral-sh/uv:0.13.7@sha256:96f40d3904aad8d0bd010539001d36c8e2188b981e1334471a90c4a1d93bb490 AS uv
FROM python:3.12.16-slim-bookworm@sha256:935c3c5b12357a7e10caa9c1e6ca5692344d97cf229832ef584be2cec9fc03df AS python
FROM python AS dependencies
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never UV_LINK_MODE=copy UV_PROJECT_ENVIRONMENT=/opt/venv
WORKDIR /build
COPY pyproject.toml uv.lock .python-version ./
# No project build backend resolution, development tools or source builds.
RUN uv sync --locked --no-dev --no-install-project --no-build --no-cache

FROM python AS runtime
ENV PATH="/opt/venv/bin:$PATH" PYTHONPATH=/app/src \
    PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 HOME=/nonexistent TMPDIR=/tmp
WORKDIR /app
COPY --from=dependencies /opt/venv /opt/venv
COPY src/studymate/ /app/src/studymate/
COPY migrations/ /app/migrations/
COPY alembic.ini /app/alembic.ini
# Numeric identity requires neither root entrypoint nor a writable home.
USER 10001:10001
EXPOSE 8000
STOPSIGNAL SIGTERM
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/api/health', timeout=2).close()"]
CMD ["python", "-m", "studymate.server", "--host", "0.0.0.0", "--port", "8000"]
