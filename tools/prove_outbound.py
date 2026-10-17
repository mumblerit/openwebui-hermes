#!/usr/bin/env python3
"""Standalone outbound proof for the Open WebUI adapter's send() path.

Posts one message to an Open WebUI channel using ONLY the REST API +
a bot API key (no Socket.IO, no JWT, no Hermes), then reads it back
by ID to prove it landed. This is the exact transport the patched
adapter send() uses for cron / send_message delivery.

Usage:
    OPENWEBUI_URL=http://host:3000 \
    OPENWEBUI_API_KEY=sk-... \
    OPENWEBUI_CHANNEL_NAME='#hermes' \
    python3 tools/prove_outbound.py ["custom message text"]

Endpoints (verified against open-webui backend/open_webui/routers/channels.py):
    GET  /api/v1/auths/                              -> bot user id
    GET  /api/v1/channels/                           -> resolve name -> id
    POST /api/v1/channels/{id}/messages/post         -> {content, data} -> MessageModel
    GET  /api/v1/channels/{id}/messages/{message_id} -> verify
"""
import json
import os
import sys
import urllib.request
import urllib.error

BASE = os.environ.get("OPENWEBUI_URL", "").rstrip("/")
KEY = os.environ.get("OPENWEBUI_API_KEY", "")
CHANNEL = os.environ.get("OPENWEBUI_CHANNEL_NAME", "")


def call(method, path, body=None):
    req = urllib.request.Request(
        BASE + path,
        method=method,
        data=json.dumps(body).encode() if body is not None else None,
        headers={"Authorization": f"Bearer {KEY}", "Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read().decode() or "null")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:400]


def main() -> int:
    if not BASE or not KEY or not CHANNEL:
        print("Set OPENWEBUI_URL, OPENWEBUI_API_KEY, OPENWEBUI_CHANNEL_NAME", file=sys.stderr)
        return 2

    status, me = call("GET", "/api/v1/auths/")
    if status >= 400 or not isinstance(me, dict) or not me.get("id"):
        print(f"FAIL auth: {status} {me}")
        return 1
    print(f"authed as {me.get('name')} ({me['id']})")

    # Resolve channel: treat CHANNEL as an ID if it isn't a name.
    channel_id = CHANNEL
    if CHANNEL.startswith("#") or " " in CHANNEL:
        status, channels = call("GET", "/api/v1/channels/")
        found = None
        if isinstance(channels, list):
            want = CHANNEL.lstrip("#").lower()
            for ch in channels:
                if str(ch.get("name", "")).strip().lower() == want:
                    found = ch.get("id")
                    break
        if not found:
            print(f"FAIL channel {CHANNEL!r} not found via /api/v1/channels/")
            return 1
        channel_id = found
    print(f"channel {CHANNEL!r} -> {channel_id}")

    text = sys.argv[1] if len(sys.argv) > 1 else "✅ Outbound proof: Hermes can post here unprompted (REST send)."
    status, msg = call(
        "POST",
        f"/api/v1/channels/{channel_id}/messages/post",
        {"content": text, "data": {"files": []}},
    )
    if status >= 400 or not isinstance(msg, dict) or not msg.get("id"):
        print(f"FAIL post: {status} {msg}")
        return 1
    print(f"posted message_id={msg['id']}")

    status, back = call("GET", f"/api/v1/channels/{channel_id}/messages/{msg['id']}")
    if status >= 400 or not isinstance(back, dict):
        print(f"FAIL verify read-back: {status} {back}")
        return 1
    print("VERIFIED: message is persisted in the channel. Outbound path works.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
