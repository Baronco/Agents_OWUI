# Python 3.13 slim (Debian Bookworm) base
FROM python:3.13-slim-bookworm

# Bring in the uv binary
COPY --from=ghcr.io/astral-sh/uv:0.10.4 /uv /uvx /bin/

WORKDIR /app

# Dependency layer first (cached unless pyproject/uv.lock change)
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project

# Application source. Secrets (.env) are excluded via .dockerignore;
# configuration comes only from environment values at runtime.
COPY api.py ./
COPY src/ ./src/
COPY tools/ ./tools/
COPY utils/ ./utils/

# Finalize the environment
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen

# Create an unprivileged user; build steps above run as root (package install),
# runtime drops to `app` to reduce risk from container compromise.
RUN groupadd -r app \
    && useradd -r -g app -d /home/app -m -s /bin/bash app \
    && chown -R app:app /app

ENV HOME=/home/app
USER app

EXPOSE 8000

# Run the real FastAPI entrypoint (api.py exposes `app`), bound to 0.0.0.0
# so the port is reachable from outside the container. PORT is REQUIRED: it
# tells the app which internal port to listen on (it must match the right
# side of the -p HOST:CONTAINER mapping). Clouds like Azure set PORT
# themselves; locally you set it with -e PORT=... or in .env.
CMD ["sh", "-c", "exec uv run uvicorn api:app --host 0.0.0.0 --port $PORT"]
