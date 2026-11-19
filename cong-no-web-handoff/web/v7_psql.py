"""Tầng DB của API V7: chạy hàm `sokhach.*` qua psql trong container thử (`Psql`) hoặc qua socket (`PsqlDirect`).

Nơi duy nhất dựng lệnh psql cho đường sổ khách V7 (ARCH-01 trong `scripts/business-rules.js`).
Tách nguyên từ `v7_ledger_api.py` 31/10/2026: lệnh, tham số, timeout và ánh xạ lỗi giữ nguyên.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tempfile
import threading
from collections.abc import Iterator
from pathlib import Path

from v7_api_tables import BASE64, ERRORS, IMAGE_MARK, SQL
from v7_api_validate import ApiError, no_duplicates, vnd

# LUOI-AN-TOAN-01: câu đọc nền (read_only, máy canh) được chạy lâu hơn lệnh của người dùng (15 giây). Đo trên hao 18/11/2026
# lúc API vừa khởi động lại: một sổ lớn mất 8 giây mở bằng get_ledger, cả phần sổ chứa nó 11 giây.
READ_ONLY_STATEMENT_TIMEOUT = "60s"
READ_ONLY_PROCESS_TIMEOUT = 90
# XUAT-SO-01: bản xuất cả sổ đọc mọi sổ trong một giao dịch. Mỗi câu vẫn giới hạn như trên; cả lượt tối đa 5 phút
# (lưới an toàn đo 23 giây cho get_ledger của 242 sổ trên hao, 18/11/2026).
SNAPSHOT_PROCESS_TIMEOUT = 300
SNAPSHOT_READS = frozenset({"get_dashboard", "get_dashboard_debt", "list_customers", "get_fee_types", "get_ledger_export"})
_UNAVAILABLE = "Sổ tạm thời không truy cập được."


def begin_sql(*, read_only: bool = False, consistent: bool = False) -> str:
    """Đầu giao dịch của một lần gọi hàm. Harness PostgreSQL dùng đúng chuỗi này để kiểm ảnh dữ liệu (audit 19/11, A01)."""
    if read_only:
        return ("BEGIN ISOLATION LEVEL REPEATABLE READ, READ ONLY;\n"
                f"SET LOCAL statement_timeout = '{READ_ONLY_STATEMENT_TIMEOUT}';\n")
    return "BEGIN ISOLATION LEVEL REPEATABLE READ, READ ONLY;\n" if consistent else "BEGIN;\n"


def _real_psql(connect: list[str], check_sql: str, env: dict[str, str]) -> list[str]:
    """Lệnh psql nhanh nhất mà vẫn chắc chắn tới đúng cluster.

    `psql` trên Debian/Ubuntu là script Perl `pg_wrapper`: chọn cluster rồi `exec` binary thật. Đo trên `hao` 4/11/2026:
    57 ms mỗi lần gọi so với 11 ms của binary, mà mở một sổ gọi ít nhất 4 lần. Lệnh của API đã có `-X -h -U -d` nên wrapper
    chỉ còn đóng góp cổng: đi thẳng binary khi cổng của server đúng là cổng binary sẽ dùng và binary qua được đúng câu kiểm
    đầu vào. Không chứng minh được thì giữ wrapper, không bao giờ làm hỏng lúc khởi động.
    """
    found = shutil.which("psql")
    if not found or os.path.basename(os.path.realpath(found)) != "pg_wrapper":
        return ["psql"]
    try:
        server = subprocess.run(
            ["psql", *connect, "SELECT current_setting('server_version_num')::int/10000, current_setting('port')"],
            capture_output=True, text=True, timeout=10, check=False, env=env,
        )
        match = re.fullmatch(r"([0-9]+)\|([0-9]+)", server.stdout.strip())
        if server.returncode or not match or match[2] != os.environ.get("PGPORT", "5432"):
            return ["psql"]
        binary = f"/usr/lib/postgresql/{match[1]}/bin/psql"
        check = subprocess.run(
            [binary, *connect, check_sql], capture_output=True, text=True, timeout=10, check=False, env=env,
        )
    except (OSError, subprocess.SubprocessError):
        return ["psql"]
    return [binary] if check.returncode == 0 and check.stdout.strip() == "t|t" else ["psql"]


def _feed(stream, text: str) -> None:
    """Ghi lệnh vào stdin của psql ở luồng riêng: psql in kết quả trong lúc còn nhận lệnh mà không kẹt ống."""
    try:
        stream.write(text)
        stream.close()
    except (OSError, ValueError):
        pass  # psql đã thoát (lỗi hoặc bị dừng): mã thoát của nó báo lỗi


class _PsqlRunner:
    def run(self, function: str, payload: dict, actor: str, *, read_only: bool = False, consistent: bool = False) -> dict:
        try:
            return json.loads(self.run_text(function, payload, actor, read_only=read_only, consistent=consistent))
        except ValueError as exc:
            raise ApiError(
                503, "DB_UNAVAILABLE", "Sổ tạm thời không truy cập được."
            ) from exc

    def run_text(self, function: str, payload: dict, actor: str, *, read_only: bool = False, consistent: bool = False) -> str:
        """Chữ JSON hàm trả về, chưa phân tích (HIEU-NANG-01: bộ nhớ đọc giữ chữ, mỗi lượt `loads` một bản mới).

        `read_only=True` (LUOI-AN-TOAN-01): giao dịch REPEATABLE READ READ ONLY, mọi câu trong hàm cùng một ảnh dữ liệu và
        không ghi được gì; giới hạn thời gian của việc nền (60 giây mỗi câu).
        `consistent=True` (audit 19/11/2026, A01): cùng giao dịch REPEATABLE READ READ ONLY cho lượt GET của người dùng, giữ
        giới hạn thời gian thường. Hàm đọc nhiều câu (get_ledger) dưới READ COMMITTED có thể trả tổng nợ trước một phiếu thu
        cùng danh sách phiếu sau phiếu đó. Đường ghi không dùng cờ này: lệnh ghi gọi get_ledger phải thấy chính phần mình ghi.
        """
        return self._run_psql(self._argv(), function, payload, actor, read_only, consistent)

    def run_snapshot(self, calls: list[tuple[str, dict]], actor: str, *,
                     timeout: float = SNAPSHOT_PROCESS_TIMEOUT) -> Iterator[dict]:
        """Nhiều hàm đọc trong MỘT giao dịch REPEATABLE READ READ ONLY (XUAT-SO-01): mọi kết quả cùng một ảnh dữ liệu.

        Trả lần lượt kết quả từng hàm theo thứ tự `calls` (mỗi hàm một dòng JSON của psql), không giữ cả lượt trong bộ nhớ.
        Chỉ nhận hàm trong SNAPSHOT_READS. Lỗi psql, hết giờ hay thiếu dòng thành DB_UNAVAILABLE ở cuối lượt, sau các kết quả đã
        trả: người gọi bỏ cả lượt. Dừng đọc giữa chừng (đóng generator) thì psql bị dừng.
        """
        if not calls or any(function not in SNAPSHOT_READS for function, _ in calls):
            raise ValueError("snapshot accepts read functions only")
        statements, variables = [], []
        for index, (function, payload) in enumerate(calls):
            statements.append(SQL[function].replace(":'payload'", f":'p{index}'"))
            variables += ["-v", f"p{index}=" + json.dumps(payload, ensure_ascii=False, separators=(",", ":"))]
        sql = ("BEGIN ISOLATION LEVEL REPEATABLE READ, READ ONLY;\n"
               f"SET LOCAL statement_timeout = '{READ_ONLY_STATEMENT_TIMEOUT}';\n"
               "SET LOCAL sokhach.actor = :'actor';\n" + "\n".join(statements) + "\nCOMMIT;\n")
        env = {**os.environ, "PGOPTIONS": "-c statement_timeout=15000 -c lock_timeout=12000"}
        with tempfile.TemporaryFile() as errors:   # stderr ra file: ống đầy không chặn được psql
            try:
                process = subprocess.Popen(self._argv() + variables + ["-v", "actor=" + actor], stdin=subprocess.PIPE,
                                           stdout=subprocess.PIPE, stderr=errors, text=True, encoding="utf-8",
                                           errors="replace", env=env)
            except OSError as exc:
                raise ApiError(503, "DB_UNAVAILABLE", _UNAVAILABLE) from exc
            timer = threading.Timer(timeout, process.kill)
            feeder = threading.Thread(target=_feed, args=(process.stdin, sql), daemon=True)
            timer.start()
            feeder.start()
            count = 0
            try:
                for line in process.stdout:
                    try:
                        value = json.loads(line)
                    except ValueError as exc:
                        raise ApiError(503, "DB_UNAVAILABLE", _UNAVAILABLE) from exc
                    count += 1
                    yield value
                process.wait()
            finally:
                timer.cancel()
                if process.poll() is None:
                    process.kill()
                    process.wait()
                process.stdout.close()
                feeder.join(5)
            if process.returncode or count != len(calls):
                raise ApiError(503, "DB_UNAVAILABLE", _UNAVAILABLE)

    def _argv(self) -> list[str]:
        raise NotImplementedError

    def _run_psql(
        self, argv: list[str], function: str, payload: dict, actor: str, read_only: bool = False,
        consistent: bool = False,
    ) -> str:
        statement = SQL[function]
        if function == "attach_receipt_image":
            payload = dict(payload)
            image = payload.pop("data_base64", None)
            if not isinstance(image, str) or len(image) % 4 or not BASE64.fullmatch(image):
                raise ApiError(422, "IMAGE_INVALID", ERRORS["IMAGE_INVALID"][1])
            statement = statement.replace(IMAGE_MARK, image)
        sql = (
            begin_sql(read_only=read_only, consistent=consistent)
            + "SET LOCAL sokhach.actor = :'actor';\n"
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
                timeout=READ_ONLY_PROCESS_TIMEOUT if read_only else 25,
                check=False,
                env=env,
            )
        except subprocess.TimeoutExpired as exc:
            reading = read_only or function in ("get_ledger", "get_ledger_events", "list_offset_sources", "get_price_table", "get_price_status", "preview_price_table")
            raise ApiError(
                503,
                "DB_UNAVAILABLE" if reading else "RESULT_UNKNOWN",
                "Sổ tạm thời không truy cập được."
                if reading
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
        return result.stdout.strip()


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

    def _argv(self) -> list[str]:
        return [
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
            ]


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
        connect = [
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
        ]
        check_sql = (
            "SELECT current_user='"
            + role
            + "' AND current_user=(SELECT rolname FROM pg_roles WHERE rolname=current_user AND NOT rolsuper AND NOT rolcreaterole AND NOT rolcreatedb AND NOT rolreplication AND NOT rolbypassrls), EXISTS (SELECT 1 FROM pg_proc WHERE pronamespace='sokhach'::regnamespace AND proname='get_ledger')"
        )
        env = {**os.environ, "PGOPTIONS": "-c statement_timeout=15000 -c lock_timeout=12000"}
        try:
            check = subprocess.run(
                self.psql_command + connect + [check_sql],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
                env=env,
            )
        except (OSError, subprocess.SubprocessError) as exc:
            raise ValueError("direct database unavailable") from exc
        if check.returncode or check.stdout.strip() != "t|t":
            raise ValueError("direct database preflight rejected")
        if psql_command is None:
            self.psql_command = _real_psql(connect, check_sql, env)

    def _argv(self) -> list[str]:
        return (
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
            ]
        )
