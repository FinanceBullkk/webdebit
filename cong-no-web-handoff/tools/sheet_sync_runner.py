"""Read-only Sheet snapshot runner for a service account."""

from __future__ import annotations

import argparse
import base64
import datetime as dt
import json
import os
import pathlib
import subprocess
import tempfile
import time
import urllib.parse
import urllib.request
from collections.abc import Callable
from typing import Any

from webdebit_export_connector import read_export

TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPE = "https://www.googleapis.com/auth/spreadsheets.readonly"


def _b64(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).rstrip(b"=").decode("ascii")


def load_credentials(path: str | os.PathLike[str]) -> dict[str, str]:
    with open(path, encoding="utf-8") as stream:
        credentials = json.load(stream)
    if credentials.get("type") != "service_account":
        raise ValueError("credential is not a service account")
    for field in ("client_email", "private_key"):
        if not isinstance(credentials.get(field), str) or not credentials[field]:
            raise ValueError(f"credential missing {field}")
    return credentials


def make_assertion(credentials: dict[str, str], now: int | None = None,
                   signer: Callable[[bytes, bytes], bytes] | None = None, scope: str = SCOPE) -> str:
    issued = int(time.time()) if now is None else now
    header = _b64(json.dumps({"alg": "RS256", "typ": "JWT"}, separators=(",", ":")).encode())
    claims = _b64(json.dumps({
        "iss": credentials["client_email"],
        "scope": scope,
        "aud": TOKEN_URL,
        "iat": issued,
        "exp": issued + 3600,
    }, separators=(",", ":")).encode())
    signing_input = f"{header}.{claims}".encode("ascii")
    if signer is None:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", delete=False) as key:
            key.write(credentials["private_key"])
            key_path = key.name
        try:
            completed = subprocess.run(
                ["openssl", "dgst", "-sha256", "-sign", key_path],
                input=signing_input, capture_output=True, check=True,
            )
            signature = completed.stdout
        finally:
            os.unlink(key_path)
    else:
        signature = signer(signing_input, credentials["private_key"].encode())
    return f"{header}.{claims}.{_b64(signature)}"


def exchange_token(credentials: dict[str, str], opener: Callable[..., Any] = urllib.request.urlopen,
                   scope: str = SCOPE) -> str:
    assertion = make_assertion(credentials, scope=scope)
    body = urllib.parse.urlencode({
        "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
        "assertion": assertion,
    }).encode()
    request = urllib.request.Request(TOKEN_URL, data=body, method="POST",
                                     headers={"Content-Type": "application/x-www-form-urlencoded"})
    with opener(request, timeout=20) as response:
        payload = json.loads(response.read().decode("utf-8"))
    token = payload.get("access_token")
    if not isinstance(token, str) or not token:
        raise ValueError("token response missing access_token")
    return token


def run_once(credentials_path: str, spreadsheet_id: str, output_path: str,
             token_exchange: Callable[[dict[str, str]], str] = exchange_token) -> dict[str, Any]:
    credentials = load_credentials(credentials_path)
    token = token_exchange(credentials)
    snapshot = read_export(spreadsheet_id, token, include_booking=True, include_mapping=True)
    snapshot["runner"] = {"created_at": dt.datetime.now(dt.UTC).isoformat(), "mode": "read-only"}
    destination = pathlib.Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=destination.parent,
                                     prefix=".sheet-snapshot-", delete=False) as stream:
        temporary = pathlib.Path(stream.name)
        json.dump(snapshot, stream, ensure_ascii=False, indent=2)
        stream.write("\n")
    try:
        os.chmod(temporary, 0o600)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return snapshot


def main() -> int:
    parser = argparse.ArgumentParser(description="Read Sheet into a local review snapshot")
    parser.add_argument("--credentials", default=os.getenv("WEBDEBIT_GOOGLE_CREDENTIALS"))
    parser.add_argument("--spreadsheet-id", default=os.getenv("WEBDEBIT_SHEET_ID"))
    parser.add_argument("--output", default=os.getenv("WEBDEBIT_SNAPSHOT_PATH", "sheet-snapshot.json"))
    args = parser.parse_args()
    if not args.credentials or not args.spreadsheet_id:
        parser.error("set --credentials/WEBDEBIT_GOOGLE_CREDENTIALS and --spreadsheet-id/WEBDEBIT_SHEET_ID")
    snapshot = run_once(args.credentials, args.spreadsheet_id, args.output)
    print(json.dumps({"output": args.output, "row_count": snapshot["row_count"], "sha256": snapshot["sha256"]}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
