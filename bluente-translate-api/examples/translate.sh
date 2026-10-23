#!/usr/bin/env bash
# Translate one document with the Bluente API: upload -> wait -> validate ->
# start -> wait -> download.
#
# Usage:   BLUENTE_API_KEY=sk-... ./translate.sh <file> <from> <to> [out_dir]
# Example: ./translate.sh contract.docx en fr ./out
#
# Needs: bash, curl, jq.
# Optional env: BLUENTE_ENGINE (3 = LLM, default; 4 = LLM Pro),
#               BLUENTE_PROCESS_TIMEOUT (seconds, default 900),
#               BLUENTE_TRANSLATE_TIMEOUT (seconds, default 3600).
#
# Starting the translation spends credits on the account that owns the key.

set -euo pipefail

BASE="https://api.bluente.com/api/20250924/blu_translate"
ENGINE="${BLUENTE_ENGINE:-3}"
PROCESS_TIMEOUT="${BLUENTE_PROCESS_TIMEOUT:-900}"
TRANSLATE_TIMEOUT="${BLUENTE_TRANSLATE_TIMEOUT:-3600}"

die() { echo "error: $*" >&2; exit 1; }

[ "$#" -ge 3 ] || die "usage: $0 <file> <from> <to> [out_dir]"
FILE="$1"; FROM="$2"; TO="$3"; OUT_DIR="${4:-.}"
[ -f "$FILE" ] || die "no such file: $FILE"
[ -n "${BLUENTE_API_KEY:-}" ] || die "set BLUENTE_API_KEY"
command -v jq >/dev/null || die "jq is required"
mkdir -p "$OUT_DIR"

AUTH="Authorization: Bearer ${BLUENTE_API_KEY}"

# Fail unless the JSON body has code 0. Prints the body on success.
require_ok() {
  local body="$1" what="$2" code
  code="$(jq -r '.code // empty' <<<"$body" 2>/dev/null || true)"
  [ "$code" = "0" ] || die "$what failed: code=${code:-?} message=$(jq -r '.message // empty' <<<"$body" 2>/dev/null || echo "$body")"
  printf '%s' "$body"
}

check() {
  curl -sS --max-time 60 -H "$AUTH" "$BASE/check?id=$1"
}

# wait_for <task_id> <wanted_status> <timeout_seconds> <interval_seconds>
wait_for() {
  local id="$1" wanted="$2" timeout="$3" interval="$4"
  local deadline=$(( $(date +%s) + timeout )) failures=0 body code status
  while :; do
    if body="$(check "$id")"; then
      code="$(jq -r '.code // empty' <<<"$body" 2>/dev/null || true)"
      if [ "$code" = "0" ]; then
        failures=0
        status="$(jq -r '.data.status' <<<"$body")"
        case "$status" in
          "$wanted") return 0 ;;
          ERROR|CANCELLED|CREDITS_INSUFFICIENT)
            die "task $id stopped: $status - $(jq -r '.data.message // empty' <<<"$body")" ;;
        esac
        echo "  status: $status" >&2
      elif [ "$code" = "500" ] && ! jq -e '.message | test("record not found")' <<<"$body" >/dev/null 2>&1; then
        failures=$((failures + 1))   # possibly transient server error
      else
        die "check failed: code=${code:-?} message=$(jq -r '.message // empty' <<<"$body" 2>/dev/null)"
      fi
    else
      failures=$((failures + 1))     # network error
    fi
    [ "$failures" -lt 5 ] || die "too many consecutive /check failures"
    [ "$(date +%s)" -lt "$deadline" ] || die "timed out waiting for $wanted (task $id)"
    sleep "$interval"
  done
}

echo "Uploading $FILE ..." >&2
UPLOAD="$(require_ok "$(curl -sS --max-time 600 -X POST -H "$AUTH" \
  -F "file=@${FILE}" "$BASE/upload?engine=${ENGINE}")" "upload")"
ID="$(jq -r '.data.id' <<<"$UPLOAD")"
echo "Task id: $ID" >&2

echo "Waiting for processing ..." >&2
wait_for "$ID" SERVICE_PROCESSED "$PROCESS_TIMEOUT" 5

REQ="$(jq -n --argjson id "$ID" --arg from "$FROM" --arg to "$TO" \
  '{id: $id, action: "start", from: $from, to: $to}')"

# Dry run first: same checks as /translate, no charge.
require_ok "$(curl -sS --max-time 120 -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d "$REQ" "$BASE/validate_options?engine=${ENGINE}")" "validate_options" >/dev/null

echo "Starting translation $FROM -> $TO ..." >&2
require_ok "$(curl -sS --max-time 120 -X POST -H "$AUTH" -H "Content-Type: application/json" \
  -d "$REQ" "$BASE/translate?engine=${ENGINE}")" "translate" >/dev/null

echo "Waiting for translation ..." >&2
wait_for "$ID" READY "$TRANSLATE_TIMEOUT" 15

echo "Downloading ..." >&2
TMP_BODY="$(mktemp)"; TMP_HEAD="$(mktemp)"
trap 'rm -f "$TMP_BODY" "$TMP_HEAD"' EXIT
curl -sS --max-time 600 -H "$AUTH" -D "$TMP_HEAD" -o "$TMP_BODY" "$BASE/download?id=${ID}"

CTYPE="$(grep -i '^content-type:' "$TMP_HEAD" | tail -1 | cut -d: -f2- | tr -d ' \r' || true)"
case "$CTYPE" in
  application/json*) die "download failed: $(cat "$TMP_BODY")" ;;
esac

# Use the extension from Content-Disposition so the saved name matches the real format.
DISPO="$(grep -i '^content-disposition:' "$TMP_HEAD" | tail -1 | tr -d '\r' || true)"
EXT="$(sed -nE 's/.*filename="[^"]*\.([A-Za-z0-9]+)".*/\1/p' <<<"$DISPO")"
[ -n "$EXT" ] || EXT="${FILE##*.}"
STEM="$(basename "${FILE%.*}")"
OUT="${OUT_DIR%/}/${STEM}.${TO}.${EXT}"
mv "$TMP_BODY" "$OUT"
echo "$OUT"
