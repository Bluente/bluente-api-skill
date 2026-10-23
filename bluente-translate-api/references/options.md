# Translation options

Options are sent to `POST /translate` (and identically to `POST /validate_options`). Each one can go in the query string or in the JSON body; a query parameter that is present overrides the body.

| Query | JSON body | Values | Notes |
|---|---|---|---|
| `engine` | — | `3`, `4` | Required. `3` = LLM, `4` = LLM Pro. Match the upload. |
| `glossary` + `custom_glossary` | `is_use_glossary` + `is_use_custom_glossary` | `1` / `true` | Both must be on to apply your custom glossary. See `glossary.md`. |
| `bilingual` | `is_use_bilingual` | `1` / `true` | Output shows source and translation together. |
| `vertical_bilingual` | `is_vertical_bilingual` | `1` = top-down, `0` = side by side | Only with bilingual. |
| `scanned` | `scanned_option` | `0` none, `1` text only, `2` with format (overlay) | For scanned documents / images. See below. |
| `only_extract` | `is_only_extract` | `1` / `true` | With `scanned=1`: run OCR only, no translation. |
| `translate_image` | `translate_image` | `1` / `true` | Also translate text inside images embedded in the document. |
| `table_layout_enhancement` | `is_use_table_layout_enhancement` | `1` / `true` | PDF only. See below. |
| — | `page_range` | e.g. `"1-5, 8"` | Translate and charge only these pages. Not for IDML. |
| — | `namespace` / `namespaces` | string / string[] | Glossary namespaces. |
| — | `meta_data` | JSON object | Echoed back in the webhook. |

## Check before you charge

1. **`GET /capabilities`** lists the features this account can use (`enabled`), which document modes and file types each applies to, and which features conflict. Use it to decide which options to offer.
2. **`POST /validate_options`** runs the exact `/translate` checks against a real, processed task without starting it or charging credits. It returns `data.valid: true`, or an error with `data.error_code` (`FEATURE_NOT_ENABLED` → code `41`; `FEATURE_NOT_APPLICABLE` / `FEATURE_CONFLICT` → code `40`) and `data.feature_keys`.
3. **`GET /account`** shows the credit balance; `/validate_options` does not check it.

A feature that isn't enabled makes `/translate` return `41`. An option that doesn't apply to the file type, or two options that conflict, return `40`.

## Scanned documents and OCR

- `scanned=1` (text only): recognises the text and produces a text-based translation.
- `scanned=2` (with format / overlay): keeps the page look and places the translation over it.
- `scanned=1&only_extract=1`: OCR without translation; download the extracted result with `/download`.
- Each mode is a separate feature (`scanned_text_only`, `scanned_overlay`) and must be enabled for the account; check `/capabilities`.

## Table layout enhancement (TLE)

- Improves the layout of translated tables in **PDF** documents.
- **Off unless enabled for the account** (`table_layout_enhancement` in `/capabilities`). Requesting it without access returns `41`.
- **Charged at 3× the normal page credits.**
- Applies only to normal (non-scanned) PDF translation. Don't combine it with bilingual output or in-image translation; those are dropped when TLE applies.
- Not available for IDML.

## Bilingual output

- `bilingual=1` produces a document with source and translation together; `vertical_bilingual` picks top-down (`1`) or side-by-side (`0`).
- Requires the `translate_bilingual` feature. Not available for IDML.

## Converting at download (`to_type`)

`GET /download?id=...&to_type=...` can convert the finished result:

| Task result | `to_type` | You get |
|---|---|---|
| PDF | `word` (or `docx`) | Word document |
| PDF | `pptx` | PowerPoint |
| Word, PowerPoint or another non-PDF result | `pdf` | PDF |
| IDML | — | IDML only; any other value is refused |

- Leave `to_type` out to get the normal result.
- A combination that can't be converted returns `code: 40` `"invalid target file format"`.
- **If the conversion itself fails, the server returns the unconverted file instead of an error.** Always check the extension of the filename in `Content-Disposition` before trusting the format.
- Conversion happens after translation, so the layout of a converted file can differ from the native result. Prefer the native format unless the user needs another one.

The `/translate` body also has a `to_type` field. Its behaviour is not part of the public contract, so don't set it (for IDML it must be empty or `"idml"`).

## Cancelling

`POST /translate` with `"action": "cancel"` and the same `id` (plus `from` / `to`) cancels the task. The status becomes `CANCELLED`. Don't assume credits are returned.
