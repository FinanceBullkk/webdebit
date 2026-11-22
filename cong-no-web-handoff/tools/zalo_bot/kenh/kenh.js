"use strict";
// Tiến trình kênh `v7-zalo-kenh` (ZALO-BOT-01, specs/zalo-bot.md): giữ phiên nick phụ bằng zca-js, chuyển tin chat riêng sang bộ
// não qua socket Unix và gửi câu trả lời bộ não trả về. Kênh chạy mã bên thứ ba nên unit systemd chặn mạng tới API web; bật
// ZALO_KENH_REQUIRE_SANDBOX=1 thì kênh tự thử nối API trước, nối được là unit sai và kênh không đăng nhập.
//
//   ZALO_KENH_SOCKET   socket của bộ não (mặc định /run/v7-zalo-sock/kenh.sock)
//   ZALO_KENH_STATE    thư mục trạng thái 0700: credentials.json, qr.png, login-request (mặc định /srv/v7/zalo-kenh)
//
// Quét QR: tạo file `<ZALO_KENH_STATE>/login-request`; kênh ghi `qr.png` (3 mã, mỗi mã 100 giây) rồi tự xóa khi xong.
// Nhật ký chỉ có mã trạng thái, không có chữ tin hay id.

const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const net = require("node:net");
const path = require("node:path");
const core = require("./core");
const { ZaloSession } = require("./zalo");

const VERSION = "0.1.0";
const QUEUE_MAX = 50; // tin đến lúc bộ não chưa nối: giữ 50 tin gần nhất, nối lại thì gửi (bộ não tự chống trùng)
const TICK_MS = 10000;
const REFRESH_AT = { hour: 4, minute: 30 }; // giờ VN đăng nhập lại mỗi ngày

function log(text) {
  console.log(`zalo-kenh: ${text}`);
}

// Kênh có bị chặn tới API web không: chỉ lỗi EPERM/EACCES (eBPF của systemd chặn) mới là có chặn. Nối được, bị từ chối
// (ECONNREFUSED: tới được loopback) hay quá giờ đều coi là thiếu chặn.
function sandboxed({ host = "127.0.0.1", port = 8780, timeoutMs = 2000, connect = net.connect } = {}) {
  return new Promise((resolve) => {
    const socket = connect({ host, port });
    let settled = false;
    const done = (value) => {
      if (settled) return;
      settled = true;
      socket.destroy();
      resolve(value);
    };
    socket.setTimeout(timeoutMs, () => done(false));
    socket.once("connect", () => done(false));
    socket.once("error", (error) => done(error.code === "EPERM" || error.code === "EACCES"));
  });
}

// Socket tới bộ não: tự nối lại (1 giây, gấp đôi tới 30 giây), giữ tin trong lúc đứt, kiểm từng lệnh bộ não gửi.
class Bridge extends EventEmitter {
  constructor({ socketPath, connect = (file) => net.createConnection(file), setTimer = setTimeout, clearTimer = clearTimeout, random = Math.random }) {
    super();
    Object.assign(this, { socketPath, connect, setTimer, clearTimer });
    this.backoff = new core.Backoff({ base: 1000, max: 30000, random });
    this.socket = null;
    this.queue = [];
    this.timer = null;
    this.closed = false;
  }

  start() {
    if (this.closed) return;
    const socket = this.connect(this.socketPath);
    const lines = new core.LineBuffer();
    socket.setEncoding("utf8");
    socket.on("connect", () => {
      this.socket = socket;
      this.backoff.reset();
      this.emit("connect");
      const waiting = this.queue;
      this.queue = [];
      for (const line of waiting) this.write(line);
    });
    socket.on("data", (chunk) => {
      for (const raw of lines.push(String(chunk))) {
        const parsed = core.parseCommand(raw);
        if (parsed.command) this.emit("command", parsed.command);
        else this.emit("note", `bad_command_${parsed.drop}`);
      }
    });
    socket.on("error", () => {}); // sự kiện close đi ngay sau
    socket.on("close", () => {
      if (this.socket === socket) this.socket = null;
      if (this.closed) return;
      this.timer = this.setTimer(() => {
        this.timer = null;
        this.start();
      }, this.backoff.next());
    });
  }

  write(payload) {
    if (!this.socket) return false;
    this.socket.write(core.encode(payload));
    return true;
  }

  message(line) {
    if (this.write(line)) return;
    this.queue.push(line);
    if (this.queue.length > QUEUE_MAX) this.queue.shift();
  }

  close() {
    this.closed = true;
    if (this.timer) this.clearTimer(this.timer);
    if (this.socket) this.socket.destroy();
  }
}

function dueForRefresh(lastDay, ms) {
  const vn = core.vnClock(ms);
  const past = vn.hour > REFRESH_AT.hour || (vn.hour === REFRESH_AT.hour && vn.minute >= REFRESH_AT.minute);
  return vn.day !== lastDay && past ? vn.day : null;
}

async function main(env = process.env) {
  const stateDir = env.ZALO_KENH_STATE || "/srv/v7/zalo-kenh";
  const loginRequest = path.join(stateDir, "login-request");
  fs.mkdirSync(stateDir, { recursive: true, mode: 0o700 });
  const bridge = new Bridge({ socketPath: env.ZALO_KENH_SOCKET || "/run/v7-zalo-sock/kenh.sock" });
  let session = null;
  let current = { state: "connecting", code: null };
  const report = (state, code) => {
    current = { state, code };
    bridge.write({ type: "state", state, code });
    log(`state ${state}${code ? ` ${code}` : ""}`);
  };
  bridge.on("connect", () => {
    bridge.write({ type: "hello", kenh_version: VERSION, own_id: session && core.ID.test(session.ownId || "") ? session.ownId : null });
    bridge.write({ type: "state", ...current });
  });
  bridge.on("note", log);
  process.on("unhandledRejection", () => log("unhandled_rejection"));
  bridge.start();
  if (env.ZALO_KENH_REQUIRE_SANDBOX === "1" && !(await sandboxed())) {
    report("sandbox_missing", "api_reachable"); // không đăng nhập; chờ người sửa unit
    return;
  }
  const zca = await import("zca-js");
  session = new ZaloSession({ zca, stateDir });
  session.on("state", report);
  session.on("message", (line) => bridge.message(line));
  session.on("note", log);
  bridge.on("command", async (command) => {
    if (command.type === "typing") {
      await session.typing(command.threadId);
      return;
    }
    const result = await session.send(command.threadId, command.text, command.quoteMsgId);
    bridge.write({ type: "sent", ref: command.ref, ok: result.ok, code: result.code });
  });
  await session.start();
  let refreshedDay = core.vnClock(Date.now()).day;
  const interval = setInterval(() => {
    if (fs.existsSync(loginRequest)) {
      fs.rmSync(loginRequest, { force: true });
      if (session.state !== "online" && session.state !== "login_pending") session.loginQR().catch(() => log("qr_error"));
    }
    const day = dueForRefresh(refreshedDay, Date.now());
    if (day) {
      refreshedDay = day;
      session.refresh();
    }
  }, TICK_MS);
  const shutdown = () => {
    clearInterval(interval);
    session.stop();
    bridge.close();
    setTimeout(() => process.exit(0), 200);
  };
  process.on("SIGTERM", shutdown);
  process.on("SIGINT", shutdown);
}

if (require.main === module) {
  main().catch((error) => {
    console.error(`zalo-kenh: dừng vì lỗi ${error && error.name}`);
    process.exit(1);
  });
}

module.exports = { Bridge, sandboxed, dueForRefresh, VERSION, QUEUE_MAX };
