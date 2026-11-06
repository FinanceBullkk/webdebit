# PHU-PHI-BU-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: **dòng sổ gốc có Thành tiền khác đơn giá + phụ phí vì tiền nằm ở cột không tiêu đề trên tab Sheet thì bù phần thiếu vào phụ phí, Thành tiền giữ nguyên.**

- **Dòng được bù:** chỉ khi TOTAL trên Sheet bằng đúng đơn giá + mọi ô tiền bên trái cột giá, tới từng đồng. Dòng khác để người xem.
- **Cách ghi:** phần thiếu thành một khoản **Khác** (âm thì **Giảm trừ**), đúng [`PHU-PHI-01`](phu-phi-01.md) (8): cột phí trên tab không có nghĩa cố định. Khoản ghi chú "Theo TOTAL Sheet: cột không tiêu đề".
- **"Phụ phí ban đầu" trên dòng được bù đổi thành Khác:** lệnh ghi không nhận lại loại này. Cùng nhóm chưa phân loại nên máy PS vẫn tách được ([`MAY-PS-01`](may-ps-01.md)).
- **Không đổi tiền:** TOTAL, số dư và phân bổ phiếu thu giữ nguyên, không sinh dòng điều chỉnh. Sheet không bị đụng tới.
- **Tháng khóa:** mở, ghi, khóa lại như [`MAY-KHOA-01`](may-khoa-01.md); tháng người đang mở giữ nguyên.

## Vì sao

Bộ nạp chỉ đọc cột có tiêu đề "OTHER FEE"/"PHU PHI". Cột không tiêu đề không vào phụ phí, trong khi Thành tiền lấy thẳng ô TOTAL. Hậu quả: bảng sổ cộng không ra, debit note bị chặn vì lệch, và sửa một khoản phí trên dòng đó sẽ làm Thành tiền tính lại thiếu phần này, tức giảm nợ nhầm.

Dòng mới không bị vì `sheet_fee` đã lấy phụ phí = TOTAL − đơn giá (`GIA-NGUON-01`), nên chỉ cần bù một lần cho dòng nạp cũ, không đổi bộ nạp.

## Người chốt, thời điểm, phạm vi

Người dùng, chat 4/11/2026: "Có, bù 293 dòng", sau khi Claude báo đo trên `hao` (chỉ đọc): 307 dòng lệch, 293 dòng giải thích được, 14 dòng chưa rõ. Phạm vi: dòng sổ gốc đã nạp, một lần, bằng `tools/v7_fill_fee_gap.py`.

## Trạng thái

ĐÃ CHỐT; ĐÃ TRIỂN KHAI trên `hao` 6/11/2026: 295 dòng ở 42 sổ, số dư không đổi ([nhật ký](../deploys/2026-11-06-bu-phu-phi.md)). CÒN MỞ: 14 dòng ở 3 sổ chưa rõ nguyên nhân, để nguyên.
