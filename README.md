# webdebit

Bản chia sẻ mã nguồn và fixture giả cho sổ công nợ phải thu HTH. Đây không phải bản sao đầy đủ của workspace nội bộ, không chứa snapshot Google Sheet, dữ liệu khách, chứng từ, database dump hoặc công cụ triển khai/ghi sổ thật. Không dùng repo này như bằng chứng số dư production.

## Cấu trúc

- `cong-no-web-handoff/pilot/reconcile.py`: engine đọc snapshot và đối soát cục bộ; muốn dùng nguồn thật phải được cấp và xác minh riêng, không kèm trong repo.
- `cong-no-web-handoff/web/`: giao diện đọc sổ và tầng truy vấn; web production không được cấu hình bằng repo này.
- `cong-no-web-handoff/tools/`: một số SQL schema và mã export/verify phục vụ phát triển, không có script cài service, SSH hoặc submit giao dịch thật.
- `cong-no-web-handoff/preview/`: giao diện prototype với fixture giả.
- `cong-no-web-handoff/tests/`: unit tests fixture, không kết nối database thật.

## Kiểm tra tại máy Windows

```text
cd cong-no-web-handoff
py -3.13 -m unittest discover -s tests -v
node preview/test-so-cong-no-model.js
node preview/test-monthly-ledger-model.js
```

Các test này kiểm code/fixture cục bộ, không chứng minh số dư thực tế, quyền duyệt, tính sẵn sàng của service hoặc đường ghi tiền. Xem `AGENTS.md` trước khi sửa logic nghiệp vụ.

Dữ liệu sống và hồ sơ quyết định nội bộ không được đưa vào repository. Nếu cần triển khai chức năng tài chính, phải có đặc tả đã duyệt, thử trên DB test và review riêng từng migration/quyền/API.
