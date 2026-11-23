"""Số đệm "sổ còn việc" của menu Quản trị: một lần đọc thay ba (audit giao diện 23/11/2026, F7).

Trước đây menu ở 12/15 trang gọi `/api/v7/inbox`, `/api/v7/dashboard` và `/api/v7/dashboard/debt` lúc mở trang và mỗi 2 phút
(đo trên `hao` 23/11: khoảng 87 KB mỗi lượt, ba lượt gọi). Route này gộp ba nguồn trong một lượt: hộp chờ và Tổng quan giữ nguyên
(menu lưu chúng làm bản chụp để lần đầu mở Việc cần làm vẽ ngay, #342), còn danh sách nợ chỉ giữ mặt hàng và phương thức của
từng sổ — phần duy nhất hàm đếm cần từ đó (47 KB → vài KB). Trình duyệt vẫn đếm bằng `InboxTable.books` của trang Việc cần
làm, nên số trên menu không lệch số trên trang; module này không tự đếm.

Chỉ đọc; các lần đọc DB đi qua bộ nhớ đọc theo dấu dữ liệu (`v7_read_cache`) như hai route Tổng quan.
"""

from __future__ import annotations

from typing import Any

from v7_api_validate import not_found

DEBT_FIELDS = ("customer_id", "name", "commodity", "transport_mode")


def view(inbox_view: dict, dashboard: dict, debt: dict) -> dict[str, Any]:
    """Dựng thân trả về từ ba kết quả đọc đã có; hàm thuần để test."""
    return {
        "inbox": inbox_view,
        "dashboard": dashboard,
        "debt": {"customers": [{key: row.get(key) for key in DEBT_FIELDS} for row in (debt or {}).get("customers") or []]},
    }


def handle_get(query: str, runner, reads, inbox, actor: str) -> dict[str, Any]:
    """GET /api/v7/todo-badge: không nhận tham số."""
    if query:
        not_found()
    return view(inbox.view(runner), reads.run(runner, "get_dashboard", {}, actor), reads.run(runner, "get_dashboard_debt", {}, actor))
