FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# requirements.txt is a lock file: exact versions and sha256 hashes (see
# "Dependencies" in README.md), installed the same way as the API's.
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt

COPY app ./app

# Run as an unprivileged user instead of root, like the API.
RUN useradd --create-home --uid 10001 worker
USER worker

# No port: the worker only makes outgoing connections (RabbitMQ, Telegram).
CMD ["python", "-m", "app.main"]
