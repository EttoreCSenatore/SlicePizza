import pytest

from app.config import ConfigError, load_settings

NAMES = (
    "RABBITMQ_HOST",
    "RABBITMQ_PORT",
    "RABBITMQ_USER",
    "RABBITMQ_PASSWORD",
    "RABBITMQ_VHOST",
    "TELEGRAM_BOT_TOKEN",
    "TELEGRAM_PIZZERIA_CHAT_ID",
    "TELEGRAM_API_URL",
    "WORKER_HEARTBEAT_FILE",
)


@pytest.fixture
def env(monkeypatch):
    for name in NAMES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("RABBITMQ_HOST", "rabbitmq")
    monkeypatch.setenv("RABBITMQ_USER", "slicepizza")
    monkeypatch.setenv("RABBITMQ_PASSWORD", "p@ss")
    return monkeypatch


def test_defaults(env):
    s = load_settings()

    assert (s.rabbitmq_port, s.rabbitmq_vhost) == (5672, "/")
    assert s.telegram_bot_token == ""
    assert s.telegram_pizzeria_chat_id == ""
    assert s.telegram_api_url == "https://api.telegram.org"


@pytest.mark.parametrize("missing", ["RABBITMQ_HOST", "RABBITMQ_USER", "RABBITMQ_PASSWORD"])
def test_rabbitmq_settings_are_required(env, missing):
    env.delenv(missing)

    with pytest.raises(ConfigError, match=missing):
        load_settings()


@pytest.mark.parametrize("chat_id", ["-1001234567890", "123456", "@zes_pizzeria"])
def test_valid_chat_ids(env, chat_id):
    env.setenv("TELEGRAM_PIZZERIA_CHAT_ID", chat_id)

    assert load_settings().telegram_pizzeria_chat_id == chat_id


@pytest.mark.parametrize("chat_id", ["pizzeria", "https://t.me/zes", "12 34", "--5", "-", "@", "@a b"])
def test_invalid_chat_ids_are_refused(env, chat_id):
    env.setenv("TELEGRAM_PIZZERIA_CHAT_ID", chat_id)

    with pytest.raises(ConfigError, match="TELEGRAM_PIZZERIA_CHAT_ID"):
        load_settings()


def test_repr_hides_the_secrets(env):
    env.setenv("TELEGRAM_BOT_TOKEN", "123:SECRET")

    text = repr(load_settings())

    assert "SECRET" not in text
    assert "p@ss" not in text
    assert "telegram=on" in text
