FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

RUN pip install --no-cache-dir \
    "fastapi>=0.116,<1.0" \
    "uvicorn[standard]>=0.35,<1.0" \
    "pydantic>=2.11,<3.0"

COPY app ./app

EXPOSE 8088

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8088"]
