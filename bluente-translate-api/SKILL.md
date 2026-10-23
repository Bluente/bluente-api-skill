---
name: bluente-translate-api
description: How to integrate with Bluente's public document-translation API (api.bluente.com, BluTranslate) — upload a file, wait for processing, start translation, poll or receive a webhook, and download the translated file. Use this skill whenever the user wants to translate documents (PDF, Word, PowerPoint, Excel, InDesign/IDML and more) with Bluente, write or debug code that calls api.bluente.com or the /blu_translate endpoints, handle Bluente API keys, error codes, credits, webhooks, glossaries or IDML/InDesign translation, or build a Bluente client in any language — even if they only say "the Bluente API" or paste a Bluente endpoint without naming the skill.
---

# Bluente document-translation API

Bluente translates whole documents and keeps their layout. A translation is one **task**: upload a file, wait while Bluente processes it, start the translation, wait again, then download the result.

## Basics

- **Base URL:** `https://api.bluente.com/api/20250924/blu_translate`
- **Auth:** header `Authorization: Bearer sk-...` on every request. Keys are created at https://translate.bluente.com/apikeys.
- **Read the key from the environment** (`BLUENTE_API_KEY`). Never hard-code it or put it in browser code.
- **Every response is HTTP 200.** Success is only `"code": 0` in the JSON body `{code, message, data}`. Always check `code` before using `data`.

## The flow

| Step | Call | Continue when |
|---|---|---|
| 1. Upload | `POST /upload?engine=3` (multipart field `file`) | `code == 0`; keep `data.id` |
| 2. Wait for processing | `GET /check?id=ID` | `data.status == "SERVICE_PROCESSED"` |
| 3. Start translation | `POST /translate?engine=3` JSON `{"id": ID, "action": "start", "from": "en", "to": "fr"}` | `code == 0` |
| 4. Wait for translation | `GET /check?id=ID` | `data.status == "READY"` |
| 5. Download | `GET /download?id=ID` | response is a file, not JSON |

- `engine`: `3` = LLM, `4` = LLM Pro. Send the same value on `/upload` and `/translate`.
- Language codes are the `svcCode` values from `GET /supported_languages`. They are case-sensitive (`en`, `zh`, `en-GB`, ...).
- Optional `meta_data` (any JSON object) on `/translate` comes back unchanged in the webhook. Use it to carry your own job ID.

## Gotchas — read these before writing code

1. **Upload is asynchronous.** The `id` comes back before the file is opened. A corrupt, password-protected or unsupported file shows up later as `status: "ERROR"` on `/check`, not as an upload error.
2. **Don't call `/translate` before `SERVICE_PROCESSED`.** The page count is not known yet, so it fails with `code: 40`.
3. **`/translate` charges credits immediately.** Code `70` = not enough (or expired) credits. Code `80` = this task was already started — don't resend, just poll. To check options without charging, send the identical request to `POST /validate_options` first.
4. **Any `action` other than exactly `"cancel"` starts the translation.** Always send `"action": "start"` explicitly, and never send a request you didn't mean to be charged for.
5. **Polling: stop on failure states too.** `READY` = done. `ERROR`, `CANCELLED` and `CREDITS_INSUFFICIENT` = stopped; read `data.message`. Every other status (`UPLOADING`, `SERVICE_PROCESSING`, `TRANSLATING`, and other intermediate values) means keep waiting. Poll every 5–30 seconds and always use an overall timeout. Most documents finish in 2–5 minutes; 100+ pages can take 15–20 minutes.
6. **Download errors come back as JSON with HTTP 200.** Check `Content-Type` (`application/json` = error) or look for a `code` field before saving bytes to disk. Without `to_type` the result has the uploaded format; if you pass `to_type` to convert (see `references/options.md`), check the extension in `Content-Disposition` — a failed conversion silently returns the unconverted file.
7. **Unknown task IDs return `code: 500` (`"record not found"`)** on `/check` and `/translate`, not 404. `/validate_options` returns `43`.
8. **One active key per user.** Creating a new API key expires that user's previous keys (they start getting `code: 20`). Give each environment or integration its own Bluente user.
9. **Tasks belong to the user whose key uploaded them.** Another user's key gets `code: 41` (or a `500` on download).
10. **Webhooks are unsigned and best-effort.** Treat a webhook as a hint: confirm with `/check` using your own key, then download. Keep a polling fallback.

## IDML / InDesign

Upload `.idml` (exported from InDesign via File → Export → InDesign Markup), not `.indd`. Output is always `.idml`. Bilingual, page ranges, scanned/OCR modes, image translation, table layout enhancement, extract-only, custom fonts and non-IDML `to_type` are rejected with `code: 40`. IDML is billed for the whole document. Details: `references/file-types-and-idml.md`.

## Where to look next

| Need | Read |
|---|---|
| Every endpoint, parameter and response shape | `references/endpoints.md` |
| Error codes, retry rules, the status list | `references/errors.md` |
| Translation options (bilingual, scanned/OCR, glossary flags, table layout enhancement, `/capabilities`, `/validate_options`, download `to_type`) | `references/options.md` |
| File types, IDML rules and billing | `references/file-types-and-idml.md` |
| Webhook payload and handling | `references/webhooks.md` |
| Custom glossary upload, list, update, delete | `references/glossary.md` |
| Working end-to-end clients | `examples/translate.sh`, `examples/translate.py`, `examples/translate.ts` |

When writing a client, start from the matching example rather than from scratch: they already check `code`, poll with a timeout, and detect JSON-instead-of-file on download.

## Writing correct client code

- In JavaScript/TypeScript, build the header from the environment: `` `Bearer ${process.env.BLUENTE_API_KEY}` ``. A plain string such as `"Bearer $BLUENTE_API_KEY"` sends the literal text `$BLUENTE_API_KEY` and fails with `code: 20`.
- Send `/upload` as `multipart/form-data`, and let the HTTP library set the boundary (don't set `Content-Type` by hand). The filename must have an extension (`contract.docx`); without one the upload returns `code: 40`.
- Send `/translate` and `/validate_options` with `Content-Type: application/json`.
- Take the output filename from the `Content-Disposition` header: prefer `filename*=UTF-8''...` when present, otherwise URL-decode `filename=` (spaces may be `+`). Fall back to your own name if neither is usable.
- Don't invent limits. The API documents no rate limits, file-size limits or SLAs; don't promise any to the user.
- Never run a real translation as a "test" without the user's say-so: it spends their credits.
