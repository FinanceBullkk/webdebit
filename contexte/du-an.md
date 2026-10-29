# Dự án: bối cảnh

- **Mục tiêu:** web quản lý công nợ phải thu vượt trội so với làm trên Google Sheet.
- **Người dùng:** 2–3 người (chủ dự án và 2 người ít rành công nghệ), dùng laptop. Màn thực tế 1280×720 CSS, tuổi trên 40: chữ thân ≥ 16px, vùng bấm ≥ 40px, không thông tin thừa (`docs/ux-guidelines.md`).
- **Đầu ra và tiêu chí xong:** chính xác là ưu tiên số một; web chạy đúng logic nợ và giữ đúng mối liên hệ giữa toàn bộ dữ liệu công nợ; thao tác dễ, gọn, hiệu quả. Nghiệm thu chi tiết ở `SPEC.md`.
- **Công nghệ:** Node 24 (web preview, test, Playwright), Python 3.13 (backend, tools, ruff), PostgreSQL trên máy `hao`.
- **Kiểm tra chính:** `npm run check` (ruff, luật nghiệp vụ, eslint, unittest, test JS và trình duyệt). CI gọi đúng lệnh này.
- **Vai trò agent:** từ 29/10/2026 Claude làm hết (spec, backend, frontend, test, review) theo `CLAUDE-ALL-01`; Codex/Gemini không còn được giao việc.
- **Luồng frontend:** spec có luồng người dùng + đối chiếu dữ liệu, code, kiểm trình duyệt, người dùng nghiệm thu trên bản thử; không bắt buộc mockup Penpot (`docs/development.md#quy-trình-frontend`).
