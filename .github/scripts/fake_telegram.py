"""A fake Telegram Bot API for end-to-end tests (standard library only).

The worker talks to it as if it were api.telegram.org (TELEGRAM_API_URL):

- POST /bot<token>/getUpdates   long polling, answers with injected updates
- POST /bot<token>/sendMessage  records the message; answers 403 for chats
                                listed in BLOCKED_CHATS (the bot was blocked)

The test drives it with:

- POST /_inject {"chat_id": 555, "text": "/start <order id>"}  as if a person wrote to the bot
- GET  /_sent                                                  every message the bot sent
- POST /_block {"chat_id": 666}                                that chat blocks the bot

Usage: fake_telegram.py [port]   (default 8081)
"""

import json
import sys
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

lock = threading.Condition()
updates = []  # waiting to be fetched
next_update_id = 1
sent = []
blocked = set()


class Handler(BaseHTTPRequestHandler):
    def _json(self, status, payload):
        data = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _body(self):
        length = int(self.headers.get("Content-Length") or 0)
        return json.loads(self.rfile.read(length)) if length else {}

    def do_GET(self):
        if self.path == "/_sent":
            with lock:
                return self._json(200, sent)
        self._json(404, {"ok": False, "description": "Not Found"})

    def do_POST(self):
        global next_update_id
        body = self._body()
        if self.path == "/_inject":
            with lock:
                chat_id = body["chat_id"]
                updates.append(
                    {
                        "update_id": next_update_id,
                        "message": {
                            "message_id": next_update_id,
                            "chat": {"id": chat_id, "type": "private" if chat_id > 0 else "group"},
                            "text": body["text"],
                        },
                    }
                )
                next_update_id += 1
                lock.notify_all()
            return self._json(200, {"ok": True})
        if self.path == "/_block":
            with lock:
                blocked.add(body["chat_id"])
            return self._json(200, {"ok": True})

        method = self.path.rsplit("/", 1)[-1]
        if method == "getUpdates":
            offset = body.get("offset") or 0
            deadline = time.monotonic() + min(float(body.get("timeout", 0)), 5)
            with lock:
                # Confirm (drop) everything before the offset, as Telegram does.
                updates[:] = [u for u in updates if u["update_id"] >= offset]
                while not updates and time.monotonic() < deadline:
                    lock.wait(deadline - time.monotonic())
                return self._json(200, {"ok": True, "result": list(updates)})
        if method == "sendMessage":
            with lock:
                if body["chat_id"] in blocked:
                    return self._json(403, {"ok": False, "description": "Forbidden: bot was blocked by the user"})
                sent.append({"chat_id": body["chat_id"], "text": body["text"]})
            return self._json(200, {"ok": True, "result": {"message_id": len(sent)}})
        self._json(404, {"ok": False, "description": "Not Found"})

    def log_message(self, *args):
        pass


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8081
    ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
