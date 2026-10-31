"""Tầng DB của API V7: chạy hàm `sokhach.*` qua psql trong container thử (`Psql`) hoặc qua socket (`PsqlDirect`).

Nơi duy nhất dựng lệnh psql cho đường sổ khách V7 (ARCH-01 trong `scripts/business-rules.js`).
Tách nguyên từ `v7_ledger_api.py` 31/10/2026: lệnh, tham số, timeout và ánh xạ lỗi giữ nguyên.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path

from v7_api_tables import BASE64, ERRORS, IMAGE_MARK, SQL
from v7_api_validate import ApiError, no_duplicates, vnd


class _PsqlRunner:
    def _run_psql(
        self, argv: list[str], function: str, payload: dict, actor: str
    ) -> dict:
        statement = SQL[function]
        if function == "attach_receipt_image":
            payload = dict(payload)
            image = payload.pop("data_base64", None)
            if not isinstance(image, str) or len(image) % 4 or not BASE64.fullmatch(image):
                raise ApiError(422, "IMAGE_INVALID", ERRORS["IMAGE_INVALID"][1])
            statement = statement.replace(IMAGE_MARK, image)
        sql = (
            "BEGIN;\nSET LOCAL sokhach.actor = :'actor';\n"
            + statement
            + "\nCOMMIT;\n"
        )
        env = os.environ.copy()
        env["PGOPTIONS"] = "-c statement_timeout=15000 -c lock_timeout=12000"
        try:
            result = subprocess.run(
                argv
                + [
                    "-v",
                    "payload="
                    + json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    "-v",
                    "actor=" + actor,
                ],
                input=sql,
                text=True,
                encoding="utf-8",
                errors="replace",
                capture_output=True,
                timeout=25,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            raise ApiError(
                503,
                "DB_UNAVAILABLE"
                if function in ("get_ledger", "list_offset_sources", "get_price_table", "get_price_status")
                else "RESULT_UNKNOWN",
                "Sổ tạm thời không truy cập được."
                if function in ("get_ledger", "list_offset_sources", "get_price_table", "get_price_status")
                else "Chưa rõ lệnh đã lưu. Thử lại với cùng mã yêu cầu.",
            ) from exc
        except OSError as exc:
            raise ApiError(
                503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được."
            ) from exc
        if result.returncode:
            match = re.search(
                r"(?m)^psql:.*: ERROR:  P0001: ([A-Z_]+)\s*$", result.stderr
            )
            if match and match.group(1) in ERRORS:
                status, message = ERRORS[match.group(1)]
                extra = {}
                if match.group(1) == "OFFSET_EXCEEDS_CREDIT":
                    detail = re.search(r"(?m)^DETAIL:\s+(.*)$", result.stderr)
                    if detail:
                        try:
                            data = json.loads(
                                detail.group(1), object_pairs_hook=no_duplicates
                            )
                            if isinstance(data, dict) and vnd(
                                data.get("available_credit_vnd")
                            ):
                                extra["available_credit_vnd"] = data[
                                    "available_credit_vnd"
                                ]
                        except (ValueError, ApiError):
                            pass
                raise ApiError(status, match.group(1), message, extra)
            raise ApiError(503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được.")
        try:
            return json.loads(result.stdout.strip())
        except ValueError as exc:
            raise ApiError(
                503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được."
            ) from exc


class Psql(_PsqlRunner):
    def __init__(self, container: str, database: str, user: str):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", container):
            raise ValueError("invalid container name")
        if not all(
            re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", name) for name in (database, user)
        ):
            raise ValueError("invalid database or user")
        try:
            inspected = subprocess.run(
                ["docker", "inspect", "--type=container", container],
                text=True,
                encoding="utf-8",
                capture_output=True,
                timeout=8,
                check=True,
            )
            info = json.loads(inspected.stdout)[0]
        except (OSError, ValueError, IndexError, subprocess.SubprocessError) as exc:
            raise ValueError("test container unavailable") from exc
        labels = info.get("Config", {}).get("Labels") or {}
        if (
            labels.get("codex.test") != "webdebit-v7-backend"
            or not labels.get("codex.run")
            or info.get("HostConfig", {}).get("NetworkMode") != "none"
            or not re.fullmatch(r"[0-9a-f]{64}", info.get("Id", ""))
        ):
            raise ValueError("target is not isolated V7 test container")
        self.container, self.database, self.user = info["Id"], database, user

    def run(self, function: str, payload: dict, actor: str) -> dict:
        return self._run_psql(
            [
                "docker",
                "exec",
                "-i",
                "--env",
                "PGOPTIONS=-c statement_timeout=15000 -c lock_timeout=12000",
                self.container,
                "psql",
                "-X",
                "-qAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-v",
                "VERBOSITY=verbose",
                "-U",
                self.user,
                "-d",
                self.database,
                "-f",
                "-",
            ],
            function,
            payload,
            actor,
        )


class PsqlDirect(_PsqlRunner):
    def __init__(
        self,
        socket_dir: str,
        database: str,
        role: str,
        *,
        psql_command: list[str] | None = None,
    ):
        if (
            not isinstance(socket_dir, str)
            or not socket_dir.startswith("/")
            or ":" in socket_dir
        ):
            raise ValueError("invalid socket directory")
        if role == "postgres" or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", role):
            raise ValueError("invalid role")
        if (
            not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]*", database)
            or database == "webdebit_ledger"
        ):
            raise ValueError("invalid database")
        if "PGPASSWORD" in os.environ:
            raise ValueError("PGPASSWORD is forbidden")
        if "PGPASSFILE" in os.environ:
            p = Path(os.environ["PGPASSFILE"])
            if (
                p.is_symlink()
                or not p.is_file()
                or (os.name != "nt" and p.stat().st_mode & 0o177)
            ):
                raise ValueError("invalid PGPASSFILE")
        self.socket_dir, self.database, self.user = socket_dir, database, role
        self.psql_command = list(psql_command or ["psql"])
        probe = self.psql_command + [
            "-X",
            "-qAt",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            socket_dir,
            "-U",
            role,
            "-d",
            database,
            "-c",
            "SELECT current_user='"
            + role
            + "' AND current_user=(SELECT rolname FROM pg_roles WHERE rolname=current_user AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication AND NOT rolbypassrls), EXISTS (SELECT 1 FROM pg_proc WHERE pronamespace='sokhach'::regnamespace AND proname='get_ledger')",
        ]
        try:
            check = subprocess.run(
                probe,
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                env={**os.environ, "PGOPTIONS": "-c statement_timeout=15000 -c lock_timeout=12000"},
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("direct database unavailable") from exc
        if check.returncode or check.stdout.strip() != "t|t":
            raise ValueError("direct database preflight rejected")

    def run(self, function: str, payload: dict, actor: str) -> dict:
        return self._run_psql(
            self.psql_command
            + [
                "-X",
                "-qAt",
                "-v",
                "ON_ERROR_STOP=1",
                "-v",
                "VERBOSITY=verbose",
                "-h",
                self.socket_dir,
                "-U",
                self.user,
                "-d",
                self.database,
                "-f",
                "-",
            ],
            function,
            payload,
            actor,
        )
