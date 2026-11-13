# Content Factory runtime: daemon, CLI and one-shot jobs.
# Build:  docker build -t content-factory .
# Run:    docker run --rm --env-file .env -v "$PWD/data:/app/data" content-factory daemon
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

# Pillow wheels are self-contained, but ca-certificates are needed for RSS/APIs.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY content_factory ./content_factory
COPY scripts ./scripts
COPY config ./config
COPY assets ./assets

RUN mkdir -p data/outbox data/logs data/reports data/locks \
    && groupadd --system app \
    && useradd --system --gid app --home-dir /app app \
    && chown -R app:app /app
USER app

HEALTHCHECK --interval=60s --timeout=10s --start-period=20s --retries=3 \
    CMD ["python", "-m", "content_factory", "--version"]

ENTRYPOINT ["python", "-m", "content_factory"]
CMD ["daemon"]
