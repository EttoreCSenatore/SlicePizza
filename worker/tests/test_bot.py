"""The bot's commands (/start, /stop) and its getUpdates loop."""

import threading
import time

import pytest

from app.api_client import ApiUnavailable, OrderNotFound, TooManyFollowers
from app.bot import BotPoller
from app.messages import (
    REPLY_HELP,
    REPLY_STOPPED,
    REPLY_TOO_MANY,
    REPLY_UNAVAILABLE,
    REPLY_UNKNOWN_ORDER,
    REPLY_WELCOME,
)
from app.telegram import SetupFailure, TelegramSender, TemporaryFailure

from fakes import FakeServer

ORDER = "9b2e1c4a-0000-4000-8000-000000000000"


class FakeTelegram:
    def __init__(self, batches=()):
        self.sent = []
        self.batches = list(batches)  # each: a list of updates, or an exception
        self.offsets = []

    def send(self, chat_id, text):
        self.sent.append((chat_id, text))

    def get_me(self):
        return {"id": 42, "is_bot": True, "username": "ZesPizzeriaBot"}

    def get_updates(self, offset, timeout):
        self.offsets.append(offset)
        if not self.batches:
            time.sleep(0.01)
            return []
        batch = self.batches.pop(0)
        if isinstance(batch, Exception):
            raise batch
        return batch


class FakeApi:
    def __init__(self, status="preparing", error=None):
        self.status = status
        self.error = error
        self.followed = []
        self.unfollowed = []

    def follow(self, order_id, chat_id):
        if self.error:
            raise self.error
        self.followed.append((order_id, chat_id))
        return self.status

    def unfollow_all(self, chat_id):
        if self.error:
            raise self.error
        self.unfollowed.append(chat_id)
        return 1


def message(text, chat_id=111, chat_type="private", update_id=1):
    return {"update_id": update_id, "message": {"chat": {"id": chat_id, "type": chat_type}, "text": text}}


def poller(api=None, telegram=None):
    return BotPoller(telegram or FakeTelegram(), api, threading.Event())


# --- Commands -----------------------------------------------------------------------


def test_start_with_an_order_follows_it_and_answers_with_its_status():
    telegram, api = FakeTelegram(), FakeApi(status="preparing")

    poller(api, telegram).handle(message(f"/start {ORDER}"))

    assert api.followed == [(ORDER, 111)]
    [(chat, text)] = telegram.sent
    assert chat == 111
    assert "You're following order 9b2e1c4a" in text
    assert "is being prepared" in text


@pytest.mark.parametrize(
    ("error", "reply"),
    [(OrderNotFound(), REPLY_UNKNOWN_ORDER), (TooManyFollowers(), REPLY_TOO_MANY), (ApiUnavailable("down"), REPLY_UNAVAILABLE)],
)
def test_start_when_following_fails(error, reply):
    telegram = FakeTelegram()

    poller(FakeApi(error=error), telegram).handle(message(f"/start {ORDER}"))

    assert telegram.sent == [(111, reply)]


def test_start_without_an_order_says_hello():
    telegram, api = FakeTelegram(), FakeApi()

    poller(api, telegram).handle(message("/start"))

    assert telegram.sent == [(111, REPLY_WELCOME)]
    assert api.followed == []


def test_start_without_the_internal_token_says_try_later():
    telegram = FakeTelegram()

    poller(None, telegram).handle(message(f"/start {ORDER}"))

    assert telegram.sent == [(111, REPLY_UNAVAILABLE)]


def test_stop_unfollows_everything():
    telegram, api = FakeTelegram(), FakeApi()

    poller(api, telegram).handle(message("/stop"))

    assert api.unfollowed == [111]
    assert telegram.sent == [(111, REPLY_STOPPED)]


def test_commands_addressed_to_the_bot_in_a_group():
    telegram, api = FakeTelegram(), FakeApi()

    poller(api, telegram).handle(message(f"/start@ZesPizzeriaBot {ORDER}", chat_id=-100, chat_type="group"))

    assert api.followed == [(ORDER, -100)]


def test_commands_for_another_bot_in_the_same_group_are_ignored():
    """"/stop@OtherBot" must not unlink the pizzeria's group from its orders."""
    telegram, api = FakeTelegram(), FakeApi()
    bot = poller(api, telegram)
    bot.username = "zespizzeriabot"

    bot.handle(message("/stop@OtherBot", chat_id=-100, chat_type="group"))
    bot.handle(message("/stop@ZesPizzeriaBot", chat_id=-100, chat_type="group"))

    assert api.unfollowed == [-100]  # only the one addressed to us


def test_the_loop_learns_the_bots_username_first():
    telegram = FakeTelegram()
    bot = poller(FakeApi(), telegram)

    run_until(bot, lambda: telegram.offsets)

    assert bot.username == "zespizzeriabot"


def test_other_text_gets_help_in_private_but_is_ignored_in_groups():
    telegram = FakeTelegram()
    bot = poller(FakeApi(), telegram)

    bot.handle(message("hello?"))
    bot.handle(message("the oven is on fire", chat_id=-100, chat_type="group"))
    bot.handle(message("/unknown", chat_id=-100, chat_type="group"))

    assert telegram.sent == [(111, REPLY_HELP)]


@pytest.mark.parametrize(
    "update",
    [
        {"update_id": 1},
        {"update_id": 1, "message": "text"},
        {"update_id": 1, "message": {"chat": {"id": "111"}, "text": "/stop"}},
        {"update_id": 1, "message": {"chat": {"id": 111}, "photo": []}},
        {"update_id": 1, "message": {"chat": {"id": True}, "text": "/stop"}},
    ],
)
def test_updates_that_are_not_text_messages_are_ignored(update):
    telegram, api = FakeTelegram(), FakeApi()

    poller(api, telegram).handle(update)

    assert telegram.sent == []
    assert api.unfollowed == []


def test_a_failed_reply_is_only_logged():
    class FailingTelegram(FakeTelegram):
        def send(self, chat_id, text):
            raise TemporaryFailure("Telegram is down")

    poller(FakeApi(), FailingTelegram()).handle(message("/stop"))  # no exception


# --- The loop -------------------------------------------------------------------------


def run_until(bot, condition, timeout=3):
    thread = threading.Thread(target=bot.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline and not condition():
        time.sleep(0.01)
    bot._stop.set()
    thread.join(3)
    assert not thread.is_alive()


def test_each_update_is_confirmed_with_the_next_offset():
    telegram = FakeTelegram([[message("/stop", update_id=41), message("/stop", update_id=42)]])
    bot = poller(FakeApi(), telegram)

    run_until(bot, lambda: len(telegram.offsets) >= 2)

    assert telegram.offsets[:2] == [None, 43]


def test_an_update_that_crashes_the_handler_is_still_confirmed():
    class CrashingApi(FakeApi):
        def unfollow_all(self, chat_id):
            raise RuntimeError("bug")

    telegram = FakeTelegram([[message("/stop", update_id=7)]])

    run_until(poller(CrashingApi(), telegram), lambda: len(telegram.offsets) >= 2)

    assert telegram.offsets[1] == 8


def test_the_loop_survives_telegram_failures(monkeypatch):
    monkeypatch.setattr("app.bot.MAX_BACKOFF_SECONDS", 0.05)
    telegram = FakeTelegram([TemporaryFailure("down"), SetupFailure("401"), [message("/stop", update_id=5)]])
    api = FakeApi()

    run_until(poller(api, telegram), lambda: api.unfollowed)

    assert api.unfollowed == [111]


# --- getUpdates over HTTP ----------------------------------------------------------------


def test_get_updates_asks_for_messages_with_the_offset():
    answer = {"ok": True, "result": [message("/stop", update_id=9)]}
    with FakeServer(lambda method, path, body, headers: (200, answer)) as server:
        updates = TelegramSender("123:SECRET", server.url).get_updates(offset=9, timeout=0)

    assert updates[0]["update_id"] == 9
    [request] = server.requests
    assert request["path"] == "/bot123:SECRET/getUpdates"
    assert request["json"] == {"timeout": 0, "allowed_updates": ["message"], "offset": 9}


def test_get_updates_conflict_is_temporary():
    """409: another process polls the same bot (or a webhook is set)."""
    answer = {"ok": False, "description": "Conflict: terminated by other getUpdates request"}
    with FakeServer(lambda method, path, body, headers: (409, answer)) as server:
        with pytest.raises(TemporaryFailure, match="409"):
            TelegramSender("123:SECRET", server.url).get_updates(offset=None, timeout=0)


def test_get_me_reads_the_username():
    answer = {"ok": True, "result": {"id": 42, "is_bot": True, "username": "ZesPizzeriaBot"}}
    with FakeServer(lambda method, path, body, headers: (200, answer)) as server:
        assert TelegramSender("123:SECRET", server.url).get_me()["username"] == "ZesPizzeriaBot"
    assert server.requests[0]["path"] == "/bot123:SECRET/getMe"
