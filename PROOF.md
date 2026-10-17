# Outbound proof: Hermes -> Open WebUI channel

Goal: prove the gateway can deliver *to* Open WebUI unprompted
(cron / notifications), not just reply when @mentioned. Everything is
LAN / WireGuard-local — Hermes and Open WebUI are on the home network,
no public endpoint, no webhook exposure.

## What changed in this fork

`plugin/adapter.py`:

- `send()` (the `BasePlatformAdapter` method Hermes core calls for
  cron delivery and the `send_message` tool) now posts via REST:
  `POST /api/v1/channels/{id}/messages/post` with the bot's API key.
  No Socket.IO session or JWT needed for outbound.
- It returns an honest `SendResult`: success only on a 2xx with a
  message ID; on failure it returns the REST error (a Socket.IO emit
  is attempted as best-effort but never reported as success — emit
  has no delivery ack).
- Targets resolve by channel ID or by the configured/home channel
  name, so `--deliver openwebui` (home channel) and
  `--deliver openwebui:<id>` both work.
- `_send_socket()` falls back to the same REST post when the socket
  is down, so thread replies survive a dead JWT/socket too.
- No more "Hermes online!" spam on every gateway connect
  (opt in with `OPENWEBUI_ANNOUNCE=true`).

Endpoint and payload verified against open-webui source
(`backend/open_webui/routers/channels.py`,
`backend/open_webui/models/messages.py` `MessageForm`).

## Step 0 — prove the transport without Hermes (2 minutes)

With a bot user in Open WebUI, that bot a member of the channel:

```bash
OPENWEBUI_URL=http://<owui-host>:3000 \
OPENWEBUI_API_KEY=<bot-api-key> \
OPENWEBUI_CHANNEL_NAME='#hermes' \
python3 tools/prove_outbound.py
```

Expect: `VERIFIED: message is persisted in the channel.`

## Step 1 — install the plugin on the Hermes box

```bash
mkdir -p ~/.hermes/plugins/openwebui
cp plugin/adapter.py plugin/__init__.py plugin/plugin.yaml ~/.hermes/plugins/openwebui/
pip install python-socketio aiohttp   # into the Hermes venv, if missing
```

In the profile's `.env` (or `config.yaml` `extra:`):

```bash
OPENWEBUI_URL=http://<owui-host>:3000
OPENWEBUI_API_KEY=<bot-api-key>
OPENWEBUI_CHANNEL_NAME=#hermes
OPENWEBUI_HOME_CHANNEL=#hermes
# inbound (Socket.IO) still needs one of:
OPENWEBUI_JWT_TOKEN=<...>        # or
OPENWEBUI_EMAIL=<bot-email>
OPENWEBUI_PASSWORD=<bot-password>
```

```bash
hermes gateway restart
```

## Step 2 — one cron delivery

```bash
mkdir -p ~/.hermes/scripts
printf '#!/bin/sh\necho "⏰ owui cron proof: $(date)"\n' > ~/.hermes/scripts/owui_ping.sh
chmod +x ~/.hermes/scripts/owui_ping.sh
```

Create a `--no-agent` job delivering to Open WebUI and run it now
(exact `cron create` flags: check `hermes cron create --help` on the
box — delivery target is the platform name):

```bash
hermes cron create "every 1h" --no-agent --script owui_ping.sh --deliver openwebui --name owui-proof
hermes cron run <job_id>
hermes cron remove <job_id>   # when done proving
```

Pass condition: the ping lands in the OWUI channel as the bot user,
unprompted, and the cron run reports success. Failure condition that
matters: if REST posting fails, the run now reports the real HTTP
error instead of silently claiming delivery.
