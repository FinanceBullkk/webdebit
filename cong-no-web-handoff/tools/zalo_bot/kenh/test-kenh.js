"use strict";
// Test tiến trình kênh bot Zalo (ZALO-BOT-01): phần thuần, phiên zca-js với module zca-js giả, cầu nối socket giả, bước tự kiểm
// chặn mạng. Không cần zca-js thật, mạng hay Zalo.

const assert = require("node:assert/strict");
const { EventEmitter } = require("node:events");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const test = require("node:test");
const core = require("./core");
const { ZaloSession } = require("./zalo");
const { Bridge, sandboxed, dueForRefresh } = require("./kenh");

const TS = 1795316400000; // 22/11/2026 10:00 giờ VN

function userMessage(overrides = {}, data = {}) {
  return { type: 0, threadId: "1111", isSelf: false, ...overrides,
    data: { msgId: "5001", cliMsgId: "1", msgType: "webchat", uidFrom: "1111", ts: String(TS), content: "khách A còn nợ bao nhiêu", ...data } };
}

test("tin chữ chat riêng thành dòng message; mã số lớn đổi sang chuỗi", () => {
  assert.deepEqual(core.normalize(userMessage({ threadId: 1111 }, { msgId: 7123456789012345678n, uidFrom: 1111 })).line, {
    v: 1, type: "message", msg_id: "7123456789012345678", thread_id: "1111", from_id: "1111", ts: TS, kind: "text", text: "khách A còn nợ bao nhiêu",
  });
  const photo = core.normalize(userMessage({}, { msgType: "chat.photo", content: { href: "x" } })).line;
  assert.equal(photo.kind, "image");
  assert.equal(photo.text, null);
  assert.equal(core.normalize(userMessage({}, { msgType: "chat.voice", content: {} })).line.kind, "other");
});

test("tin của chính nick phụ, tin nhóm, thread khác người gửi và tin rỗng bị bỏ", () => {
  assert.deepEqual(core.normalize(userMessage({ isSelf: true })), { drop: "self" });
  assert.deepEqual(core.normalize(userMessage({ type: 1, threadId: "group-1" })), { drop: "group" });
  assert.deepEqual(core.normalize(userMessage({ threadId: "2222" })), { drop: "not_private" });
  assert.deepEqual(core.normalize(userMessage({}, { content: "   " })), { drop: "empty" });
  assert.deepEqual(core.normalize(userMessage({}, { msgId: "có dấu" })), { drop: "bad_id" });
  assert.deepEqual(core.normalize(userMessage({}, { ts: "không phải số" })), { drop: "bad_ts" });
  assert.deepEqual(core.normalize(null), { drop: "shape" });
});

test("lệnh từ bộ não: chỉ gửi tin và báo đang gõ, sai khuôn thì bỏ", () => {
  const send = { v: 1, type: "send", ref: "a-1", thread_id: "1111", text: "Chào", quote_msg_id: "5001" };
  assert.deepEqual(core.parseCommand(JSON.stringify(send)).command, { type: "send", ref: "a-1", threadId: "1111", text: "Chào", quoteMsgId: "5001" });
  assert.deepEqual(core.parseCommand(JSON.stringify({ v: 1, type: "typing", thread_id: "1111" })).command, { type: "typing", threadId: "1111" });
  assert.equal(core.parseCommand("rác").drop, "bad_json");
  assert.equal(core.parseCommand(JSON.stringify({ ...send, v: 2 })).drop, "bad_version");
  assert.equal(core.parseCommand(JSON.stringify({ ...send, type: "delete" })).drop, "bad_type");
  assert.equal(core.parseCommand(JSON.stringify({ ...send, text: "x".repeat(2001) })).drop, "bad_text");
  assert.equal(core.parseCommand(JSON.stringify({ ...send, thread_id: "../etc" })).drop, "bad_thread_id");
  assert.equal(core.parseCommand(JSON.stringify({ ...send, quote_msg_id: 5 })).drop, "bad_quote");
});

test("tách dòng socket qua nhiều mảnh, bỏ dòng quá dài", () => {
  const buffer = new core.LineBuffer(10);
  assert.deepEqual(buffer.push('{"a":'), []);
  assert.deepEqual(buffer.push('1}\n{"b":2}\n'), ['{"a":1}', '{"b":2}']);
  assert.deepEqual(buffer.push("x".repeat(15)), []);
  assert.deepEqual(buffer.push("yyy\nok\n"), ["ok"]);
  assert.equal(buffer.dropped, 1);
});

test("nhịp nối lại 5 giây gấp đôi tới 5 phút; đặt lại khi nối được", () => {
  const backoff = new core.Backoff({ random: () => 0.5 });
  assert.deepEqual([1, 2, 3, 4, 5, 6, 7, 8].map(() => backoff.next()), [5000, 10000, 20000, 40000, 80000, 160000, 300000, 300000]);
  backoff.reset();
  assert.equal(backoff.next(), 5000);
});

test("bị đá: mã 3000/3003 ngay, hoặc 3 lần đóng sớm trong 10 phút", () => {
  const judge = new core.CloseJudge();
  assert.equal(judge.judge(3000, 999999, 0), "kicked");
  assert.equal(judge.judge(1006, 120000, 0), "retry");
  assert.equal(judge.judge(1000, 5000, 1000), "retry");
  assert.equal(judge.judge(1000, 5000, 2000), "retry");
  assert.equal(judge.judge(1000, 5000, 3000), "kicked");
  const late = new core.CloseJudge();
  late.judge(1000, 5000, 0);
  late.judge(1000, 5000, 1000);
  assert.equal(late.judge(1000, 5000, 700000), "retry"); // hai lần trước đã quá 10 phút
});

test("nhớ tin gần đây để trích, bỏ tin cũ nhất khi đầy; giờ Việt Nam", () => {
  const recent = new core.Recent(2);
  recent.add("a", 1);
  recent.add("b", 2);
  recent.add("c", 3);
  assert.deepEqual([recent.get("a"), recent.get("b"), recent.get("c"), recent.get(null)], [null, 2, 3, null]);
  assert.deepEqual(core.vnClock(Date.UTC(2026, 10, 21, 21, 30)), { day: "2026-11-22", hour: 4, minute: 30 });
  assert.equal(dueForRefresh("2026-11-21", Date.UTC(2026, 10, 21, 21, 29)), null);
  assert.equal(dueForRefresh("2026-11-21", Date.UTC(2026, 10, 21, 21, 30)), "2026-11-22");
  assert.equal(dueForRefresh("2026-11-22", Date.UTC(2026, 10, 22, 3, 0)), null);
});

// zca-js giả: đủ phần kênh dùng (Zalo.login, Zalo.loginQR, listener, sendMessage, sendTypingEvent, getContext, getOwnId).
function fakeZca({ loginFails = 0, qr = null } = {}) {
  const made = { options: [], apis: [], logins: 0 };
  class Listener extends EventEmitter {
    constructor() {
      super();
      this.started = 0;
      this.stopped = 0;
    }
    start() { this.started += 1; }
    stop() { this.stopped += 1; }
  }
  class Api {
    constructor() {
      this.listener = new Listener();
      this.sent = [];
      this.typed = [];
      made.apis.push(this);
    }
    getOwnId() { return 999; }
    getContext() {
      return { imei: "imei-1", userAgent: "UA", language: "vi", cookie: { toJSON: () => ({ version: "x", cookies: [{ key: "k", value: "v" }] }) } };
    }
    async sendMessage(content, threadId, type) { this.sent.push({ content, threadId, type }); return { message: { msgId: 1 } }; }
    async sendTypingEvent(threadId, type) { this.typed.push({ threadId, type }); return { status: 0 }; }
  }
  class Zalo {
    constructor(options) { made.options.push(options); }
    async login(credentials) {
      made.logins += 1;
      made.lastCredentials = credentials;
      if (made.logins <= loginFails) throw new Error("login");
      return new Api();
    }
    async loginQR(options, callback) { return qr(callback, () => new Api()); }
  }
  const zca = { Zalo, ThreadType: { User: 0, Group: 1 }, LoginQRCallbackEventType: { QRCodeGenerated: 0, QRCodeExpired: 1, QRCodeScanned: 2, QRCodeDeclined: 3, GotLoginInfo: 4 } };
  return { zca, made };
}

function harness(options = {}, { credentials = true } = {}) {
  const stateDir = fs.mkdtempSync(path.join(os.tmpdir(), "zalo-kenh-"));
  if (credentials) fs.writeFileSync(path.join(stateDir, "credentials.json"), JSON.stringify({ imei: "i", cookie: [], userAgent: "UA" }));
  const { zca, made } = fakeZca(options);
  const timers = [];
  let clock = TS;
  const session = new ZaloSession({ zca, stateDir, now: () => clock, random: () => 0.5,
    setTimer: (fn, delay) => { timers.push({ fn, delay }); return timers.length; }, clearTimer: () => {} });
  const states = [];
  const lines = [];
  session.on("state", (state, code) => states.push(code ? `${state}:${code}` : state));
  session.on("message", (line) => lines.push(line));
  return { session, made, timers, states, lines, stateDir, advance: (ms) => { clock += ms; } };
}

test("không có file đăng nhập thì báo cần quét QR, không gọi Zalo", async () => {
  const h = harness({}, { credentials: false });
  await h.session.start();
  assert.deepEqual(h.states, ["login_required:no_credentials"]);
  assert.equal(h.made.logins, 0);
});

test("đăng nhập bằng file, tắt checkUpdate và logging, nhận tin, trả lời có trích bằng ThreadType.User", async () => {
  const h = harness();
  await h.session.start();
  assert.deepEqual(h.made.options[0], { selfListen: false, checkUpdate: false, logging: false });
  const api = h.made.apis[0];
  assert.equal(api.listener.started, 1);
  assert.ok(api.listener.listenerCount("error") > 0, "thiếu handler error thì Node chết");
  api.listener.emit("connected");
  assert.equal(h.session.state, "online");
  api.listener.emit("message", userMessage());
  api.listener.emit("message", userMessage({ type: 1, threadId: "g" }));
  assert.equal(h.lines.length, 1);
  assert.deepEqual(await h.session.send("1111", "Chào", "5001"), { ok: true, code: null });
  assert.equal(api.sent[0].type, 0);
  assert.equal(api.sent[0].content.quote.msgId, "5001");
  await h.session.send("1111", "Không trích", null);
  assert.equal(api.sent[1].content.quote, undefined);
  await h.session.typing("1111");
  assert.deepEqual(api.typed, [{ threadId: "1111", type: 0 }]);
});

test("rớt mạng thì đăng nhập lại bằng API mới theo nhịp chờ; bị đá thì dừng tự nối", async () => {
  const h = harness();
  await h.session.start();
  h.made.apis[0].listener.emit("connected");
  h.advance(120000);
  h.made.apis[0].listener.emit("closed", 1006);
  assert.equal(h.session.state, "offline");
  assert.equal(h.timers.at(-1).delay, 5000);
  await h.timers.at(-1).fn();
  assert.equal(h.made.apis.length, 2);
  h.made.apis[0].listener.emit("closed", 1006); // API cũ báo muộn: bỏ qua
  assert.equal(h.timers.length, 1);
  h.made.apis[1].listener.emit("connected");
  h.made.apis[1].listener.emit("closed", 3000);
  assert.deepEqual([h.session.state, h.session.code], ["kicked", "duplicate_connection"]);
  assert.equal(h.timers.length, 1);
  assert.deepEqual(await h.session.send("1111", "x"), { ok: false, code: "not_online" });
});

test("đăng nhập bằng file lỗi 3 lần liền thì báo cần quét QR", async () => {
  const h = harness({ loginFails: 5 });
  await h.session.start();
  await h.timers[0].fn();
  await h.timers[1].fn();
  assert.deepEqual([h.session.state, h.session.code], ["login_required", "login_failed"]);
  assert.equal(h.made.logins, 3);
});

test("quét QR: ghi ảnh 0600, mã hết hạn thì xin mã mới tối đa 3 lần, quét xong lưu file đăng nhập rồi nghe tin", async () => {
  const seen = [];
  const h = harness({ qr: async (callback, makeApi) => {
    const actions = { retry: () => seen.push("retry"), abort: () => seen.push("abort") };
    callback({ type: 0, data: { image: Buffer.from("PNG1").toString("base64") }, actions });
    seen.push(fs.readFileSync(path.join(h.stateDir, "qr.png"), "utf8"));
    callback({ type: 1, data: null, actions });
    callback({ type: 0, data: { image: Buffer.from("PNG2").toString("base64") }, actions });
    callback({ type: 0, data: { image: Buffer.from("PNG3").toString("base64") }, actions });
    callback({ type: 1, data: null, actions });
    return makeApi();
  } }, { credentials: false });
  assert.equal(await h.session.loginQR(), true);
  assert.deepEqual(seen, ["PNG1", "retry", "abort"]);
  assert.equal(fs.existsSync(path.join(h.stateDir, "qr.png")), false);
  const saved = JSON.parse(fs.readFileSync(path.join(h.stateDir, "credentials.json"), "utf8"));
  assert.deepEqual(saved, { imei: "imei-1", cookie: [{ key: "k", value: "v" }], userAgent: "UA", language: "vi" });
  if (process.platform !== "win32") assert.equal(fs.statSync(path.join(h.stateDir, "credentials.json")).mode & 0o777, 0o600);
  assert.equal(h.made.apis.at(-1).listener.started, 1);
  assert.deepEqual(h.states.slice(0, 2), ["login_pending", "connecting:qr_scanned"]);
});

test("quét QR bị hủy hay hết mã thì báo cần quét lại và xóa ảnh QR", async () => {
  const h = harness({ qr: async (callback) => {
    callback({ type: 0, data: { image: "UE5H" }, actions: { retry() {}, abort() {} } });
    throw new Error("aborted");
  } }, { credentials: false });
  assert.equal(await h.session.loginQR(), false);
  assert.deepEqual([h.session.state, h.session.code], ["login_required", "qr_not_scanned"]);
  assert.equal(fs.existsSync(path.join(h.stateDir, "qr.png")), false);
});

test("đăng nhập lại mỗi ngày: đóng listener cũ, nghỉ 5 giây rồi đăng nhập; dừng thì không tự nối", async () => {
  const h = harness();
  await h.session.start();
  h.made.apis[0].listener.emit("connected");
  assert.equal(h.session.refresh(), true);
  assert.equal(h.made.apis[0].listener.stopped, 1);
  assert.equal(h.timers.at(-1).delay, 5000);
  await h.timers.at(-1).fn();
  assert.equal(h.made.apis.length, 2);
  assert.equal(h.session.refresh(), false); // chưa nối xong: không đăng nhập chồng
  h.session.stop();
  assert.equal(h.made.apis[1].listener.stopped, 1);
  h.made.apis[1].listener.emit("closed", 1006);
  assert.equal(h.timers.length, 1);
});

function fakeSocket() {
  const socket = new EventEmitter();
  socket.written = [];
  socket.setEncoding = () => {};
  socket.write = (text) => socket.written.push(text);
  socket.destroy = () => socket.emit("close");
  return socket;
}

test("cầu nối: giữ tin lúc bộ não chưa nối, nối thì gửi; lệnh hợp lệ mới tới phiên; đứt thì tự nối lại", () => {
  const sockets = [];
  const timers = [];
  const bridge = new Bridge({ socketPath: "x", connect: () => { const s = fakeSocket(); sockets.push(s); return s; },
    setTimer: (fn, delay) => { timers.push({ fn, delay }); return 1; }, clearTimer: () => {}, random: () => 0.5 });
  const commands = [];
  const notes = [];
  bridge.on("command", (command) => commands.push(command));
  bridge.on("note", (note) => notes.push(note));
  bridge.start();
  bridge.message({ v: 1, type: "message", msg_id: "1" });
  assert.equal(sockets[0].written.length, 0);
  sockets[0].emit("connect");
  assert.deepEqual(sockets[0].written.map((line) => JSON.parse(line).msg_id), ["1"]);
  sockets[0].emit("data", `${JSON.stringify({ v: 1, type: "typing", thread_id: "1111" })}\n{"v":1,"type":"exec","thread_id":"1111"}\n`);
  assert.deepEqual(commands, [{ type: "typing", threadId: "1111" }]);
  assert.deepEqual(notes, ["bad_command_bad_type"]);
  sockets[0].emit("close");
  assert.equal(timers[0].delay, 1000);
  timers[0].fn();
  assert.equal(sockets.length, 2);
  bridge.close();
});

test("tự kiểm chặn mạng: chỉ EPERM/EACCES là có chặn; nối được hay bị từ chối là thiếu chặn", async () => {
  const fake = (event, payload) => () => {
    const socket = new EventEmitter();
    socket.setTimeout = () => {};
    socket.destroy = () => {};
    setImmediate(() => socket.emit(event, payload));
    return socket;
  };
  assert.equal(await sandboxed({ connect: fake("error", Object.assign(new Error("x"), { code: "EPERM" })) }), true);
  assert.equal(await sandboxed({ connect: fake("error", Object.assign(new Error("x"), { code: "ECONNREFUSED" })) }), false);
  assert.equal(await sandboxed({ connect: fake("connect") }), false);
});
