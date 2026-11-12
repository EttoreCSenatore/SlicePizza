"""The app lifespan: wait for the database, create the schema and seed the menu."""

from fastapi.testclient import TestClient

from app.database import Base, engine
from app.main import app


def test_startup_creates_schema_and_seeds_menu():
    Base.metadata.drop_all(bind=engine)

    # Using TestClient as a context manager runs the lifespan.
    with TestClient(app) as client:
        response = client.get("/menu")

    assert response.status_code == 200
    assert len(response.json()) == 5


def test_startup_does_not_duplicate_the_menu():
    # The autouse fixture already created and seeded the schema.
    with TestClient(app) as client:
        response = client.get("/menu")

    assert len(response.json()) == 5
