# COT-PHU-PHI-01

[← Sổ quyết định](../decisions.md)

## Quyết định

Người dùng chốt trong chat ngày 13/11/2026 (gửi ảnh tiêu đề cột phí của debit note): "set giúp mình những cái này là những cột phụ phí default cho mọi sổ khách … và bỏ giới hạn chọn cột phụ phí, và cho bật tắt tất cả".

1. **Bảy cột mặc định cho mọi sổ**, theo thứ tự cột phí của debit note ([DEBIT-NOTE-04](debit-note-04.md)): Lưu bãi (Storage), Ghép (Trucking), Điện (Generator / electricity fee), Neo (Overstay), Health + KĐ (HC fee), Phí hủy (Cancellation fee), Sửa bill (AMD fee). Danh mục thêm ba loại Lưu bãi, Phí hủy, Sửa bill (tên khớp quy tắc `dnFeeCode` nên vào đúng cột chứng từ). HC fee chọn **Health + KĐ** vì đó là loại máy PS ghi và đang có dòng trên `hao`; Health cert vẫn trong danh mục, bật cột riêng được.
2. **Bỏ giới hạn 3 cột riêng mỗi sổ** của [PHU-PHI-01](phu-phi-01.md) (thay "tối đa 3" và điểm (6) "sổ mặc định chỉ có cột Khác"). Loại không bật cột riêng vẫn hiện ở cột Khác như trước.
3. **Cài đặt loại phụ phí** có nút **Bật tất cả** (giữ thứ tự cột đang có, thêm mọi loại đang dùng theo thứ tự danh mục; loại hệ thống vẫn ở cột Khác), **Tắt tất cả** (chỉ còn cột Khác) và **Về mặc định** (bảy cột trên).
4. Sổ hiện có nhận bảy cột một lần bằng migration; cột riêng ngoài bảy cột (nếu có) giữ lại, xếp sau. Sổ mới do máy tạo sổ ([MAY-TAO-SO-01](may-tao-so-01.md)) có sẵn bảy cột. Cột mặc định lưu ở danh mục (`fee_type.default_position`).
5. Máy tách phụ phí PS ([MAY-PS-01](may-ps-01.md)) chỉ **thêm** cột cho loại nhiều tiền nhất của sổ chưa có cột, không thay hay đổi thứ tự cột đang có.

Chỉ đổi cách hiện: không đổi dòng phụ phí, tiền, số dư hay phân bổ.

## Ngày / nguồn

13/11/2026, chat với người dùng; Claude chọn tên ba loại mới (theo gợi ý trong DEBIT-NOTE-04) và chọn Health + KĐ cho HC fee.

## Hiệu lực và giới hạn

ĐÃ CHỐT. **ĐÃ TRIỂN KHAI trên `hao` 13/11/2026 12:14 giờ VN** (#415, migration `2026-11-13-v7-cot-phu-phi-mac-dinh.sql`, release `5a720f8`; [nhật ký](../deploys/2026-11-13-cot-phu-phi-mac-dinh.md)): 242/242 sổ có bảy cột, số dư không đổi. Người dùng chưa tự đi luồng trên bản thật. Bố cục (Claude chọn): cột riêng chưa có khoản nào trong sổ hẹp (60 px, tên loại chữ nhỏ hai dòng); thiếu chỗ thì Tuyến/Shipper nhường trước; vẫn không vừa (bảy cột ở màn 1280 khi sổ có Shipper) thì bảng chuyến cuộn ngang trong khung như màn hẹp, tiêu đề cột cuộn cùng bảng và không dính đầu trang nữa. Không cột nào bị cắt mất. Ba cột trở xuống vẫn vừa 1280 như trước.
