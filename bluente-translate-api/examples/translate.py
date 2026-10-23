#!/usr/bin/env python3
"""Translate one document with the Bluente API.

Flow: upload -> wait for SERVICE_PROCESSED -> validate_options (free dry run)
-> translate (charges credits) -> wait for READY -> download.

Usage:
    BLUENTE_API_KEY=sk-... python3 translate.py contract.docx en fr [out_dir]

Needs: Python 3.8+, `pip install requests`.
Optional env: BLUENTE_ENGINE (3 = LLM, default; 4 = LLM Pro).
"""

from __future__ import annotations

import os
import re
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote, unquote_plus

import requests

BASE = "https://api.bluente.com/api/20250924/blu_translate"
FAILED_STATES = {"ERROR", "CANCELLED", "CREDITS_INSUFFICIENT"}


class BluenteError(Exception):
    def __init__(self, code: Optional[int], message: str, data: Any = None):
        super().__init__(f"Bluente API error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


class BluenteClient:
    def __init__(self, api_key: Optional[str] = None, engine: int = 3):
        api_key = api_key or os.environ.get("BLUENTE_API_KEY")
        if not api_key:
            raise SystemExit("Set BLUENTE_API_KEY")
        self.engine = engine
        self.session = requests.Session()
        self.session.headers["Authorization"] = f"Bearer {api_key}"

    # Every JSON response is HTTP 200; success is only code == 0.
    @staticmethod
    def _unwrap(resp: requests.Response) -> Any:
        try:
            body = resp.json()
        except ValueError:
            raise BluenteError(None, f"non-JSON response (HTTP {resp.status_code})")
        if body.get("code") != 0:
            raise BluenteError(body.get("code"), body.get("message", ""), body.get("data"))
        return body.get("data")

    def upload(self, path: Path) -> int:
        with path.open("rb") as fh:
            # The filename (with extension) tells Bluente the file type.
            resp = self.session.post(
                f"{BASE}/upload",
                params={"engine": self.engine},
                files={"file": (path.name, fh)},
                timeout=600,
            )
        return int(self._unwrap(resp)["id"])

    def check(self, task_id: int) -> Dict[str, Any]:
        resp = self.session.get(f"{BASE}/check", params={"id": task_id}, timeout=60)
        return self._unwrap(resp)

    def wait_for(self, task_id: int, wanted: str, timeout: float, interval: float) -> Dict[str, Any]:
        deadline = time.monotonic() + timeout
        transient_failures = 0
        while True:
            try:
                data = self.check(task_id)
                transient_failures = 0
                status = data.get("status")
                if status == wanted:
                    return data
                if status in FAILED_STATES:
                    raise BluenteError(None, f"task {task_id} stopped: {status} - {data.get('message', '')}", data)
                print(f"  status: {status}", file=sys.stderr)
            except requests.RequestException:
                transient_failures += 1
            except BluenteError as err:
                # Unknown IDs come back as 500 "record not found"; that is not transient.
                if err.code == 500 and "record not found" not in err.message:
                    transient_failures += 1
                else:
                    raise
            if transient_failures >= 5:
                raise BluenteError(None, "too many consecutive /check failures")
            if time.monotonic() >= deadline:
                raise BluenteError(None, f"timed out waiting for {wanted} (task {task_id})")
            time.sleep(interval)

    def _translate_request(self, task_id: int, source: str, target: str, **extra: Any) -> Dict[str, Any]:
        return {"id": task_id, "action": "start", "from": source, "to": target, **extra}

    def validate(self, task_id: int, source: str, target: str, **extra: Any) -> None:
        resp = self.session.post(
            f"{BASE}/validate_options",
            params={"engine": self.engine},
            json=self._translate_request(task_id, source, target, **extra),
            timeout=120,
        )
        self._unwrap(resp)

    def start(self, task_id: int, source: str, target: str, **extra: Any) -> None:
        """Starts the translation. This charges credits."""
        resp = self.session.post(
            f"{BASE}/translate",
            params={"engine": self.engine},
            json=self._translate_request(task_id, source, target, **extra),
            timeout=120,
        )
        self._unwrap(resp)

    def download(self, task_id: int, out_dir: Path, fallback_name: str) -> Path:
        with self.session.get(f"{BASE}/download", params={"id": task_id}, stream=True, timeout=600) as resp:
            ctype = resp.headers.get("Content-Type", "")
            if ctype.startswith("application/json"):
                self._unwrap(resp)  # raises with the server's code and message
                raise BluenteError(None, "expected a file but got JSON")
            name = filename_from_disposition(resp.headers.get("Content-Disposition", "")) or fallback_name
            out = out_dir / Path(name).name  # never trust a path from a header
            with out.open("wb") as fh:
                for chunk in resp.iter_content(chunk_size=1 << 16):
                    fh.write(chunk)
        return out


def filename_from_disposition(value: str) -> Optional[str]:
    star = re.search(r"filename\*=UTF-8''([^;]+)", value, re.IGNORECASE)
    if star:
        return unquote(star.group(1).strip())
    plain = re.search(r'filename="([^"]*)"', value, re.IGNORECASE)
    if plain:
        return unquote_plus(plain.group(1))
    return None


def main() -> int:
    if len(sys.argv) < 4:
        print(__doc__, file=sys.stderr)
        return 2
    path, source, target = Path(sys.argv[1]), sys.argv[2], sys.argv[3]
    out_dir = Path(sys.argv[4]) if len(sys.argv) > 4 else Path(".")
    out_dir.mkdir(parents=True, exist_ok=True)

    client = BluenteClient(engine=int(os.environ.get("BLUENTE_ENGINE", "3")))
    try:
        task_id = client.upload(path)
        print(f"Task id: {task_id}", file=sys.stderr)
        client.wait_for(task_id, "SERVICE_PROCESSED", timeout=900, interval=5)
        client.validate(task_id, source, target)
        client.start(task_id, source, target, meta_data={"source_file": path.name})
        client.wait_for(task_id, "READY", timeout=3600, interval=15)
        out = client.download(task_id, out_dir, fallback_name=f"{path.stem}.{target}{path.suffix}")
    except BluenteError as err:
        print(f"error: {err}", file=sys.stderr)
        if err.data:
            print(f"details: {err.data}", file=sys.stderr)
        return 1
    print(out)
    return 0


if __name__ == "__main__":
    sys.exit(main())
