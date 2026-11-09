"""Application settings, read from environment variables."""

import os


class Settings:
    """Runtime configuration.

    Docker Compose sets DATABASE_URL. When running the API locally without
    Docker, it falls back to a SQLite file so the app still starts; the tests
    override it with an in-memory SQLite database.
    """

    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./slicepizza.db")


settings = Settings()
