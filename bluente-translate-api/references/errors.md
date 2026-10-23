# Errors, statuses and retries

## The response envelope

Every JSON response — success or failure — has HTTP status **200**:

```json
{ "code": 0, "message": "success", "data": { } }
```

- `code: 0` is the only success value. Treat any other value as an error.
- `message` is human-readable. Show it to the user or log it; don't parse it.
- `data` may be missing. Read it only when `code` is `0`, except where an endpoint puts error details in `data` (`/validate_options`, `/translate` feature-policy failures, glossary upload).
- `/download` returns file bytes on success and this envelope on error.

## Codes

| Code | Meaning | Typical causes | What to do |
|---|---|---|---|
| `0` | Success | — | — |
| `20` | Unauthorized | Missing header; value not starting with `Bearer sk-`; expired key; key replaced by a newer key for the same user | Fix the key. Don't retry unchanged. |
| `40` | Invalid parameters | Bad JSON or form; missing file; filename without extension; invalid language code; option not applicable to this file or conflicting with another; `/translate` before `SERVICE_PROCESSED`; IDML-incompatible option; invalid `to_type` on download | Fix the request. Don't retry unchanged. |
| `41` | No permission | Task uploaded by another user; feature not enabled for this account | Use the uploading user's key, or drop the feature (see `/capabilities`). |
| `43` | Not found | Unknown task ID on `/validate_options` | Check the ID. |
| `70` | Insufficient or expired credits | The account can't pay for the document | Check `/account`, top up, then call `/translate` again. |
| `80` | Already exists | `/translate` called again for a task already started; duplicate glossary entry on update | Don't resend. Poll `/check`. |
| `500` | Server error, or "not found" on some endpoints | Unknown task ID on `/check` and `/translate` (`"record not found"`); download not available; invalid `page_range` for some file types; `/text` and glossary list/update/delete failures; transient server errors | Read `message`. Retry later only if it looks transient. |

Codes not listed may appear in future; treat any non-zero code as an error.

## Task statuses (`data.status` from `/check`)

| Status | Phase | Action |
|---|---|---|
| `UPLOADING`, `SERVICE_PROCESSING` (and other intermediate values such as `CREATED`, `UPLOADED`) | After upload | Keep polling. |
| `SERVICE_PROCESSED` | Ready to translate | Call `/translate`. `pageCount` is now known. |
| `TRANSLATING` (and other intermediate values such as `TRANSLATED`, `DOWNLOADING`, `DOWNLOADED`, `SAVING`) | After start | Keep polling. |
| `READY` | Done | Call `/download`. |
| `ERROR` | Failed | Stop. Show `data.message`. |
| `CANCELLED` | Cancelled | Stop. |
| `CREDITS_INSUFFICIENT` | `/translate` was refused for credits | Stop polling. Top up and call `/translate` again. |

Write polling code as: success on `READY`; failure on `ERROR`, `CANCELLED`, `CREDITS_INSUFFICIENT`; otherwise wait and poll again, until an overall timeout. Don't enumerate "in-progress" states — new intermediate values should simply mean "keep waiting".

## Errors that arrive late

- **Upload problems are reported by `/check`.** `/upload` returns an ID as soon as the bytes arrive. A corrupt, password-protected or unsupported file shows up as `status: "ERROR"` before translation starts. No webhook is sent for these.
- **Translation problems are reported by `/check`** (`ERROR`) and, when configured, usually by the webhook.

## Retry guidance

- `20`, `40`, `41`, `43`: the request itself must change. Retrying it unchanged returns the same error.
- `70`: retry only after the account has credits.
- `80`: never retry; the task is already running.
- `500` on `/check` during polling: one transient `500` can be tolerated (retry with back-off), but `"record not found"` means the ID is wrong.
- Never auto-retry `/translate` in a loop: each successful start is charged. Code `80` protects against double charging for the same task, but a new upload is a new task.
