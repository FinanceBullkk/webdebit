"use strict";
// Phiên zca-js của nick phụ (ZALO-BOT-01 Phần 1): đăng nhập bằng file đã lưu, quét QR khi được yêu cầu, nghe tin chat riêng,
// gửi tin và báo đang gõ, tự nối lại khi rớt mạng, dừng khi bị phiên khác đá. Rút từ mã zca-js 2.3.0 và zalo-agent-cli:
// - tắt `checkUpdate` (gọi npm registry mỗi lần đăng nhập) và `logging` (in uid, tên ra stdout);
// - luôn gắn handler `error` cho listener, thiếu là Node chết;
// - không dùng lại Listener cũ: rớt thì đăng nhập lại bằng file đã lưu để có API mới (zca-js PR #387);
// - tự nối lại theo Backoff, vì `retryOnClose` của zca-js không thử lại mã 1006 và không đặt lại bộ đếm (PR #371);
// - mã QR hết hạn sau 100 giây; có callback thì phải gọi retry()/abort(), không thì promise treo;
// - tự ghi ảnh QR (0600) vào thư mục trạng thái thay vì để zca-js ghi `qr.png` ở thư mục làm việc.
// `zca` là module zca-js (test truyền module giả), nên file này không tự import zca-js.

const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const path = require("node:path");
const core = require("./core");

const USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:133.0) Gecko/20100101 Firefox/133.0"; // mặc định của zca-js
const QR_ATTEMPTS = 3; // 3 mã QR liền, mỗi mã sống 100 giây
const LOGIN_TRIES = 3; // đăng nhập bằng file lỗi 3 lần liền thì coi như phải quét QR lại
const REFRESH_PAUSE = 5000; // nghỉ giữa lúc đóng phiên cũ và đăng nhập lại (zca-js #331: đóng không sạch thì bị đá)
const CLOSE_CODE = { 1000: "closed_rapidly", 1006: "abnormal_closure", 3000: "duplicate_connection", 3003: "kick_connection" };

function writePrivate(file, data, encoding) {
  const tmp = `${file}.tmp-${process.pid}`;
  fs.writeFileSync(tmp, data, { encoding, mode: 0o600 });
  fs.chmodSync(tmp, 0o600);
  fs.renameSync(tmp, file);
}

class ZaloSession extends EventEmitter {
  constructor({ zca, stateDir, now = Date.now, setTimer = setTimeout, clearTimer = clearTimeout, random = Math.random }) {
    super();
    Object.assign(this, { zca, stateDir, now, setTimer, clearTimer });
    this.credentialsFile = path.join(stateDir, "credentials.json");
    this.qrFile = path.join(stateDir, "qr.png");
    this.state = "connecting";
    this.code = null;
    this.api = null;
    this.ownId = null;
    this.connectedAt = 0;
    this.loginFailures = 0;
    this.timer = null;
    this.stopped = false;
    this.backoff = new core.Backoff({ random });
    this.judge = new core.CloseJudge();
    this.recent = new core.Recent();
  }

  setState(state, code = null) {
    if (state === this.state && code === this.code) return;
    this.state = state;
    this.code = code;
    this.emit("state", state, code);
  }

  newZalo() {
    return new this.zca.Zalo({ selfListen: false, checkUpdate: false, logging: false });
  }

  readCredentials() {
    const data = JSON.parse(fs.readFileSync(this.credentialsFile, "utf8"));
    if (!data || typeof data.imei !== "string" || !Array.isArray(data.cookie) || typeof data.userAgent !== "string") {
      throw new Error("credentials shape");
    }
    return data;
  }

  async start() {
    if (!fs.existsSync(this.credentialsFile)) {
      this.setState("login_required", "no_credentials");
      return;
    }
    await this.login();
  }

  async login() {
    this.clearRetry();
    if (this.stopped) return;
    this.setState("connecting");
    let api;
    try {
      api = await this.newZalo().login(this.readCredentials());
    } catch {
      this.loginFailures += 1;
      if (this.loginFailures >= LOGIN_TRIES) {
        this.setState("login_required", "login_failed");
      } else {
        this.setState("offline", "login_retry");
        this.retryLater(this.backoff.next());
      }
      return;
    }
    this.loginFailures = 0;
    this.attach(api);
  }

  attach(api) {
    if (this.stopped) return;
    this.api = api;
    this.ownId = String(api.getOwnId());
    const listener = api.listener;
    listener.on("error", () => this.emit("note", "listener_error"));
    listener.on("connected", () => {
      if (this.api !== api) return;
      this.connectedAt = this.now();
      this.backoff.reset();
      this.setState("online");
    });
    listener.on("message", (message) => {
      if (this.api === api) this.onMessage(message);
    });
    listener.on("closed", (code) => {
      if (this.api === api) this.onClosed(Number(code));
    });
    listener.start();
  }

  onMessage(message) {
    const result = core.normalize(message);
    if (result.drop) {
      this.emit("note", `drop_${result.drop}`);
      return;
    }
    this.recent.add(result.line.msg_id, message.data);
    this.emit("message", result.line);
  }

  onClosed(code) {
    this.api = null;
    if (this.stopped) return;
    const uptime = this.connectedAt ? this.now() - this.connectedAt : 0;
    this.connectedAt = 0;
    const reason = CLOSE_CODE[code] || "closed";
    if (this.judge.judge(code, uptime, this.now()) === "kicked") {
      this.setState("kicked", reason); // không tự nối: cần người xem ai đang dùng nick phụ, rồi quét QR lại
      return;
    }
    this.setState("offline", reason);
    this.retryLater(this.backoff.next());
  }

  retryLater(delay) {
    this.clearRetry();
    this.timer = this.setTimer(() => {
      this.timer = null;
      return this.login(); // setTimeout bỏ qua giá trị trả về; test chờ được lượt đăng nhập
    }, delay);
  }

  clearRetry() {
    if (this.timer) this.clearTimer(this.timer);
    this.timer = null;
  }

  closeApi() {
    const api = this.api;
    this.api = null; // handler `closed` của API cũ thấy không còn là API hiện tại nên bỏ qua
    if (!api) return;
    try {
      api.listener.stop();
    } catch {
      // listener đã đóng
    }
  }

  // Đăng nhập lại có chủ đích (mỗi ngày một lần): người dùng zca-js thấy listener để lâu thì không nhận tin nữa (#153, #198).
  refresh() {
    if (this.stopped || this.state !== "online") return false;
    this.closeApi();
    this.setState("connecting", "daily_refresh");
    this.retryLater(REFRESH_PAUSE);
    return true;
  }

  // Quét QR: chỉ chạy khi có yêu cầu (file `login-request`), ghi ảnh QR cho người dùng quét bằng app Zalo của nick phụ.
  async loginQR() {
    if (this.stopped) return false;
    this.clearRetry();
    this.closeApi();
    this.setState("login_pending");
    const types = this.zca.LoginQRCallbackEventType;
    let shown = 0;
    let api;
    try {
      api = await this.newZalo().loginQR({ userAgent: USER_AGENT }, (event) => {
        if (event.type === types.QRCodeGenerated) {
          shown += 1;
          writePrivate(this.qrFile, event.data.image, "base64");
          this.emit("note", "qr_ready");
        } else if (event.type === types.QRCodeExpired) {
          if (shown < QR_ATTEMPTS) event.actions.retry();
          else event.actions.abort();
        } else if (event.type === types.QRCodeDeclined) {
          event.actions.abort();
        }
      });
    } catch {
      api = null;
    }
    fs.rmSync(this.qrFile, { force: true });
    if (!api || this.stopped) {
      this.setState("login_required", "qr_not_scanned");
      return false;
    }
    const ctx = api.getContext();
    const credentials = { imei: ctx.imei, cookie: ctx.cookie.toJSON().cookies, userAgent: ctx.userAgent, language: ctx.language };
    writePrivate(this.credentialsFile, JSON.stringify(credentials), "utf8");
    this.judge.reset();
    this.loginFailures = 0;
    this.setState("connecting", "qr_scanned");
    this.attach(api);
    return true;
  }

  async send(threadId, text, quoteMsgId) {
    if (!this.api || this.state !== "online") return { ok: false, code: "not_online" };
    const quote = this.recent.get(quoteMsgId);
    try {
      await this.api.sendMessage(quote ? { msg: text, quote } : { msg: text }, threadId, this.zca.ThreadType.User);
      return { ok: true, code: null };
    } catch {
      return { ok: false, code: "zalo_error" };
    }
  }

  async typing(threadId) {
    if (!this.api || this.state !== "online") return;
    try {
      await this.api.sendTypingEvent(threadId, this.zca.ThreadType.User);
    } catch {
      // chỉ là báo đang gõ
    }
  }

  stop() {
    this.stopped = true;
    this.clearRetry();
    this.closeApi();
  }
}

module.exports = { ZaloSession, USER_AGENT, QR_ATTEMPTS, LOGIN_TRIES, CLOSE_CODE };
