"""The worker's client for the API's /internal routes, against a fake API."""

import pytest

from app.api_client import ApiClient, ApiUnavailable, OrderNotFound, TooManyFollowers

from fakes import FakeServer

TOKEN = "SECRET-internal-token-0123456789abcdef"
ORDER = "9b2e1c4a-0000-4000-8000-000000000000"


def api(status, payload):
    return FakeServer(lambda method, path, body, headers: (status, payload))


def test_follow_returns_the_status_and_sends_the_token():
    with api(200, {"order_id": ORDER, "status": "preparing", "created": True}) as server:
        status = ApiClient(server.url, TOKEN).follow(ORDER, -1001234)

    assert status == "preparing"
    [request] = server.requests
    assert request["method"] == "PUT"
    assert request["path"] == f"/internal/orders/{ORDER}/telegram-subscriptions/-1001234"
    assert request["headers"]["Authorization"] == f"Bearer {TOKEN}"


def test_unfollow_all():
    with api(200, {"removed": 2}) as server:
        assert ApiClient(server.url, TOKEN).unfollow_all(111) == 2

    assert server.requests[0]["method"] == "DELETE"
    assert server.requests[0]["path"] == "/internal/telegram-subscriptions/111"


def test_unknown_order():
    with api(404, {"detail": "Order not found"}) as server:
        with pytest.raises(OrderNotFound):
            ApiClient(server.url, TOKEN).follow(ORDER, 1)


def test_routes_turned_off_are_not_mistaken_for_an_unknown_order():
    """Without INTERNAL_API_TOKEN on the API, its routes answer a plain 404."""
    with api(404, {"detail": "Not Found"}) as server:
        with pytest.raises(ApiUnavailable, match="404"):
            ApiClient(server.url, TOKEN).follow(ORDER, 1)


def test_a_link_that_is_not_an_order_id_never_reaches_the_api():
    with api(200, {"status": "received"}) as server:
        with pytest.raises(OrderNotFound):
            ApiClient(server.url, TOKEN).follow("../../menu", 1)

    assert server.requests == []


def test_too_many_followers():
    with api(409, {"detail": "Too many chats follow this order"}) as server:
        with pytest.raises(TooManyFollowers):
            ApiClient(server.url, TOKEN).follow(ORDER, 1)


@pytest.mark.parametrize(("status", "payload"), [(401, {"detail": "Unauthorized"}), (500, {}), (200, {"unexpected": 1})])
def test_other_answers_mean_the_api_is_unavailable(status, payload):
    with api(status, payload) as server:
        with pytest.raises(ApiUnavailable) as raised:
            ApiClient(server.url, TOKEN).follow(ORDER, 1)

    assert "SECRET" not in str(raised.value)
    assert raised.value.__cause__ is None


def test_an_unreachable_api():
    with pytest.raises(ApiUnavailable, match="cannot reach"):
        ApiClient("http://127.0.0.1:9", TOKEN).unfollow_all(1)


def test_repr_hides_the_token():
    assert "SECRET" not in repr(ApiClient("http://api:8000", TOKEN))
