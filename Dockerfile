# Python 3.13 slim (Debian Bookworm) base
FROM python:3.13-slim-bookworm

# Bring in the uv binary
COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /uvx /bin/

WORKDIR /app

# Dependency layer first (cached unless pyproject/uv.lock change)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Application source. The real config/tenants.json, .env, users/ and
# token_store.json are excluded via .dockerignore, so only code + the config
# TEMPLATE (config/tenants.json.example) land in the image.
COPY api.py ./
COPY src/ ./src/
COPY owui_tools/ ./owui_tools/
COPY config/ ./config/

# Finalize the environment
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# Create an unprivileged user; build steps above run as root (package install),
# runtime drops to `app` to reduce risk from container compromise.
RUN groupadd -r app \
    && useradd -r -g app -d /home/app -m -s /bin/bash app \
    && mkdir -p /data/config /data/users \
    && chown -R app:app /app /data

ENV HOME=/home/app
# Per-environment data lives on the mounted volume at /data
ENV TENANTS_CONFIG_PATH=/data/config/tenants.json
ENV USERS_DIR=/data/users
USER app

EXPOSE 8000

# Run the real FastAPI entrypoint (api.py exposes `app`), bound to 0.0.0.0
# so the port is reachable from outside the container.
CMD ["uv", "run", "uvicorn", "api:app", "--host", "0.0.0.0", "--port", "8000"]
