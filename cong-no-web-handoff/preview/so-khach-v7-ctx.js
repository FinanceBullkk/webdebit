/* Sổ khách V7 bản live — hợp đồng ctx giữa lõi (initLive trong so-khach-v7-ui.js) và các phần so-khach-v7-*-ui.js.
 *
 * FIELDS: mỗi trường của ctx → [ai ghi, kiểu, ai đọc, ý nghĩa]. "core" là lõi; tên khác là tên phần trong PARTS.
 *   Ai ghi "core+fee": lõi tạo trường, phần fee được gán qua setter. Kiểu: giá trị | hàm | đọc (getter, luôn là giá trị mới
 *   nhất) | đọc/ghi (getter + setter) | danh sách (phần đẩy thêm) | móc (phần có thể không ghi, ví dụ trang thiếu
 *   Presence; nơi đọc gọi bằng ?.).
 * PARTS: thứ tự cài các phần — cũng là thứ tự trình nghe sự kiện của chúng trên #app, trước trình nghe của lõi —
 *   kèm file và các trường của phần khác mà phần đó đọc ngay lúc cài (phải do phần đứng trước ghi).
 *
 * install() cài theo PARTS, không theo thứ tự thẻ <script>, và dừng ngay (lỗi nêu tên trường/phần) khi lõi đưa thiếu
 * hoặc thừa trường, thiếu phần, phần đọc lúc cài trường chưa có, hay phần ghi trường không khai.
 * test-so-khach-v7-ctx.js đối chiếu hợp đồng này với mã từng file (đọc, ghi, thẻ script). Thêm phần mới: khai trường nó
 * ghi/đọc ở FIELDS, thêm một dòng ở PARTS, rồi thêm thẻ script trong so-khach-v7-live.html. */
const SoKhachV7Ctx = (() => {
  'use strict';
  const FIELDS = {
    // Lõi: dữ liệu và hàm dùng chung.
    root: ['core', 'giá trị', 'debit edit fee images loc offset pay presence price ps receipts sheet trips', 'phần tử #app chứa cả sổ'],
    model: ['core', 'giá trị', 'debit edit fee history month offset price ps receipts sheet trips', 'SoKhachV7Model — mọi phép tính tiền (ARCH-03)'],
    api: ['core', 'giá trị', 'edit fee images offset price ps receipts sheet', 'phiên API của sổ (đọc, gửi lệnh, giữ phiên bản)'],
    live: ['core', 'giá trị', 'debit edit offset presence price', 'SoKhachV7Api (tên khách, câu báo dùng chung)'],
    customerId: ['core', 'giá trị', 'debit images offset presence price ps receipts sheet', 'mã khách của sổ đang mở'],
    escape: ['core', 'hàm', 'debit edit fee history images month offset pay price ps receipts sheet trips', 'thoát HTML (CongNoFormat.esc)'],
    fmt: ['core', 'hàm', 'edit history month pay price sheet trips', 'chuỗi VND nguyên → "1.234.567"; trống → "–"'],
    cell: ['core', 'hàm', 'pay trips', 'ô <td> chữ đã thoát'],
    num: ['core', 'hàm', 'month pay trips', 'ô <td> số, căn phải'],
    empty: ['core', 'hàm', 'trips', 'ô <td> trống'],
    spanOf: ['core', 'hàm', 'edit offset sheet', 'số cột của bảng chứa một hàng (để chèn hàng trải hết bảng)'],
    dateText: ['core', 'hàm', 'edit fee history images month offset pay price ps sheet trips', 'yyyy-mm-dd → dd/mm/yyyy'],
    sheetDay: ['core', 'hàm', 'pay trips', 'ngày trong ô Sheet (số ngày Excel, ISO có giờ) → dd/mm/yyyy'],
    dateInput: ['core', 'hàm', 'edit offset', 'dd/mm/yyyy gõ vào → yyyy-mm-dd'],
    monthKey: ['core', 'hàm', 'edit fee history month pay price ps sheet', 'ngày/tháng → "yyyy-mm"'],
    monthLabel: ['core', 'hàm', 'debit edit history month pay price ps sheet', '"yyyy-mm" → "7/2026"'],
    liveOpenMonth: ['core', 'giá trị', 'edit month', 'tháng hiện tại theo đồng hồ máy (giờ VN), khi server chưa trả today_month'],
    methods: ['core', 'giá trị', 'edit offset pay', 'các hình thức thu'],
    fieldNames: ['core', 'giá trị', 'edit trips', 'tên ô chuyến cho nhãn đọc màn hình'],
    moved: ['core', 'giá trị', 'edit trips', 'Map dòng vừa đổi ngày sang tháng khác → tháng cũ (edit ghi nội dung)'],
    ghosts: ['core', 'giá trị', 'edit month', 'dòng mờ "đã chuyển sang tháng" ở tháng cũ (edit ghi nội dung)'],
    sheetFieldLabel: ['core', 'hàm', 'sheet', 'tên cột Sheet trong khung đối chiếu'],
    resolvableSheetFields: ['core', 'giá trị', 'sheet', 'cột lệch Sheet được lấy theo Sheet'],
    moneyText: ['core', 'hàm', 'edit', 'chữ gõ vào → chuỗi VND nguyên (qua model)'],
    referenceFields: ['core', 'hàm', 'edit offset', 'ô Tham chiếu của khung nhập phiếu → { reference }'],
    showNotice: ['core', 'hàm', 'edit fee images offset price ps receipts sheet', 'băng thông báo trên sổ'],
    renderSnapshot: ['core', 'hàm', 'ps receipts sheet', 'vẽ cả sổ từ một bản GET'],
    redraw: ['core', 'hàm', 'edit fee images pay price', 'vẽ lại từ bản đang có, giữ ô ghi thu đang gõ'],
    submit: ['core', 'hàm', 'edit fee images ps sheet', 'gửi lệnh; lỗi thì hiện ở băng thông báo'],
    columns: ['core', 'giá trị', 'edit month price trips', 'khung cột hiện tại: count, trip, feeStart, unitPrice, tags, all, shipper, shipperCell'],
    feeTypeName: ['core', 'hàm', 'fee history ps trips', 'mã loại phụ phí → tên'],
    feeTypes: ['core+fee', 'đọc/ghi', 'debit fee', 'danh mục loại phụ phí (fee nạp)'],
    feeColumnIds: ['core', 'đọc', 'fee month ps trips', 'loại phụ phí có cột riêng của sổ, theo bản GET đang vẽ'],
    snapshot: ['core', 'đọc', 'debit edit fee history images offset price ps receipts sheet', 'bản GET đang vẽ'],
    historyOpen: ['core+edit', 'đọc/ghi', 'edit', 'khung Lịch sử đang mở'],
    busyChecks: ['core', 'danh sách', 'core debit fee images price', 'hàm báo đang mở khung/nhập dở → tạm dừng tự cập nhật'],
    // Phần vẽ vùng màn hình.
    historyList: ['history', 'hàm', 'core', 'danh sách trong khung Lịch sử'],
    legacyTripRow: ['trips', 'hàm', 'month', 'hàng chuyến của dòng sổ gốc'],
    webTripRow: ['trips', 'hàm', 'month', 'hàng chuyến web'],
    sheetPendingRows: ['trips', 'hàm', 'month', 'hàng chuyến Sheet chờ duyệt/lệch chưa nối'],
    conflictsAfterRender: ['trips', 'hàm', 'core', 'tô KHÁC + nút Xem trên dòng lệch Sheet sau khi vẽ'],
    payRows: ['pay', 'hàm', 'month', 'các hàng của danh sách phiếu thu một tháng'],
    monthSections: ['month', 'hàm', 'core', 'các bảng tháng và danh sách tháng'],
    locAfterRender: ['loc', 'hàm', 'core', 'tô dòng và thanh ?loc= sau khi vẽ'],
    // Phần tính năng: hàm cho phần khác.
    reviewReasonText: ['history', 'giá trị', 'edit', 'lý do CHỜ KIỂM → câu tiếng Việt'],
    decoratePrices: ['sheet', 'hàm', 'core', 'gợi ý giá Sheet trên ô Đơn giá sau khi vẽ'],
    todayIso: ['offset', 'hàm', 'edit', 'hôm nay (giờ VN) dạng yyyy-mm-dd'],
    startOffset: ['offset', 'hàm', 'edit', 'mở hàng chọn sổ nguồn khi chọn CẤN TRỪ'],
    openOffsetReceipt: ['offset', 'hàm', 'edit', 'mở hỏi hủy/sửa khoản cấn trừ'],
    offsetState: ['offset', 'giá trị', 'core', 'trạng thái hàng chọn sổ nguồn (giữ qua vẽ lại)'],
    sourceRowHtml: ['offset', 'giá trị', 'core', 'HTML hàng chọn sổ nguồn'],
    renderSourceCell: ['offset', 'hàm', 'core', 'vẽ ô chọn sổ nguồn'],
    openInfoEdit: ['edit', 'hàm', 'sheet', 'mở sửa một ô chuyến'],
    // Móc: lõi/phần khác gọi bằng ?. — phần không cài được (thiếu DOM, thiếu Presence) thì không có.
    removedAfterRender: ['sheet', 'móc', 'core', 'báo dòng Sheet không còn, sau khi vẽ'],
    feeAfterRender: ['fee', 'móc', 'core', 'khôi phục khung phụ phí sau khi vẽ'],
    presenceStale: ['presence', 'móc', 'core', 'thêm tên người cùng mở sổ vào câu "Sổ vừa thay đổi"'],
    imagesOnSnapshot: ['images', 'móc', 'core', 'nạp danh sách ảnh chứng từ khi có bản GET mới'],
    imageClip: ['images', 'móc', 'pay', 'nút 📎 cạnh số tiền phiếu'],
    imageEntryBox: ['images', 'móc', 'pay', 'chỗ dán ảnh trong khung nhập phiếu'],
    afterReceiptSaved: ['images', 'móc', 'edit', 'ghi ảnh đã dán sau khi ghi phiếu'],
    priceOnSnapshot: ['price', 'móc', 'core', 'nạp trạng thái bảng giá khi có bản GET mới'],
    priceButtons: ['price', 'móc', 'core', 'nút Bảng giá ở đầu sổ'],
    priceAfterRender: ['price', 'móc', 'core', 'chữ nhỏ giá theo bảng ở ô Đơn giá sau khi vẽ'],
    psAfterRender: ['ps', 'móc', 'core', 'nút và khung tách phụ phí theo PS sau khi vẽ'],
    receiptButton: ['receipts', 'móc', 'core', 'nút ghi phiếu thu từ Sheet ở đầu sổ'],
    receiptsAfterRender: ['receipts', 'móc', 'core', 'khung phiếu thu Sheet sau khi vẽ'],
  };
  const PARTS = [
    ['history', 'so-khach-v7-history-ui.js', []],
    ['sheet', 'so-khach-v7-sheet-ui.js', []],
    ['offset', 'so-khach-v7-offset-ui.js', []],
    ['edit', 'so-khach-v7-edit-ui.js', ['reviewReasonText', 'todayIso', 'startOffset', 'openOffsetReceipt']],
    ['fee', 'so-khach-v7-fee-ui.js', []],
    ['presence', 'so-khach-v7-presence-ui.js', []],
    ['images', 'so-khach-v7-images-ui.js', []],
    ['debit', 'so-khach-v7-debit-ui.js', []],
    ['price', 'so-khach-v7-price-ui.js', []],
    ['ps', 'so-khach-v7-ps-ui.js', []],
    ['receipts', 'so-khach-v7-receipt-ui.js', []],
    ['trips', 'so-khach-v7-trips-ui.js', []],
    ['pay', 'so-khach-v7-pay-ui.js', []],
    ['month', 'so-khach-v7-month-ui.js', ['legacyTripRow', 'webTripRow', 'sheetPendingRows', 'payRows']],
    ['loc', 'so-khach-v7-loc-ui.js', []],
  ];
  const KINDS = ['giá trị', 'hàm', 'đọc', 'đọc/ghi', 'danh sách', 'móc'];
  const writer = name => FIELDS[name][0].split('+')[0];
  const setters = name => FIELDS[name][0].split('+').slice(1);
  const readers = name => FIELDS[name][2].split(' ').filter(Boolean);

  function install(ctx, registry) {
    const fail = text => { throw Error(`Hợp đồng ctx sổ khách (so-khach-v7-ctx.js): ${text}`); };
    const core = Object.keys(FIELDS).filter(name => writer(name) === 'core');
    const given = Object.keys(ctx);
    const missing = core.filter(name => !given.includes(name)), extra = given.filter(name => !core.includes(name));
    if (missing.length || extra.length) fail(`lõi thiếu ${missing.join(', ') || '–'}; thừa ${extra.join(', ') || '–'}`);
    for (const name of Object.keys(registry)) if (!PARTS.some(([part]) => part === name)) fail(`phần "${name}" chưa khai trong PARTS`);
    for (const [name, file, needs] of PARTS) {
      if (typeof registry[name] !== 'function') fail(`thiếu phần "${name}" (thẻ <script src="${file}">)`);
      const absent = needs.filter(field => ctx[field] === undefined);
      if (absent.length) fail(`phần "${name}" cần ${absent.join(', ')} ngay lúc cài nhưng chưa có`);
      const before = new Set(Object.keys(ctx));
      registry[name](ctx);
      const stray = Object.keys(ctx).filter(field => !before.has(field) && (!Object.hasOwn(FIELDS, field) || writer(field) !== name));
      if (stray.length) fail(`phần "${name}" ghi trường không khai: ${stray.join(', ')}`);
    }
    const lacking = Object.keys(FIELDS).filter(name => writer(name) !== 'core' && FIELDS[name][1] !== 'móc' && ctx[name] === undefined);
    if (lacking.length) fail(`chưa phần nào ghi ${lacking.join(', ')}`);
    return ctx;
  }

  return { FIELDS, PARTS, KINDS, writer, setters, readers, install };
})();
if (typeof module !== 'undefined') module.exports = SoKhachV7Ctx;
