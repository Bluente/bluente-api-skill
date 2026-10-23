# Endpoint reference

All paths are relative to `https://api.bluente.com/api/20250924/blu_translate`. Every request needs `Authorization: Bearer sk-...`. Every JSON response has the shape `{ "code": int, "message": string, "data": any }` with HTTP status 200; `code: 0` is success (see `errors.md`).

## Contents

- Document translation: `POST /upload`, `GET /check`, `POST /translate`, `POST /validate_options`, `GET /download`
- Account and discovery: `GET /account`, `GET /credit`, `GET /capabilities`, `GET /supported_languages`, `GET /supported_filetypes`, `GET /history`
- Text: `POST /text`
- Glossary: see `glossary.md`

---

## POST /upload

Upload one document. Returns a task ID **before** the file is processed.

| Where | Field | Required | Notes |
|---|---|---|---|
| Query | `engine` | Yes | `3` = LLM, `4` = LLM Pro. Use the same value on `/translate`. |
| Form data | `file` | Yes | The document. The filename must include its extension. |

```bash
curl -X POST "$BASE/upload?engine=3" \
  -H "Authorization: Bearer $BLUENTE_API_KEY" \
  -F "file=@/path/to/contract.docx"
```

```json
{ "code": 0, "message": "success", "data": { "id": 12345, "language": "", "sub_task_ids": null } }
```

- `data.id` — the task ID used by every later call.
- `data.language` — reserved; currently always empty (no language detection at upload).
- `data.sub_task_ids` — `null` for a single-file upload.
- Errors: `40` with `"missing file from body"` (no `file` field), `"uploaded file is missing a filename or extension"`, or `"invalid request body"` (not multipart).

## GET /check

Get the status of a task. Poll it after upload and after starting the translation.

| Where | Field | Required | Notes |
|---|---|---|---|
| Query | `id` | Yes | Task ID from `/upload`. |

Older docs show an `entry` query parameter (`get_status` / `get_page_count`). The server ignores it; the response always has both the status and the page count.

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "id": 12345,
    "status": "SERVICE_PROCESSED",
    "message": "document is done being processed on the translation server",
    "pageCount": 8,
    "serviceCode": 0,
    "filename": "contract.docx",
    "source_lang": "",
    "target_lang": "",
    "updatedAt": "..."
  }
}
```

- `status` — see the status table in `errors.md`.
- `message` — human-readable detail; on `ERROR` it describes the problem.
- `pageCount` — known once the status reaches `SERVICE_PROCESSED`.
- More fields may be present. Ignore fields you don't use, and don't depend on a fixed timestamp format for `updatedAt`.
- Errors: `40` `"invalid id"` (missing or non-numeric), `41` (task belongs to another user), `500` `"record not found"` (unknown ID).

## POST /translate

Start (or cancel) the translation of an uploaded task. **Starting charges credits.**

Query string:

| Field | Notes |
|---|---|
| `engine` | Required. `3` or `4`; same as the upload. |
| `glossary`, `custom_glossary` | Send both as `1` to apply your custom glossary. See `glossary.md`. |
| `bilingual` | `1` = bilingual output (source and translation together). |
| `vertical_bilingual` | With `bilingual=1`: `1` = top-down, `0` = side by side. |
| `scanned` | Scanned-document mode: `1` = text only, `2` = with format (overlay). See `options.md`. |
| `only_extract` | With `scanned=1`: `1` = OCR only, no translation. |
| `translate_image` | `1` = also translate text inside images embedded in the file, where enabled. |
| `table_layout_enhancement` | `1` = table layout enhancement, where enabled. See `options.md`. |

JSON body:

| Field | Type | Required | Notes |
|---|---|---|---|
| `id` | int | Yes | Task ID. |
| `action` | string | Yes | `"start"` or `"cancel"`. Anything other than exactly `"cancel"` is treated as start. |
| `from` | string | Yes | Source language `svcCode`. |
| `to` | string | Yes | Target language `svcCode`. |
| `namespace` | string | No | Glossary namespace to use. |
| `namespaces` | string[] | No | Several glossary namespaces. Takes precedence over `namespace`. |
| `meta_data` | object | No | Any JSON object; returned unchanged in the webhook. |
| `page_range` | string | No | Translate (and pay for) only some pages, e.g. `"1-5, 8, 11-13"`. Not supported for IDML. |

The boolean options can also be sent in the JSON body instead of the query string: `is_use_glossary`, `is_use_custom_glossary`, `is_use_bilingual`, `is_vertical_bilingual`, `scanned_option`, `is_only_extract`, `translate_image`, `is_use_table_layout_enhancement`. A query parameter, when present, overrides the body value.

```bash
curl -X POST "$BASE/translate?engine=3" \
  -H "Authorization: Bearer $BLUENTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"id": 12345, "action": "start", "from": "en", "to": "fr", "meta_data": {"job_id": "abc-123"}}'
```

```json
{ "code": 0, "message": "success" }
```

- Errors: `40` (invalid language, option not applicable, conflicting options, task not yet processed, IDML-incompatible option), `41` (not the owner, or a feature not enabled for the account), `70` (credits), `80` (already started), `500` (unknown ID, invalid `page_range` for some file types, or a server error).
- Feature-policy failures (`41`/`40`) may carry details in `data` — see `/validate_options`.
- To cancel: same call with `"action": "cancel"`. Don't assume a cancel returns credits.

## POST /validate_options

Dry-run of `/translate`: same query string and body, same option checks, but **no translation starts and no credits are charged**.

```json
{ "code": 0, "message": "success", "data": { "valid": true } }
```

On a feature-policy failure:

```json
{
  "code": 41,
  "message": "…",
  "data": {
    "error_code": "FEATURE_NOT_ENABLED",
    "feature_keys": ["translate_bilingual"],
    "reason": "…",
    "task_id": 12345
  }
}
```

- `error_code`: `FEATURE_NOT_ENABLED` (code `41`), `FEATURE_NOT_APPLICABLE` or `FEATURE_CONFLICT` (code `40`).
- Other problems (for example an IDML-incompatible option) return `40` with the reason in `message` and no `data`.
- Unknown task ID: `43`.
- It does **not** check the credit balance and does **not** validate `from` / `to`. Use `/account` for the balance and `/supported_languages` for codes.

## GET /download

Download the result once `/check` says `READY`.

| Where | Field | Required | Notes |
|---|---|---|---|
| Query | `id` | Yes | Task ID. |
| Query | `to_type` | No | Leave out to get the normal result. See "Converting at download" in `options.md`. |

- **Success:** the file bytes, with `Content-Type` set for the file type and a `Content-Disposition: attachment; filename="..."` header. The `filename=` value is URL-encoded (spaces may appear as `+`); a `filename*=UTF-8''...` form may also be present — prefer it when it is. Translated filenames look like, for example, `BluTranslate_LLM_fr_contract.docx`.
- **Error:** a JSON body (`Content-Type: application/json`) with HTTP 200, e.g. `{"code": 500, "message": "unable to get downloaded data"}`. This is also what you get for a task that isn't ready, an unknown ID, or another user's task. Check before writing to disk.
- `to_type` that can't apply to the task returns `40` `"invalid target file format"`.

## GET /account

The user and organization that own the key, and spendable credits per feature.

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "user": { "email": "translator@example.com", "full_name": "Alex Chen" },
    "organization": { "name": "Example Corp", "role": "staff" },
    "credits": [
      {
        "feature": "translate",
        "paid_by": "organization",
        "balance": 1200,
        "expiries": [ { "at": "2026-11-30T23:59:59Z", "credits": 200 } ]
      }
    ]
  }
}
```

- `organization` is `null` when the user is not in an organization.
- `credits[]` always includes `translate` (pages); `transcribe` and `rewrite` appear only when above 0.
- `balance` counts only unexpired credits. `expiries` is soonest first.

## GET /credit

Older credit endpoint with the credit record and its transaction history (`data.pages`, `data.expire_at`, `data.transactions[]`). Prefer `/account` for balances.

## GET /capabilities

The translation features available to this account and how they combine.

```json
{
  "code": 0,
  "message": "success",
  "data": {
    "policy_version": "…",
    "features": [
      {
        "feature_key": "translate_bilingual",
        "display_name": "Bilingual",
        "enabled": true,
        "applicable_document_modes": ["STANDARD"],
        "applicable_file_types": ["pdf", "docx"],
        "conflicts_with": [],
        "grantable": true,
        "active": true,
        "sort_order": 10
      }
    ]
  }
}
```

Feature keys include `standard`, `scanned_text_only`, `scanned_overlay`, `image_translation`, `custom_glossary`, `table_layout_enhancement`, `translate_bilingual`, `translate_images_within_file`, `custom_font`. Use it to show or hide options in your UI.

## GET /supported_languages

```json
{ "code": 0, "message": "success", "data": [ { "language": "Arabic", "svcCode": "ar", "source": 1, "target": 1, "supported": 1, "name": "Arabic" } ] }
```

Use `svcCode` as `from` / `to`. `source` / `target` = `1` when the language can be used on that side. Cache the result.

## GET /supported_filetypes

```json
{ "code": 0, "message": "success", "data": [ { "extension": "pdf", "mimeType": "application/pdf" } ] }
```

`.idml` is accepted by `/upload` even though this list doesn't include it yet.

## GET /history

Translation tasks of the caller's organization, newest first, 10 per page.

| Query | Notes |
|---|---|
| `next_token` | Omit for the first page; then pass the previous `data.next_token`. |

`data.translations[]` has `id`, `file_extension`, `page_count`, `deducted`, `source_lang`, `target_lang`, `state_str`, `created_at`, `created_by`, `updated_at`. `data.next_token` is empty when there are no more pages.

## POST /text

Translate a short text or HTML snippet synchronously.

```bash
curl -X POST "$BASE/text" \
  -H "Authorization: Bearer $BLUENTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"from": "en", "to": "zh", "text": "<p>Hello</p>"}'
```

```json
{ "code": 0, "message": "success", "data": { "text": "<html><head></head><body><p>你好</p></body></html>" } }
```

- HTML input comes back wrapped in `<html><head></head><body>…</body></html>`.
- Errors from this endpoint use `code: 500`; for invalid input `data` is `40` and `message` explains (e.g. `"source language is not valid"`).
