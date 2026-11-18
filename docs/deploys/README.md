# Nhật ký triển khai tay

Mỗi đợt triển khai tay lên `hao` (khi `Deploy hao` dừng ở gate SQL/migration/loader) là **một file mới** ở đây:
`YYYY-MM-DD-<việc>.md`. Không chèn thêm mục vào [runbook](../v7-deploy-runbook.md): runbook giữ quy trình,
file ở đây giữ chuyện đã xảy ra. Các đợt trước 29/10/2026 vẫn nằm trong runbook.

Mỗi file ghi: PR và migration, quyết định liên quan (link tới `../decisions/<id>.md`), người cho chạy và lúc nào,
các bước đã làm (bản sao trước, cửa sổ dừng ghi, release SHA), kết quả kiểm, cách rollback, và điều CÒN MỞ.
Dump, log và số liệu khách nằm trên `hao`, ngoài Git; chỉ ghi tên thư mục bằng chứng. Không chép tổng nợ, số tiền của khách,
tên khách hay số container vào đây: ghi số đếm, mã sổ hoặc câu giữ ý ("tổng nợ không đổi", "bằng tổng Sheet", dấu vân tay
không đổi). `npm run check` chặn số tiền nhóm chấm từ 7 chữ số và số container ([lint](../development.md#lint-và-lệnh-check)).

Triển khai app tự động không ghi ở đây: xem lượt `Deploy hao` và tab *Environments → hao* ([quy trình](../development.md#quy-trình-pr-và-triển-khai)).
