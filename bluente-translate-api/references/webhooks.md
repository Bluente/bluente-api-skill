# Webhooks

A webhook lets Bluente call your server when a translation finishes, instead of you polling `/check`.

## Setup

- The webhook URL is an **account-level setting**: one URL per Bluente user, set in the web app under Settings → API keys (https://translate.bluente.com/settings/?type=apiKeys). There is no API to set it and no per-request callback URL.
- It fires for every translation started by that user, whichever key or app started it.
- To match a notification to your own job, send `meta_data` (any JSON object) on `POST /translate`; it comes back unchanged.

## Delivery

- `POST` to your URL with a JSON body and headers `Content-Type: application/json` and `User-Agent: Bluente-Translation-Webhook/1.0`.
- Sent when the translation finishes (`state: "READY"`) and when the translation step fails (`state: "ERROR"`).
- Respond with any `2xx` status within 30 seconds. A non-`2xx` response or a timeout is **not** redelivered.
- Not sent for problems found while the file is processed after upload (corrupt, password-protected, unsupported). Those only show on `/check`.
- Delivery is best-effort. Some failures may not produce a webhook, and the same task may be notified more than once.

## Payload

```json
{
  "task_id": 12345,
  "state": "READY",
  "filename": "contract.docx",
  "source_language": "en",
  "target_language": "fr",
  "page_count": 8,
  "engine": 3,
  "meta_data": { "job_id": "abc-123" },
  "user_id": "…",
  "created_at": "2026-10-08 11:32:59",
  "updated_at": "2026-10-08 11:36:03"
}
```

| Field | Type | Meaning |
|---|---|---|
| `task_id` | int | The `id` for `/check` and `/download`. |
| `state` | string | `READY` or `ERROR`. |
| `filename` | string | Task filename. |
| `source_language`, `target_language` | string | Language codes. |
| `page_count` | int | Pages in the document. |
| `engine` | int | Engine identifier. Don't rely on it to tell LLM from LLM Pro; record that in `meta_data` if you need it. |
| `meta_data` | object or null | Exactly what you sent to `/translate`; `null` if you sent none. |
| `user_id` | string | The user who started the translation. |
| `created_at`, `updated_at` | string | Timestamps. |

## Handling a webhook safely

**Requests are not signed.** Anyone who learns the URL can post a fake payload. So:

1. Treat the payload only as a hint that `task_id` may have changed.
2. Respond `2xx` quickly; do the work asynchronously.
3. Look up `task_id` (and your `meta_data` job ID) in your own records. Ignore task IDs you didn't create.
4. Call `GET /check?id=task_id` with your own API key. Act on the status it returns, not on `state` in the payload.
5. If `READY`, call `/download`. Make this idempotent — the same task may arrive twice.
6. Use a hard-to-guess URL path (for example with a random token in it) and HTTPS.

**Keep a polling fallback.** For each task you started, poll `/check` occasionally (for example every few minutes) until it reaches `READY` or a failure state, in case the webhook never arrives.

## Minimal receiver (Python / Flask)

```python
import os, requests
from flask import Flask, request

BASE = "https://api.bluente.com/api/20250924/blu_translate"
HEADERS = {"Authorization": f"Bearer {os.environ['BLUENTE_API_KEY']}"}
app = Flask(__name__)

def enqueue_check(task_id: int) -> None:
    """Hand off to your own job queue, which later calls handle_task(task_id)."""
    ...

@app.post("/bluente-webhook/<token>")
def bluente_webhook(token):
    if token != os.environ["BLUENTE_WEBHOOK_TOKEN"]:
        return "", 404
    payload = request.get_json(silent=True) or {}
    task_id = payload.get("task_id")
    if not isinstance(task_id, int):
        return "", 204
    enqueue_check(task_id)
    return "", 204

def handle_task(task_id: int) -> None:
    body = requests.get(f"{BASE}/check", params={"id": task_id}, headers=HEADERS, timeout=30).json()
    if body.get("code") != 0:
        return
    if body["data"]["status"] == "READY":
        ...  # download (see examples/translate.py)
```
