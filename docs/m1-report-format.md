# Định dạng báo cáo PostgreSQL M1

`tools/pg_m1_report.py` xuất báo cáo chỉ đọc vào thư mục mới, trống và nằm ngoài Git worktree. `--as-of` nhận định dạng `YYYY-MM-DD`; capture ID chỉ nhận chữ ASCII, số, `_`, `.`, `-`.

## `period_event_counts.csv`

File này bắt buộc với `tools/pg_m1_verify.py`. Mỗi kỳ PostgreSQL có đúng một dòng cho từng loại sự kiện, kể cả loại không có sự kiện:

| Cột | Ý nghĩa |
| --- | --- |
| `capture_id`, `as_of` | Định danh snapshot lặp lại trên từng dòng; verifier đối chiếu với `summary.json` → `run` của replay. |
| `customer`, `debt_period`, `kind` | Khóa khách/kỳ và một trong `opening`, `charge`, `receipt`, `offset`, `adjustment_plus`, `adjustment_minus`. |
| `event_count` | Số dòng `pilot.replay_event` của khóa và loại sự kiện. |
| `amount_nonnull_count` | Số dòng có `amount_vnd` khác NULL. |

Count là số nguyên không âm chính xác; `amount_nonnull_count <= event_count`. Mỗi kỳ phải có đủ sáu dòng duy nhất. Thiếu file, cột, dòng, có dòng trùng, count sai định dạng hoặc capture/as-of không khớp đều làm verifier từ chối và yêu cầu export mới.

Verifier tự đếm `events.jsonl`, kiểm `posting_date` không vượt ngày snapshot trong `summary.json`, rồi so count nguồn, count PostgreSQL, tổng theo kỳ và aggregate tiền. `amount_vnd` và VND aggregate giữ số nguyên chính xác; không dùng số thực.

Aggregate NULL chỉ được tính đóng góp 0 khi cả nguồn và DB cùng chứng minh `event_count=0` và `amount_nonnull_count=0`. Event có amount 0 vẫn có count dương và khác trường hợp không có event. Khi có event, amount và aggregate ở cả nguồn/DB đều bắt buộc. Balance theo kỳ luôn bắt buộc. Export cũ không có count file là chứng cứ không đủ; không sửa CSV cũ để lấp count.

## Đối soát baseline

`period_reconciliation.csv` và `customer_reconciliation.csv` phải có dòng cho mọi kỳ/khách của replay, không trùng khóa. Kết quả chỉ được là `MATCH`, `NO_BASELINE` hoặc `NO_DB_EVENTS`; `INVALID_BASELINE`, `DUPLICATE_BASELINE`, `MISMATCH` hoặc giá trị lạ bị từ chối. Với dòng có baseline, `delta_vnd` bắt buộc là số nguyên bằng 0; delta trống không còn được bỏ qua như 0 (chỉ `NO_BASELINE` được trống). Khóa `NO_BASELINE` theo kỳ vẫn phải khớp danh sách của replay.

`old_book_delta_vnd` trống là chưa biết, không phải 0: khách có baseline mà thiếu giá trị làm verifier từ chối; chỉ khách `NO_BASELINE` được trống và không đóng góp vào tổng. Tập khách `NO_BASELINE` phải khớp các dòng `baseline_row` trống trong `customer_diffs.csv` của replay (file bắt buộc), giống như đã làm với khóa theo kỳ. Export cũ thiếu cột `event_count` ở `period_balances.csv` bị từ chối với yêu cầu export mới.

Báo cáo so replay lịch sử Sheet với snapshot PostgreSQL pilot cô lập. Báo cáo không xác minh tiền ngân hàng, phê duyệt, GL, ghi sổ production hoặc runtime live hiện tại.
