# R. Nghiên cứu tham chiếu ngành

Trạng thái: tài liệu chính thức đọc lại ngày 24/11/2026 (SAP Help Portal, Oracle Fusion docs, Microsoft Learn, Odoo 18 docs, APQC, COSO). Tham chiếu là hướng đọc và kiểm chứng, **không** chứng nhận webdebit đạt chuẩn, **không** khẳng định mô tả đúng đặc thù VCB hay pháp luật Việt Nam (v3 §13).

[← Mục lục](README.md) · Gap: [C](C-gap-analysis.md) · ADR: [F2](F2-adr.md)

Nhãn phân loại (theo yêu cầu tách bạch):

- **TT** — thông lệ ngành chung (nhiều hệ thống cùng làm).
- **YC** — yêu cầu chính thức: luật, chuẩn, khung kiểm soát.
- **NCC** — mẫu triển khai riêng của một nhà cung cấp.
- **KN** — khuyến nghị của chúng tôi cho webdebit.

## 1. Nguồn và giới hạn

- **SAP S/4HANA:** trang help.sap.com đọc qua đường nội dung của chính cổng (bản Cloud 2608 / 2025 FPS02). Một số trang bị cắt (ghi "một phần").
- **Oracle Fusion Financials 25d–26c, Microsoft Dynamics 365 Finance, Odoo 18:** đọc đầy đủ, trừ chỗ ghi khác.
- **APQC:** trang web chặn truy cập tự động; đọc PDF chính thức của APQC "Financial Management Definitions and Key Measures" v2.0.0 (11/2012, PCF 6.0.0, nhóm 8.0). **Số mục ở PCF hiện hành có thể khác** (bản mới đánh số 9.0 — chưa kiểm được).
- **COSO:** Executive Summary khung 2013 (bản PDF trên coso.org) và poster nguyên tắc; bản khung đầy đủ là tài liệu bán, chưa đọc.
- **ISO 20022:** trang danh mục thông điệp từ chối truy cập; chỉ dùng tên khái niệm (camt.053) làm gợi ý đặt tên trường.
- **Không trang nào đọc được nêu luật hay chuẩn kế toán bắt buộc các kiểm soát này;** chúng là thông lệ và tính năng của nhà cung cấp.

## 2. Đối chiếu theo khái niệm

| Khái niệm | TT — thông lệ | YC — chính thức | NCC — mẫu nhà cung cấp (ví dụ) | KN — cho webdebit |
| --- | --- | --- | --- | --- |
| **Nhập sao kê, chống trùng** | Nhập file ngân hàng là đường chính; kiểm số dư đầu = số dư cuối kỳ trước; từ chối sao kê trùng | — | Microsoft: sao kê phải qua kiểm (số dư đầu bằng cuối kỳ trước, không chồng ngày, tổng dòng bằng số dư cuối) mới *Validated*; trùng (tài khoản, mã sao kê, ngày) không nhập. Oracle: phát hiện sao kê trùng, mã sao kê duy nhất theo tài khoản/năm, nhập bảng tính "tất cả hoặc không". Odoo: CAMT.053, CSV, OFX…; số dư lệch chỉ cảnh báo | File Excel gốc (ràng buộc); chặt hơn Odoo: số dư gãy thì không ký coverage; chống trùng hai tầng vì không có mã sao kê ổn định (ADR-TIEN-03) |
| **Đối soát ngân hàng** | Ghép dòng sao kê với giao dịch nội bộ theo luật có thứ tự, có dung sai; một–một tới nhiều–nhiều; ngoại lệ xử lý tay | — | Oracle: luật ghép + luật dung sai gán theo tài khoản; ngoại lệ *Ambiguous/Date/Amount*; đánh dấu *Reviewed* chống đảo nhầm. Microsoft: 1:1, n:1, n:n; dòng chưa khớp chuyển sang kỳ sau; đối soát đã xong không hoàn tác. SAP: thuật toán đọc nội dung chuyển khoản để tìm khoản mở; mục không tự ghi được vào hàng xử lý lại | Luật A/B/C có phiên bản; P0 chỉ gợi ý; không dung sai tự xóa chênh (ADR-TIEN-10) |
| **Tài khoản trung gian (suspense/clearing)** | Tiền đã về nhưng chưa biết của ai nằm ở tài khoản treo, không vào doanh thu | — | Odoo: giao dịch nằm ở tài khoản treo tới khi đối soát. SAP: tài khoản bank clearing trung gian, tài khoản phụ theo phương thức thanh toán để tách tiền đã lệnh khỏi tiền đã đi | P0 chưa có sổ cái: dùng **phần chưa phân bổ** + trạng thái `unidentified`; ánh xạ sang tài khoản treo khi kế toán cần (ADR-TIEN-01, 04) |
| **Cash application** | Áp tiền vào khoản phải thu theo tham chiếu, cho phép trả một phần, dư, on-account | — | SAP: trả một phần (hóa đơn và tiền cùng mở) khác khoản còn lại (residual, cần lý do); có payment advice. Microsoft: luật tạo payment hoặc tất toán hóa đơn, tìm khách theo tài khoản ngân hàng; có hàng duyệt trước khi ghi | Sổ nợ webdebit theo tháng, nợ cũ trước, **không** theo hóa đơn → áp ở mức sổ/phiếu; không dựng AR theo hóa đơn (ADR-TIEN-09) |
| **Trạng thái receipt** | Tách "chưa rõ khách", "biết khách chưa áp", "đã áp", "on-account" | — | Oracle: UNID, UNAPP, APP (+ NSF, REV, STOP); UNAPP → APP khi áp hết hoặc on-account | `unidentified → unapplied → partial → applied` (ADR-TIEN-07) |
| **Trả dư, trả trước** | Phần dư để mở trên khoản tiền hoặc ghi nhận như khoản trả trước (nợ phải trả) | — | Microsoft: dư để mở trên payment; trả trước ghi nợ phải trả qua hồ sơ ghi sổ riêng. Odoo: đặt cọc từ đơn bán trừ vào hóa đơn cuối | Sổ nợ giữ luật hiện hành (dư thành số âm, trừ chuyến sau); tiền chưa rõ mục đích ở sổ tiền (QD-19) |
| **Phải trả, duyệt thanh toán** | Duyệt trước khi trả; khoản bị giữ (hold) không được trả | — | Oracle: duyệt yêu cầu thanh toán tùy chọn, từ chối là dừng. SAP: duyệt lô thanh toán theo tài khoản ngân hàng, một/nhiều cấp, hạn mức người duyệt. Microsoft: nhật ký không duyệt / duyệt tay / workflow | Đề nghị chi có phiên bản + duyệt bắt buộc (QD-12); phải trả đầy đủ ở P1 (ADR-TIEN-15) |
| **Maker–checker, tách nhiệm vụ** | Người tạo khác người duyệt; tách người chuyển với người đối soát | **COSO 2013:** tách nhiệm vụ nằm trong thành phần *Hoạt động kiểm soát*; khi không tách được thì chọn kiểm soát thay thế | Microsoft: mặc định người gửi **được** tự duyệt, có tùy chọn chặn (*Disallow approval by submitter*); luật SoD gồm cặp nhiệm vụ, mức nghiêm trọng, biện pháp giảm nhẹ. SAP: đổi tài khoản ngân hàng cần duyệt hai người, người gửi không tự duyệt | Chặn tự duyệt **ở máy chủ, không tùy chọn**; trùng vai nhập/review có cờ + kiểm soát bù (ADR-TIEN-08) |
| **Dữ liệu chủ nhạy cảm** | Đổi tài khoản thụ hưởng là điểm gian lận phổ biến; cần hai người | — | SAP: đổi trường nhạy cảm của nhà cung cấp làm khóa lần chạy thanh toán tới khi người khác xác nhận | Xác minh độc lập người nhận mới/đổi tài khoản trước khi duyệt (QD-13) |
| **Phân bổ nhiều–nhiều** | Một khoản tiền áp nhiều chứng từ; nhiều khoản tiền áp một chứng từ | — | Oracle, Microsoft đều hỗ trợ khi đối soát tay | Một bảng phân bổ có trần theo giao dịch (ADR-TIEN-05) |
| **Sổ cái và sổ phụ** | Sổ phụ (AR, AP, ngân hàng) đối chiếu với sổ cái | Chuẩn mực/luật kế toán quy định sổ kế toán chính thức (cần kế toán xác nhận phạm vi) | SAP Universal Journal (một bảng cho FI và CO). Oracle: đóng sổ cái có thể bị chặn khi sổ phụ còn mở | Không dựng sổ cái ở P0; sổ tiền là sổ quản trị, xuất CSV (ADR-TIEN-01) |
| **Đóng kỳ** | Kỳ có trạng thái; đóng vĩnh viễn không mở lại; checklist đóng kỳ có phụ thuộc | — | Oracle: Open, Future Enterable, Closed, Permanently Closed, Never Opened. Microsoft: On hold, Permanently closed; workspace đóng kỳ. SAP: mở/đóng kỳ theo loại tài khoản; cockpit đóng kỳ, trạng thái duyệt tách trạng thái việc. Odoo: khóa có ngoại lệ có thời hạn, khóa cứng không đảo | Review ngày ≠ khóa kỳ tháng; mở lại ngày có lý do; khóa vĩnh viễn do kế toán (BR-DC6, ADR-TIEN-07) |
| **Đa pháp nhân** | Mỗi pháp nhân sổ riêng; giao dịch liên công ty ghi hai bên | — | SAP: tất toán khoản của công ty khác tự sinh bút toán cân ở mỗi bên. Oracle: tài khoản phải thu/phải trả liên công ty sinh theo luật. Microsoft: tài khoản due to/due from theo cặp | Chặn phân bổ khác pháp nhân ở P0; liên công ty ở P1 (ADR-TIEN-06) |
| **Đa tệ** | Lưu tiền nguyên tệ và tiền quy đổi kèm tỷ giá, loại tỷ giá; đánh giá lại chênh tỷ giá | — | Oracle: tiền hạch toán = nguyên tệ × tỷ giá; loại tỷ giá Spot/Corporate/User/Fixed. Microsoft: quy đổi riêng sang tiền hạch toán và tiền báo cáo; đánh giá lại ghi lãi/lỗ chưa thực hiện. SAP: tiền công ty bắt buộc, tiền nhóm, thêm tối đa 8 loại | Số nguyên đơn vị nhỏ nhất theo nguyên tệ; tỷ giá `numeric` + nguồn ở P1; không cộng khác tệ (ADR-TIEN-06) |
| **Tiền khách giữ hộ, trả trước** | Ghi như khoản nợ phải trả/nghĩa vụ, không phải doanh thu | Pháp luật ngoại hối, thuế, hợp đồng quyết định bản chất (cần pháp lý xác nhận) | Microsoft: trả trước ghi nợ phải trả | Cổng pháp lý trước P1 (QD-20) |
| **Khung quy trình** | O2C, P2P, quản lý ngân quỹ, kiểm soát nội bộ là nhóm quy trình riêng | APQC PCF là phân loại tham khảo, không bắt buộc | APQC PCF 6.0: 8.2.3 xử lý phải thu (gồm áp tiền), 8.6 phải trả (gồm duyệt thanh toán), 8.7.2 quản lý tiền (đối soát vị thế tiền, phí ngân hàng), 8.8 kiểm soát nội bộ | Dùng làm khung tên quy trình ở [B](B-quy-trinh-as-is-to-be.md) |

## 3. Trạng thái receipt và đảo/gỡ (Oracle)

Oracle phân biệt **đảo receipt** (coi như chưa từng nhận: bút toán đảo, khoản phải thu mở lại) với **gỡ áp** (bỏ áp để hoàn trả, chuyển on-account hoặc áp lại). Đối chiếu webdebit:

| Oracle | webdebit đề xuất |
| --- | --- |
| UNID | `unidentified` — giao dịch vào chưa có dòng phân bổ |
| UNAPP | `unapplied` — chỉ có dòng `customer_unapplied` |
| APP (một phần/toàn bộ) | `partial` / `applied` |
| On-account | Không có ở sổ nợ webdebit (phiếu tự áp nợ cũ trước, dư thành số âm) |
| Reverse | Giao dịch ngân hàng đảo là giao dịch mới; phiếu sổ nợ sai thì hủy có lý do |
| Unapply | Thay bộ phân bổ/gỡ có lý do (BR-AL3, BR-RV2) |

## 4. Đa pháp nhân và đa tệ

- **TT:** mỗi pháp nhân một sổ; mỗi tài khoản ngân hàng một tiền tệ; giao dịch giữ nguyên tệ, quy đổi khi báo cáo với tỷ giá có nguồn.
- **NCC:** SAP bắt buộc tiền của công ty, tiền nhóm toàn hệ thống; Oracle tính tiền hạch toán bằng nguyên tệ nhân tỷ giá theo loại tỷ giá; Microsoft quy đổi riêng sang tiền hạch toán và tiền báo cáo, đánh giá lại số dư ngoại tệ.
- **KN:** P0 một tài khoản VND; schema sẵn nguyên tệ và đơn vị nhỏ nhất; tỷ giá, chênh tỷ giá, liên công ty để P1 sau QD-18, QD-20. Không cộng VND với USD ở bất kỳ báo cáo nào khi chưa có tỷ giá ghi rõ.

## 5. Kiểm soát nội bộ

- **YC (COSO 2013):** năm thành phần — môi trường kiểm soát, đánh giá rủi ro, hoạt động kiểm soát, thông tin và truyền thông, hoạt động giám sát — với 17 nguyên tắc (1–5, 6–9, 10–12, 13–15, 16–17). Nguyên tắc 10–12: chọn hoạt động kiểm soát giảm rủi ro, kiểm soát công nghệ, chính sách và thủ tục. Nguyên tắc 16–17: đánh giá liên tục/riêng biệt và báo khiếm khuyết kịp thời. Về tách nhiệm vụ, Executive Summary viết: "Where segregation of duties is not practical, management selects and develops alternative control activities." Đơn vị nhỏ có thể dùng kiểm soát ít hình thức hơn mà vẫn hiệu quả.
- **NCC:** Microsoft để mặc định người gửi tự duyệt được và cho bật chặn; SAP chặn người gửi tự duyệt khi đổi tài khoản ngân hàng, khóa thanh toán khi đổi trường nhạy cảm; SAP khuyến nghị hai người duyệt mỗi lô thanh toán.
- **KN:** với 2 login người: cấm tự duyệt (máy chủ), cấm người chuyển gỡ cờ chi chưa duyệt; trùng vai nhập/review được phép nhưng có cờ, tóm tắt tuần cho chủ doanh nghiệp, chủ doanh nghiệp tự tải sao kê đối chiếu định kỳ — đúng tinh thần kiểm soát thay thế của COSO (ADR-TIEN-08).

## 6. Khung quy trình APQC (PCF 6.0, bản 2012)

| Mục PCF 6.0 | Nội dung | Quy trình webdebit |
| --- | --- | --- |
| 8.2.3 Process accounts receivable | Nhận, nộp tiền; áp tiền | B §4.1 báo thu, B §5 phân bổ cuối ngày, P0-c |
| 8.3 General accounting and reporting | Đóng sổ, đối chiếu tài khoản | B §5 review ngày; khóa kỳ tháng của kế toán |
| 8.6 Process accounts payable | Kiểm hóa đơn, duyệt thanh toán | B §4.2 đề nghị chi, P0-b; phải trả đầy đủ P1 |
| 8.7.2 Manage cash | Đối soát vị thế tiền, phí ngân hàng | Sổ tiền, coverage, dòng `bank_fee` |
| 8.8 Manage internal controls | Thiết lập, vận hành, giám sát, báo cáo | Vai, cặp xung đột, máy canh, tóm tắt tuần |

Số mục theo bản 2012; PCF hiện hành đánh số lại (chưa kiểm được), nội dung nhóm quy trình tương đương.

## 7. Yêu cầu chính thức tại Việt Nam — cần kế toán, pháp lý xác nhận

Vòng này **không** đọc văn bản pháp luật; các điểm dưới là câu hỏi để kế toán và tư vấn trả lời, không phải kết luận:

- Thời hạn lưu trữ chứng từ, sổ kế toán và sao kê theo Luật Kế toán và văn bản hướng dẫn (ảnh hưởng QD-08).
- Quy định bảo vệ dữ liệu cá nhân đối với tên, số tài khoản của người chuyển/nhận và tài khoản cá nhân (QD-03, QD-08).
- Quy định quản lý ngoại hối và thuế đối với việc nhận USD, đổi tiền, chi hộ cho khách nước ngoài (QD-20).
- Thời điểm ghi nhận doanh thu, hóa đơn so với debit note (v3 §3.1 đã nêu debit note không mặc định là hóa đơn).

## 8. Chưa kiểm được

- SAP: tên ứng dụng "Reconcile Bank Statement Items", trạng thái của F1564, người tạo không được duyệt lô thanh toán, thuật ngữ "cash in transit", đối chiếu liên công ty.
- Oracle: bỏ đối soát tay trong Fusion, ghi đè kiểm trùng, người gửi không được duyệt yêu cầu thanh toán.
- Microsoft: trang hiện hành nói nhật ký thanh toán nhà cung cấp dùng workflow nào; ý nghĩa trạng thái kỳ *Open*; *Mark as new* khi bật Modern bank reconciliation.
- Odoo 18: trang chính thức về ghi khoản trả trước của khách như nợ phải trả; nhập XLSX; bỏ đối soát.
- APQC: số mục PCF hiện hành. COSO: điểm trọng tâm gắn tách nhiệm vụ với nguyên tắc 10 (trong bản khung đầy đủ).

## 9. Kết luận nghiên cứu

- **Áp dụng:** nhập file có kiểm số dư liên tục; chống trùng sao kê; luật ghép có thứ tự và ngoại lệ; trạng thái receipt tách bạch; nhiều–nhiều; maker–checker; xác minh thay đổi tài khoản thụ hưởng; tách review ngày khỏi khóa kỳ; giữ nguyên tệ.
- **Điều chỉnh:** không dựng sổ cái, không AR theo hóa đơn; dung sai không được tự xóa chênh; tự áp chỉ sau shadow; chặn tự duyệt bắt buộc thay vì tùy chọn; số dư lệch thì chặn ký thay vì chỉ cảnh báo.
- **Không áp dụng (ràng buộc v3):** nhập tự động từ ngân hàng, API, hàng chờ thanh toán gửi ngân hàng, học máy ghép tiền.
