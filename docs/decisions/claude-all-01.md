# CLAUDE-ALL-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt: **Claude làm hết** — spec, backend (SQL, migration, API), frontend, test và review — không giao Codex làm backend hay Gemini làm frontend nữa. **Bỏ bắt buộc mockup Penpot** được duyệt trước khi code frontend; thay [`FRONTEND`](frontend.md). Vẫn giữ: spec có bước 1 (người dùng và luồng) và bước 2 (đối chiếu dữ liệu/code) trước khi code giao diện, kiểm trình duyệt ở 1280×720, và người dùng tự đi hết luồng trên bản thử (bước 8) trước khi coi là nghiệm thu. Bản xem HTML/ảnh chụp cho người dùng xem trước là tùy Claude, không phải cổng chặn.

## Ngày / nguồn

29/10/2026, người dùng nói trong chat: "bỏ cái rule viết backend cho codex và mockup penpot đi. Làm qua claude hết"

## Hiệu lực và giới hạn

ĐÃ CHỐT quy trình, áp dụng cho việc mới từ 29/10/2026. Không đổi luật tiền, quyền ghi tiền hay các gate triển khai: PR có SQL/migration/loader vẫn hỏi người dùng trước khi merge theo `CLAUDE.md`. [Cộng tác nhiều agent](../multi-agent.md) và `scripts/agent-run.ps1` giữ làm lịch sử, không còn là luồng mặc định. Spec cũ ghi `Agent: codex|gemini` hoặc `Mockup: CHỜ DUYỆT` đọc theo quyết định này.
