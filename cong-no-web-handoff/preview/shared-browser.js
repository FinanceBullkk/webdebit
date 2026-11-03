// Một Chromium cho cả file test trình duyệt, thay cho mỗi ca tự khởi động một cái.
//
// Đo 3/11/2026: khởi động Chromium + mở trang mất ~250 ms, mở context mới trên trình duyệt có sẵn ~80 ms;
// bộ test trình duyệt có gần 200 ca. Mỗi ca vẫn có context riêng nên cookie, storage, quyền clipboard,
// route và đồng hồ trang không lẫn sang ca khác.
//
// Phải require ở đầu file (trực tiếp hoặc qua helper như so-khach-v7-browser-world.js): hook `after` đăng
// ký lúc nạp mới gắn vào gốc của file và đóng trình duyệt khi cả file xong. Gọi `after` trong lúc một ca
// đang chạy sẽ gắn vào chính ca đó, đóng trình duyệt quá sớm.

const { after } = require('node:test');
const { chromium } = require('playwright');

let launched = null;
after(() => launched?.then(browser => browser.close(), () => {}));

// Dùng như Browser của Playwright trong một ca: newPage/newContext mở context mới trên trình duyệt chung,
// close() chỉ đóng các context của ca này.
async function launchShared() {
  launched ??= chromium.launch({ headless: true });
  const browser = await launched;
  const contexts = [];
  return {
    async newContext(options) {
      const context = await browser.newContext(options);
      contexts.push(context);
      return context;
    },
    async newPage(options) {
      return (await this.newContext(options)).newPage();
    },
    async close() {
      await Promise.all(contexts.map(context => context.close()));
    },
  };
}

module.exports = { launchShared };
