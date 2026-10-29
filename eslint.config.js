// Lint JavaScript cho workspace công nợ.
//
// Mã preview chạy cả trong trình duyệt (IIFE gán biến toàn cục) lẫn trong Node
// (`module.exports` + `require`), nên một cấu hình dùng chung globals của cả hai.
// Không bật luật định dạng: dòng dài nhất trong preview là 1878 ký tự (bảng
// fixture một dòng một bản ghi), ép xuống dòng sẽ làm hỏng tính dễ đọc của
// fixture mà không bắt được lỗi nào.

const js = require("@eslint/js");
const globals = require("globals");

module.exports = [
  {
    ignores: [
      "node_modules/**",
      ".venv/**",
      ".playwright-browsers/**",
      "test-results/**",
    ],
  },
  js.configs.recommended,
  {
    files: ["**/*.js"],
    languageOptions: {
      ecmaVersion: 2024,
      sourceType: "commonjs",
      globals: { ...globals.node, ...globals.browser },
    },
    rules: {
      // Biến/tham số thừa thường là dấu hiệu refactor bỏ sót; cho phép bỏ qua
      // bằng tiền tố _ khi chữ ký hàm bắt buộc phải có tham số đó.
      "no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_", caughtErrorsIgnorePattern: "^_" },
      ],
      eqeqeq: ["error", "smart"],
      "no-var": "error",
      "prefer-const": "error",
      // Nuốt lỗi im lặng ở đường tính tiền là rủi ro nghiệp vụ, không phải style.
      "no-empty": ["error", { allowEmptyCatch: false }],
    },
  },
  {
    // Các file preview nạp nhau bằng thẻ <script> trong mockup HTML, nên tên
    // model của file này là global đối với file kia. Khai báo readonly để
    // no-undef vẫn bắt được lỗi gõ sai tên thật.
    files: ["cong-no-web-handoff/preview/**/*.js"],
    languageOptions: {
      globals: {
        CongNoFormat: "readonly",
        DashboardModel: "readonly",
        DebitNoteXlsx: "readonly",
        CustomerLedgerWorkbench: "readonly",
        LedgerPreview: "readonly",
        LedgerV5Model: "readonly",
        MonthlyLedgerPreview: "readonly",
        SO_KHACH_V7_MAU: "readonly",
        SoKhachV7Model: "readonly",
      },
    },
  },
];
