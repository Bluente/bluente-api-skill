# Custom glossary

A custom glossary makes Bluente translate specific terms the way you want (product names, legal terms, client terminology). Entries are saved under the uploading user (and their organization, if they belong to one) and can be grouped into **namespaces** (for example one per client or project).

## Using a glossary in a translation

On `POST /translate` (and `/validate_options`):

- Send **both** `glossary=1` and `custom_glossary=1` in the query string (or `is_use_glossary: true` and `is_use_custom_glossary: true` in the body). One without the other does nothing.
- Optional body field `namespace` (string) or `namespaces` (array of strings) limits the glossary to those namespaces. Without either, all entries for the task's language pair are used.
- Entries apply when their source and target languages match the task's `from` and `to`.
- The `custom_glossary` feature must be enabled for the account (check `GET /capabilities`); otherwise `/translate` returns `41`.

```bash
curl -X POST "$BASE/translate?engine=3&glossary=1&custom_glossary=1" \
  -H "Authorization: Bearer $BLUENTE_API_KEY" \
  -H "Content-Type: application/json" \
  -d '{"id": 12345, "action": "start", "from": "en", "to": "zh", "namespace": "Client A"}'
```

## POST /glossary/upload — add entries from a file

Multipart form:

| Field | Required | Notes |
|---|---|---|
| `file` | Yes | `.csv` (UTF-8) or `.xlsx` (first sheet is read). |
| `namespace` | No | Applied to every row. Blank = no namespace. At most 64 characters. |

The first row is the header. Column names are matched case-insensitively; extra columns are ignored.

| Column | Required | Content |
|---|---|---|
| `Original text` | Yes | Source term. |
| `Translation text` | Yes | Target term. |
| `Source language` | Yes | Language name or code, e.g. `English` or `en`. |
| `Target language` | Yes | Language name or code, e.g. `Chinese` or `zh`. |
| `Scene` | No | Context or domain to help disambiguate. |
| `Examples` | No | Usage examples. |

```csv
Original text,Translation text,Source language,Target language,Scene,Examples
Amount of Investment,投资金额,English,Chinese,Finance,
Share Purchase Agreement,股份购买协议,English,Chinese,Legal,
```

- Each text must be written in the script of its declared language (for example Chinese text for `Chinese`). Short all-caps Latin acronyms (up to 5 letters, e.g. `CEO`) are allowed in a non-Latin column.
- Empty rows are skipped. A file with no entries is rejected.
- The upload is all-or-nothing: if any row fails, nothing is saved.

```bash
curl -X POST "$BASE/glossary/upload" \
  -H "Authorization: Bearer $BLUENTE_API_KEY" \
  -F "file=@glossary.csv" \
  -F "namespace=Client A"
```

Success: `data` is the list of created entries (`id`, `source_lang`, `source_text`, `target_lang`, `target_text`, `namespace`, ...). Languages are stored as full names (e.g. `"English"`).

Validation failure: `code: 40` with row-level details:

```json
{
  "code": 40,
  "message": "Glossary upload failed. Row 3 contains language errors.",
  "data": {
    "failed_rows": [
      { "row": 3, "column": "Translation text", "value": "hello", "expected_language": "Chinese", "detected_language": "Latin", "reason": "Translation text does not match declared Chinese." }
    ]
  }
}
```

`row` counts the header as row 1.

## GET /glossary/list — list entries

| Query | Notes |
|---|---|
| `size` | Page size, default 20. |
| `next_token` | Offset. Omit (or `0`) for the first page, then pass the previous `data.next_token`. |

```json
{ "code": 0, "message": "success", "data": { "list": [ { "id": 3, "source_lang": "English", "source_text": "Amount of Investment", "target_lang": "Chinese", "target_text": "投资金额", "namespace": "Client A" } ], "next_token": "20" } }
```

**`next_token` is never empty.** Stop when `data.list` is empty or shorter than `size`.

## POST /glossary/update — edit entries

JSON body: an array of entries. **Send all four core fields for every entry** (`source_lang`, `source_text`, `target_lang`, `target_text`); fields you leave out are overwritten with empty values. `scene`, `examples` and `namespace` are optional and are only changed when present.

```json
[
  { "id": 242, "source_lang": "English", "source_text": "hello", "target_lang": "Chinese", "target_text": "你好", "namespace": "Client A" }
]
```

Response: `data.success` (updated entries) and `data.failed` (entries that could not be updated, e.g. an invalid namespace). If an update would duplicate another entry, the call returns `code: 80`.

## POST /glossary/delete — delete entries

JSON body: an array of entry IDs, e.g. `[242, 243]`. Deletion is permanent. Only entries you uploaded are deleted; IDs that don't match are ignored without an error.

## Errors

- Upload: `40` for a request that isn't valid multipart, a missing file, an invalid namespace, or row validation errors (details in `data.failed_rows`); `500` for other failures.
- List, update and delete report failures as `500` (or `80` for a duplicate on update), with the reason in `message`.
