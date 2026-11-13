"""What the worker decides for each message, without RabbitMQ."""

import json
import logging

import pytest

from app import consumer
from app.consumer import Decision, Notifier
from app.telegram import ChatUnavailable, RejectedMessage, SetupFailure, TemporaryFailure

from test_messages import event_body


class FakeSender:
    def __init__(self, fail_with=None):
        self.sent = []
        self.fail_with = fail_with

    def send(self, chat_id, text):
        if self.fail_with:
            raise self.fail_with
        self.sent.append((chat_id, text))


def raw(body):
    return json.dumps(body).encode()


def test_sends_to_the_pizzeria_and_acks():
    sender = FakeSender()

    assert Notifier(sender, "-100123").handle(raw(event_body())) is Decision.ACK
    [(chat, text)] = sender.sent
    assert chat == "-100123"
    assert text.startswith("🍕 New order 9b2e1c4a")


def test_without_a_pizzeria_chat_nothing_is_sent_but_the_event_is_done():
    sender = FakeSender()

    assert Notifier(sender, "").handle(raw(event_body())) is Decision.ACK
    assert sender.sent == []


def test_a_duplicate_event_is_sent_once():
    sender = FakeSender()
    notifier = Notifier(sender, "-100123")

    assert notifier.handle(raw(event_body())) is Decision.ACK
    assert notifier.handle(raw(event_body())) is Decision.ACK
    assert len(sender.sent) == 1


def test_only_recent_events_are_remembered(monkeypatch):
    monkeypatch.setattr(consumer, "SEEN_EVENTS", 2)
    sender = FakeSender()
    notifier = Notifier(sender, "-100123")
    for n in range(3):
        notifier.handle(raw(event_body(event_id=f"id-{n}")))

    notifier.handle(raw(event_body(event_id="id-0")))  # forgotten: sent again
    notifier.handle(raw(event_body(event_id="id-2")))  # still remembered
    assert len(sender.sent) == 4


@pytest.mark.parametrize("body", [b"not json", b"[]", raw(event_body(version=2)), raw(event_body(order={}))])
def test_unreadable_messages_are_dead_lettered(body, caplog):
    sender = FakeSender()

    assert Notifier(sender, "-100123").handle(body) is Decision.DEAD_LETTER
    assert sender.sent == []


def test_unreadable_message_body_is_not_logged(caplog):
    caplog.set_level(logging.INFO)
    body = event_body(order={"customer_name": "Maria Secreta"})

    Notifier(FakeSender(), "-100123").handle(raw(body))

    assert "Maria Secreta" not in caplog.text


def test_unknown_event_types_are_acked_without_sending():
    sender = FakeSender()

    assert Notifier(sender, "-100123").handle(raw(event_body(type="order.refunded"))) is Decision.ACK
    assert sender.sent == []


def test_a_message_telegram_refuses_is_dead_lettered():
    sender = FakeSender(fail_with=RejectedMessage("Telegram answered 400: message is too long"))

    assert Notifier(sender, "-100123").handle(raw(event_body())) is Decision.DEAD_LETTER


@pytest.mark.parametrize("failure", [TemporaryFailure("down"), SetupFailure("401")])
def test_retryable_failures_reach_the_consumer(failure):
    notifier = Notifier(FakeSender(fail_with=failure), "-100123")

    with pytest.raises(type(failure)):
        notifier.handle(raw(event_body()))


def test_a_failed_event_is_not_remembered_as_handled():
    """After a temporary failure, the retry must really send it."""
    sender = FakeSender(fail_with=TemporaryFailure("down"))
    notifier = Notifier(sender, "-100123")
    with pytest.raises(TemporaryFailure):
        notifier.handle(raw(event_body()))

    sender.fail_with = None
    assert notifier.handle(raw(event_body())) is Decision.ACK
    assert len(sender.sent) == 1


# --- Customers (ADR 0006) -------------------------------------------------------


class ScriptedSender:
    """Fails for chosen chats: {chat: [exception, exception, ...]} in order."""

    def __init__(self, failures=None):
        self.sent = []
        self.failures = {str(k): list(v) for k, v in (failures or {}).items()}

    def send(self, chat_id, text):
        queue = self.failures.get(str(chat_id))
        if queue:
            raise queue.pop(0)
        self.sent.append((chat_id, text))


class FakeApi:
    def __init__(self):
        self.unfollowed = []

    def unfollow_all(self, chat_id):
        self.unfollowed.append(chat_id)
        return 1


def changed(status="preparing", chats=(111, 222), event_id="ev-1"):
    order = {**event_body()["order"], "status": status, "previous_status": "received"}
    return raw(event_body(event_id=event_id, type="order.status_changed", order=order, notify={"telegram_chat_ids": list(chats)}))


def test_customers_get_their_message_after_the_pizzeria():
    sender = ScriptedSender()

    assert Notifier(sender, "-100123").handle(changed()) is Decision.ACK

    assert [chat for chat, _ in sender.sent] == ["-100123", 111, 222]
    assert "Received → Being prepared" in sender.sent[0][1]
    assert sender.sent[1][1] == "Zé's Pizzeria\nYour order 9b2e1c4a is being prepared. 🍕"


def test_customers_get_messages_without_a_pizzeria_chat():
    sender = ScriptedSender()

    Notifier(sender, "").handle(changed())

    assert [chat for chat, _ in sender.sent] == [111, 222]


def test_a_retry_after_a_failure_does_not_repeat_messages_already_sent():
    sender = ScriptedSender({222: [TemporaryFailure("Telegram is down")]})
    notifier = Notifier(sender, "-100123")

    with pytest.raises(TemporaryFailure):
        notifier.handle(changed())
    assert notifier.handle(changed()) is Decision.ACK

    assert [chat for chat, _ in sender.sent] == ["-100123", 111, 222]  # each once


def test_a_customer_who_blocked_the_bot_is_skipped_and_unlinked():
    sender = ScriptedSender({111: [ChatUnavailable("Telegram answered 403: bot was blocked by the user")]})
    api = FakeApi()

    assert Notifier(sender, "-100123", api=api).handle(changed()) is Decision.ACK

    assert [chat for chat, _ in sender.sent] == ["-100123", 222]
    assert api.unfollowed == [111]


def test_unlinking_a_blocked_customer_is_best_effort():
    class BrokenApi:
        def unfollow_all(self, chat_id):
            raise RuntimeError("API down")

    sender = ScriptedSender({111: [ChatUnavailable("403")]})

    assert Notifier(sender, "", api=BrokenApi()).handle(changed()) is Decision.ACK
    assert [chat for chat, _ in sender.sent] == [222]


def test_a_message_refused_for_one_customer_does_not_stop_the_others():
    sender = ScriptedSender({111: [RejectedMessage("Telegram answered 400: message is too long")]})

    assert Notifier(sender, "-100123").handle(changed()) is Decision.ACK
    assert [chat for chat, _ in sender.sent] == ["-100123", 222]


def test_the_pizzeria_chat_being_unavailable_keeps_the_message():
    """Unlike a customer, the pizzeria's chat is configuration: fix it, don't skip it."""
    sender = ScriptedSender({"-100123": [ChatUnavailable("Telegram answered 403: bot was kicked")]})

    with pytest.raises(ChatUnavailable):
        Notifier(sender, "-100123", api=FakeApi()).handle(changed())
    assert sender.sent == []


def test_a_message_refused_for_the_pizzeria_is_dead_lettered_before_customers():
    sender = ScriptedSender({"-100123": [RejectedMessage("400")]})

    assert Notifier(sender, "-100123").handle(changed()) is Decision.DEAD_LETTER
    assert sender.sent == []


def test_the_pizzeria_chat_can_also_follow_as_a_customer():
    sender = ScriptedSender()

    Notifier(sender, "-100123").handle(changed(chats=[-100123]))

    texts = [text for _, text in sender.sent]
    assert len(texts) == 2
    assert texts[0].startswith("Order 9b2e1c4a")
    assert texts[1].startswith("Zé's Pizzeria")


def test_a_duplicate_event_sends_nothing_to_anyone():
    sender = ScriptedSender()
    notifier = Notifier(sender, "-100123")

    notifier.handle(changed())
    notifier.handle(changed())

    assert len(sender.sent) == 3
