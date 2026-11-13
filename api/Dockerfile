# Keep the version in api/.python-version: the lock files are resolved for it,
# and CI fails if the two differ.
FROM python:3.15-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# requirements.txt is a lock file: exact versions and sha256 hashes (see
# "Dependencies" in README.md). --require-hashes refuses any file whose hash is
# not in it; --only-binary refuses to compile anything from source, because the
# tools pip would download for that are not hash-checked.
COPY requirements.txt .
RUN pip install --no-cache-dir --require-hashes --only-binary=:all: -r requirements.txt

COPY app ./app

# Run as an unprivileged user instead of root.
RUN useradd --create-home --uid 10001 app
USER app

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
