# Interfaces — capture & ask from anywhere

Every channel flows through one edge Worker. **Captures are classified and routed to
TickTick at the edge, instantly** (~5s, no waiting for the Mac's cycle). Captures that
contain only prose stay queued and become vault notes on the Mac's next pass (it owns
the vault + diagrams). "Ask" queries hit
semantic search (Vectorize) directly.

Endpoints (Worker): `POST /capture`, `GET /ask`, `POST /whatsapp/<token>`,
`email()` handler, and a gated web app at `/app`. All bearer-gated with `INGEST_TOKEN`
(the web app uses Cloudflare Access instead).

## 1. Web "Ask" page (no app)
Open `https://<worker-subdomain>.workers.dev/app` on your phone — it's behind
**Cloudflare Access** (only your email). A chat box for ask-my-notes + a quick-capture
box. Bookmark it / add to home screen.

> Run **`d2d shortcuts`** to print your URLs + token pre-filled for the steps below.

## 2. Apple Shortcuts (most native)
Create two Shortcuts (Shortcuts app → +):

**"Capture to doing2done"**
1. `Get Contents of URL`
   - URL: `https://<worker-subdomain>.workers.dev/capture`
   - Method: `POST` · Headers: `Authorization: Bearer <INGEST_TOKEN>`
   - Request Body (JSON): `{ "source": "shortcut", "text": [Shortcut Input] }`
2. Enable **Use with Share Sheet** (input: text) and add to Home Screen.
   Say "Hey Siri, Capture to doing2done" or share text → it.

**"Ask my notes"**
1. `Ask for Input` (Text) → "What do you want to know?"
2. `Get Contents of URL`
   - URL: `https://<worker-subdomain>.workers.dev/ask?q=[Provided Input]`
   - Headers: `Authorization: Bearer <INGEST_TOKEN>`
3. `Get Dictionary from Input` → `Show Result` (or Speak) the `hits`.

## 3. Email capture
Cloudflare Dashboard → your domain → **Email Routing** → **Email Workers** →
route an address (e.g. `capture@your-domain`) to the **doing2done** Worker.
Or run **`d2d wire-email capture@your-domain`** (needs the token to have *Zone > Email Routing Rules > Edit*).
Then email a thought to that address; the Worker's `email()` handler queues it.

## 4. Telegram bot (your own bot, instant)

1. Create a bot: message **@BotFather** on Telegram -> `/newbot` -> copy the token.
2. Wire it in one command:
   ```
   uv run d2d telegram-setup <bot-token>
   ```
   (sets the Worker secret + registers the webhook)
3. Message your bot:
   - any thought -> classified + routed to TickTick **instantly** (edge)
   - `ask what did I decide about X` -> semantic search over your notes


### Voice notes

Send a voice note instead of typing — it's transcribed at the edge (Workers AI
Whisper) and takes the same classify -> route path. The reply echoes what it heard,
so a mishearing is obvious immediately.

### Reply to fix it

Reply to the bot's confirmation to correct what it did:

| You reply | What happens |
|---|---|
| `tomorrow 6pm` / `next monday` | re-dates the task (timed reminder if you give a time) |
| `list: Work` | moves it to that TickTick list |
| `not a todo` / `drop it` | deletes the task |

Every correction is logged to the `corrections` table — raw material for new eval cases.

> TickTick's Open API cannot move a task between lists (a cross-project update
> returns 200 and silently does nothing), so a move is implemented as
> recreate-in-target + delete-original. The task id changes; `task_map` follows it.

## 5. WhatsApp via Hermes Agent (own number, no verification, no Twilio)

[Hermes Agent](https://hermes-agent.nousresearch.com/docs/) (Nous Research) runs a
Baileys WhatsApp bridge — **your own number, no Meta verification**. It uses
doing2done as **MCP tools**. Needs an always-on host (e.g. Hetzner) + Node 18.

1. Install Hermes Agent on your host and pair WhatsApp: `hermes whatsapp` (scan the QR).
2. Point Hermes at doing2done's tools — **either**:

   **a) Remote (no install)** — the Worker hosts MCP over HTTP:
   ```
   hermes mcp add doing2done --url https://<worker-subdomain>.workers.dev/mcp
   ```
   (bearer-gated with `INGEST_TOKEN`; exposes `ask_notes` + `capture` — the edge-native tools)

   **b) Local (all four tools)** — needs doing2done + `.env` on that host:
   ```
   uv sync --extra mcp
   hermes mcp add doing2done --command "uv run d2d-mcp"
   ```
   (adds `add_todo` + `daily_brief`, which need your todo-provider credentials)
3. Restrict access: `WHATSAPP_ALLOWED_USERS=<your number>` in `~/.hermes/.env`.
4. Run as a service: `hermes gateway install`.

Now WhatsApp yourself:
- *"capture: call the dentist at 3pm"* → `capture` tool
- *"what did I note about the Clickhouse migration?"* → `ask_notes` (semantic)
- *"add todo: review PRs, high priority, Work"* → `add_todo`
- *"what's my daily brief?"* → `daily_brief`

`ask_notes` + `capture` work anywhere (they hit the edge Worker); `add_todo` +
`daily_brief` need doing2done's `.env` (todo-provider creds) on the host running the MCP.

> The same MCP server works with **Claude Desktop, Cursor, or any MCP client** —
> `d2d-mcp` exposes doing2done to any agent.

Sources: [Hermes WhatsApp](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/whatsapp) ·
[Hermes MCP](https://hermes-agent.nousresearch.com/docs/user-guide/features/mcp)


## 6. Voice capture (free — no transcription pipeline)

Siri already dictates, so voice capture is just a Shortcut:

1. Duplicate **"Capture to doing2done"**, name it **"Note to self"**.
2. Make the first action `Dictate Text`.
3. Use its output as `text` in the request body:
   `{ "source": "voice", "text": [Dictated Text] }`
4. Say **"Hey Siri, Note to self"** → speak → it lands in the capture queue and
   syncs into todos/notes on the next cycle.

Works on iPhone, Watch, AirPods, and CarPlay. (This is why a separate voice-memo
transcription pipeline was dropped — dictation covers the capture case for free.)

## Scheduler
`d2d capture` (in the launchd loop) pulls + processes queued captures every cycle.

## Sharing one note

The vault sits behind Cloudflare Access. To show someone a single note without
letting them into the vault, mint a link served from the Worker instead:

```
uv run d2d share "kubernetes concepts"      # 30-day link, prints the URL
uv run d2d share "k8s" --days 0             # no expiry
uv run d2d shares                           # list links, state, view counts
uv run d2d unshare RNqPYBkxZMPX             # revoke (token prefix is enough)
uv run d2d unshare --all                    # revoke everything, now
```

Nothing is public unless a token exists for it. The page is `noindex, nofollow,
noarchive`, sends no referrer, and isn't listed anywhere — the 43-char token is the
only way in. Notes render to HTML **before** upload with raw HTML disabled, so a
`<script>` in a note can never become live markup on a public page. Vault-relative
links, assets, and the Related block are stripped: they'd 404 off-site or leak
other note titles.
