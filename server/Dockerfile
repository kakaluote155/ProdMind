FROM python:3.12.12-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY requirements-runtime.lock ./requirements-runtime.lock
RUN pip install --no-cache-dir -r requirements-runtime.lock

COPY pyproject.toml README.md ./
COPY app ./app
RUN pip install --no-cache-dir --no-deps . \
    && groupadd --system prodmind \
    && useradd --system --gid prodmind --home-dir /app --no-create-home prodmind \
    && mkdir -p /data \
    && chown -R prodmind:prodmind /data

EXPOSE 8088

USER prodmind

HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8088/health', timeout=2)"]

CMD ["prodmind-server", "--host", "0.0.0.0", "--port", "8088"]
