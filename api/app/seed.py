"""Seed data for the menu.

The menu lives in the database from Phase 1 on, so prices can change without
a deploy. In a later phase this will be replaced by proper migrations and an
admin endpoint.
"""

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .models import Pizza

DEFAULT_MENU = [
    {
        "name": "Margherita",
        "description": "Tomato sauce, mozzarella and fresh basil",
        "price_cents": 4500,
    },
    {
        "name": "Calabresa",
        "description": "Tomato sauce, mozzarella, sausage and onion",
        "price_cents": 5200,
    },
    {
        "name": "Portuguesa",
        "description": "Ham, mozzarella, egg, onion, olives and peas",
        "price_cents": 5500,
    },
    {
        "name": "Quatro Queijos",
        "description": "Mozzarella, gorgonzola, parmesan and catupiry",
        "price_cents": 5800,
    },
    {
        "name": "Frango com Catupiry",
        "description": "Shredded chicken, catupiry and oregano",
        "price_cents": 5600,
    },
]


def seed_menu(db: Session) -> None:
    """Insert the default menu if the pizzas table is empty."""
    pizza_count = db.scalar(select(func.count()).select_from(Pizza))
    if pizza_count:
        return

    db.add_all(Pizza(**pizza) for pizza in DEFAULT_MENU)
    db.commit()
