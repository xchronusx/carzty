##xchronusx
# Carzty in a box. Good for Proxmox LXC/VM, TrueNAS apps, Unraid, a Pi, whatever.
# Prebuilt (amd64 + arm64): ghcr.io/xchronusx/carzty:latest
#
#   docker run --rm -it -v carzty-data:/app/data ghcr.io/xchronusx/carzty setup     # the wizard
#   docker run -d --name carzty --restart unless-stopped -v carzty-data:/app/data ghcr.io/xchronusx/carzty
#
# Everything (.env, the database, logs) lives in /app/data, so one volume is all you need.
# Author: Zachary Wright (xchronusx)

FROM python:3.12-slim

LABEL org.opencontainers.image.title="Carzty" \
      org.opencontainers.image.description="A Discord bot that nags you until you do the thing" \
      org.opencontainers.image.source="https://github.com/xchronusx/carzty" \
      org.opencontainers.image.licenses="MIT"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    CARZTY_HOME=/app/data \
    DATABASE_PATH=/app/data/carzty.db \
    LOG_DIR=/app/data/logs

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY carzty ./carzty
COPY .env.example ./.env.example

# don't run as root. a fresh named volume picks up this ownership automatically
RUN useradd --create-home --uid 10001 carzty \
    && mkdir -p /app/data \
    && chown -R carzty:carzty /app/data
USER carzty

VOLUME ["/app/data"]

ENTRYPOINT ["python", "-m", "carzty"]
CMD ["run"]
##xchronusx
