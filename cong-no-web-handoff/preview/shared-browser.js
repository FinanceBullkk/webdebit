// Một Chromium cho cả file test trình duyệt, thay cho mỗi ca tự khởi động một cái.
//
// Đo 3/11/2026: khởi động Chromium + mở trang mất ~250 ms, mở context mới trên trình duyệt có sẵn ~80 ms;
// bộ test trình duyệt có gần 200 ca. Mỗi ca vẫn có context riêng nên cookie, storage, quyền clipboard,
// route và đồng hồ trang không lẫn sang ca khác.
//
// Phải require ở đầu file (trực tiếp hoặc qua helper như so-khach-v7-browser-world.js): hook `after` đăng
// ký lúc nạp mới gắn vào gốc của file và đóng trình duyệt khi cả file xong. Gọi `after` trong lúc một ca
// đang chạy sẽ gắn vào chính ca đó, đóng trình duyệt quá sớm.
//
// ERR_NO_BUFFER_SPACE: trên runner windows-latest, thỉnh thoảng connect() của Chromium trả WSAENOBUFS (10055).
// Đo 4/11/2026 (bản chẩn đoán trên runner): khoảng 4 lần trong 96 lượt bộ test, lúc đó chỉ 647–3.129 TIME_WAIT
// trên 16.384 cổng, kết nối sát trước và sau vẫn được, thử lại sau dưới 200 ms là được. Chưa tìm được gốc: không
// phải cạn cổng, và lúc đo không thiếu bộ nhớ. Rơi vào trang chính thì page.goto ném lỗi; rơi vào CSS hay JS thì
// trang vẫn "tải xong" nên ca đỏ ở chỗ khác (nút đo 27px khi thiếu một file CSS) hoặc xanh trên trang thiếu CSS.
// Vì vậy lấy `test` từ file này: có đúng lỗi này trong lượt chạy thì chạy lại ca một lần, lỗi khác giữ nguyên.

const nodeTest = require('node:test');
const { chromium } = require('playwright');

const NO_BUFFER = 'ERR_NO_BUFFER_SPACE';

let launched = null;
nodeTest.after(() => launched?.then(browser => browser.close(), () => {}));

// Request hỏng vì ERR_NO_BUFFER_SPACE trong lượt chạy hiện tại. Các ca trong một file chạy lần lượt nên một biến là đủ.
let noBufferUrl = null;

function watchNetwork(context) {
  context.on('requestfailed', request => {
    if (request.failure()?.errorText?.includes(NO_BUFFER)) noBufferUrl = request.url();
  });
  return context;
}

// Chạy `run`; lượt nào gặp ERR_NO_BUFFER_SPACE thì chạy lại một lần, kể cả khi lượt đó xanh (có thể đã đo trên trang
// thiếu CSS). Lượt chạy lại đỏ thì báo lỗi của nó. `note` nhận một dòng để log CI còn đếm được số lần thử lại.
async function runWithRetry(run, note) {
  noBufferUrl = null;
  let failure = null;
  try {
    await run();
  } catch (error) {
    if (!noBufferUrl && !String(error?.message).includes(NO_BUFFER)) throw error;
    failure = error;
  }
  if (!noBufferUrl && !failure) return;
  const where = noBufferUrl ?? failure.message.split('\n')[0];
  note(`Thử lại ca này vì ${NO_BUFFER} (${where})`);
  noBufferUrl = null;
  await run();
}

function test(name, options, fn) {
  const body = typeof options === 'function' ? options : fn;
  return nodeTest.test(name, typeof options === 'function' ? {} : options, t => runWithRetry(() => body(t), note => t.diagnostic(note)));
}

// Dùng như Browser của Playwright trong một ca: newPage/newContext mở context mới trên trình duyệt chung,
// close() chỉ đóng các context của ca này.
async function launchShared() {
  launched ??= chromium.launch({ headless: true });
  const browser = await launched;
  const contexts = [];
  return {
    async newContext(options) {
      const context = watchNetwork(await browser.newContext(options));
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

module.exports = { launchShared, runWithRetry, test, watchNetwork };
