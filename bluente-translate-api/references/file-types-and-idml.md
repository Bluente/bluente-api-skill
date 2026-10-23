# File types and InDesign (IDML)

## Supported file types

- Call `GET /supported_filetypes` for the current list (`extension` + `mimeType`). It covers PDF, Word, PowerPoint, Excel, plain text and more. Cache it.
- **`.idml` is accepted by `/upload` but is not in that list yet.** If you validate extensions on your side, allow `.idml` explicitly.
- The upload filename must carry the right extension. Bluente uses it to decide how to read the file; a file with no extension is rejected with `code: 40`.
- A supported extension doesn't guarantee the file is usable. Corrupt or password-protected files are accepted by `/upload` and then fail on `/check` with `status: "ERROR"`.
- By default the result comes back in the same format as the upload. To get a different format, see "Converting at download" in `options.md`.

## InDesign (IDML)

Bluente translates InDesign documents natively when they are sent as **IDML** (InDesign Markup Language). The result is an **editable `.idml` package** to open in InDesign — not a PDF.

### Preparing the file

- In InDesign: **File → Export… → InDesign Markup (IDML)**. Upload that `.idml` file.
- **Don't upload `.indd`.** If the user only has `.indd`, ask them to export IDML first.

### Flow

The same five steps as any other file:

1. `POST /upload?engine=3` with the `.idml` file.
2. Poll `GET /check` until `SERVICE_PROCESSED` (an invalid package ends in `ERROR`).
3. `POST /translate?engine=3` with `id`, `action: "start"`, `from`, `to` — and none of the options below.
4. Poll `GET /check` until `READY`.
5. `GET /download?id=...` — omit `to_type` (or send `to_type=idml`). The result is `.idml`.

### Options rejected for IDML

Sending any of these makes `/translate` (and `/validate_options`) return `code: 40`, and nothing is charged:

| Option | Rule for IDML |
|---|---|
| `to_type` (body) | Must be empty or `"idml"`. No PDF or INDD output. |
| `page_range` | Not supported; the whole document is always translated. |
| `scanned` / `scanned_option` | Must be `0` or absent. |
| `translate_image` | Not supported. |
| `table_layout_enhancement` / `is_use_table_layout_enhancement` | Not supported. |
| `only_extract` / `is_only_extract` | Not supported. |
| `bilingual`, `vertical_bilingual` / `is_use_bilingual`, `is_vertical_bilingual` | Not supported. |
| Custom font selection | Not supported; fonts come from the original document. |

Glossary options (`glossary`, `custom_glossary`, `namespace`, `namespaces`) and `meta_data` work as usual.

A `to_type` other than `idml` on `/download` is also refused (returned as a JSON error, not a file).

Example error:

```json
{ "code": 40, "message": "IDML translation supports the complete document, not page selections" }
```

### Billing

- IDML is billed for the **whole document**. There is no partial translation and no watermarked preview.
- If the account can't pay for the whole document, the translation doesn't start: `code: 70` for insufficient or expired credits, or `code: 40` when the account would only get a partial preview.

### Tell the user after download

- **Review in InDesign before export or print.** Translated text is often longer or shorter than the source: check every spread for overset (overflowing) text and adjust frames.
- **Fonts and linked images are not inside the IDML.** IDML references them by name and path. Install the document's fonts and relink assets on the machine that opens the result.
- If the original font can't display the target language, Bluente applies a fallback font to that text. Check fonts with **Type → Find/Replace Font…**.
