"""The worker's calls to the API's /internal routes (ADR 0006).

Standard library only, like the Telegram client. The token goes in the
Authorization header and never into an error message.
"""

import json
import urllib.error
import urllib.request
import uuid

TIMEOUT_SECONDS = 10


class ApiUnavailable(Exception):
    """The API could not answer (down, misconfigured, or an unexpected error)."""


class OrderNotFound(Exception):
    pass


class TooManyFollowers(Exception):
    pass


class ApiClient:
    def __init__(self, base_url: str, token: str) -> None:
        self._base = base_url.rstrip("/")
        self._token = token

    def __repr__(self) -> str:
        return f"ApiClient({self._base!r}, <token hidden>)"

    def follow(self, order_id: str, chat_id: int) -> str:
        """Make ``chat_id`` follow the order. Returns the order's current status."""
        try:
            order_id = str(uuid.UUID(order_id))
        except ValueError:
            raise OrderNotFound() from None
        answer = self._call("PUT", f"/internal/orders/{order_id}/telegram-subscriptions/{int(chat_id)}")
        try:
            return str(answer["status"])
        except (KeyError, TypeError):
            raise ApiUnavailable("the API sent an unexpected answer") from None

    def unfollow_all(self, chat_id: int) -> int:
        """Stop every order's updates to ``chat_id``. Returns how many were removed."""
        answer = self._call("DELETE", f"/internal/telegram-subscriptions/{int(chat_id)}")
        try:
            return int(answer["removed"])
        except (KeyError, TypeError, ValueError):
            raise ApiUnavailable("the API sent an unexpected answer") from None

    def _call(self, method: str, path: str) -> dict:
        request = urllib.request.Request(
            self._base + path,
            method=method,
            headers={"Authorization": f"Bearer {self._token}", "Accept": "application/json"},
        )
        route = path.split("/")[2]  # "orders" or "telegram-subscriptions", for messages
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            detail = _detail(error)
            # The API's own "Order not found", not the 404 of routes that are
            # off (INTERNAL_API_TOKEN unset on the API): that one is a setup
            # problem, and the customer must not be told their order is gone.
            if error.code == 404 and detail == "Order not found":
                raise OrderNotFound() from None
            if error.code == 409:
                raise TooManyFollowers() from None
            raise ApiUnavailable(
                f"the API answered {error.code} ({detail or 'no detail'}) to {method} /internal/{route}"
            ) from None
        except (urllib.error.URLError, TimeoutError, ConnectionError) as error:
            raise ApiUnavailable(f"cannot reach the API: {getattr(error, 'reason', error)}") from None
        except ValueError:
            raise ApiUnavailable("the API sent an answer that is not JSON") from None


def _detail(error: urllib.error.HTTPError) -> str:
    try:
        return str(json.loads(error.read() or b"{}").get("detail") or "")[:100]
    except (ValueError, OSError, AttributeError):
        return ""
    finally:
        error.close()
