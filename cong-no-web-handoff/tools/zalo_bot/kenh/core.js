"use strict";
// Phần thuần của tiến trình kênh (ZALO-BOT-01, specs/zalo-bot.md Phần 1): chuyển tin zca-js thành dòng giao thức, kiểm lệnh
// bộ não gửi xuống, tách dòng socket, nhịp chờ nối lại, nhận ra bị phiên khác đá. Không mở socket, không gọi zca-js, nên test
// chạy trên mọi máy. Khuôn dòng phải khớp `zalo_bot/protocol.py`.

const PROTOCOL_VERSION = 1;
const MAX_LINE = 16384;
const MAX_TEXT_OUT = 2000;
const ID = /^[0-9A-Za-z_.:-]{1,64}$/;
const CODE = /^[a-z_]{1,40}$/;
const THREAD_USER = 0; // ThreadType.User của zca-js 2.3.0 (models/Enum.ts); nhóm là 1
// msgType của zca-js (utils.ts): chữ là "webchat" với content là chuỗi; còn lại content là object.
const KIND_BY_MSG_TYPE = { "chat.photo": "image", "chat.sticker": "sticker", "share.file": "file" };

function kindOf(data) {
  if (typeof data.content === "string") return "text";
  return KIND_BY_MSG_TYPE[data.msgType] || "other";
}

// Tin zca-js → dòng `message` của giao thức, hoặc { drop: lý do }. Mã tin là số lớn (json-bigint) nên đổi sang chuỗi trước.
function normalize(message) {
  if (!message || typeof message !== "object" || !message.data || typeof message.data !== "object") return { drop: "shape" };
  if (message.isSelf) return { drop: "self" };
  if (message.type !== THREAD_USER) return { drop: "group" };
  const data = message.data;
  const msgId = String(data.msgId ?? "");
  const threadId = String(message.threadId ?? "");
  const fromId = String(data.uidFrom ?? "");
  if (!ID.test(msgId) || !ID.test(threadId) || !ID.test(fromId)) return { drop: "bad_id" };
  if (threadId !== fromId) return { drop: "not_private" };
  const ts = Number(data.ts);
  if (!Number.isSafeInteger(ts) || ts <= 0) return { drop: "bad_ts" };
  const kind = kindOf(data);
  const text = kind === "text" ? data.content : null;
  if (kind === "text" && !text.trim()) return { drop: "empty" };
  return { line: { v: PROTOCOL_VERSION, type: "message", msg_id: msgId, thread_id: threadId, from_id: fromId, ts, kind, text } };
}

function encode(payload) {
  return `${JSON.stringify({ v: PROTOCOL_VERSION, ...payload })}\n`;
}

// Một dòng bộ não gửi → lệnh đã kiểm, hoặc { drop: lý do }. Kênh không làm gì ngoài gửi tin và báo đang gõ.
function parseCommand(raw) {
  let data;
  try {
    data = JSON.parse(raw);
  } catch {
    return { drop: "bad_json" };
  }
  if (!data || typeof data !== "object" || data.v !== PROTOCOL_VERSION) return { drop: "bad_version" };
  if (typeof data.thread_id !== "string" || !ID.test(data.thread_id)) return { drop: "bad_thread_id" };
  if (data.type === "typing") return { command: { type: "typing", threadId: data.thread_id } };
  if (data.type !== "send") return { drop: "bad_type" };
  if (typeof data.ref !== "string" || !ID.test(data.ref)) return { drop: "bad_ref" };
  if (typeof data.text !== "string" || !data.text || data.text.length > MAX_TEXT_OUT) return { drop: "bad_text" };
  const quote = data.quote_msg_id;
  if (quote !== null && quote !== undefined && (typeof quote !== "string" || !ID.test(quote))) return { drop: "bad_quote" };
  return { command: { type: "send", ref: data.ref, threadId: data.thread_id, text: data.text, quoteMsgId: quote || null } };
}

// Gom dữ liệu socket thành dòng; dòng dài quá MAX_LINE bị bỏ cả dòng (đếm qua `dropped`).
class LineBuffer {
  constructor(limit = MAX_LINE) {
    this.limit = limit;
    this.rest = "";
    this.skipping = false;
    this.dropped = 0;
  }

  push(chunk) {
    const lines = [];
    let text = this.rest + chunk;
    let at;
    while ((at = text.indexOf("\n")) >= 0) {
      const piece = text.slice(0, at);
      text = text.slice(at + 1);
      if (this.skipping || piece.length > this.limit) {
        this.dropped += 1;
        this.skipping = false;
      } else if (piece.trim()) {
        lines.push(piece);
      }
    }
    if (text.length > this.limit) {
      this.skipping = true;
      text = "";
    }
    this.rest = text;
    return lines;
  }
}

// Chờ trước khi nối lại: 5 giây, gấp đôi tới 5 phút, lệch ngẫu nhiên ±20% (cách zalo-agent-cli dùng cho MCP).
class Backoff {
  constructor({ base = 5000, max = 300000, random = Math.random } = {}) {
    Object.assign(this, { base, max, random, attempt: 0 });
  }

  next() {
    const plain = Math.min(this.base * 2 ** this.attempt, this.max);
    this.attempt += 1;
    return Math.round(plain * (0.8 + 0.4 * this.random()));
  }

  reset() {
    this.attempt = 0;
  }
}

// Bị phiên khác đá: zca-js báo 3000 (có kết nối khác) hay 3003 (đăng nhập nơi khác); zalo-agent-cli thấy bị Zalo Web giành phiên
// lại chỉ là 1000 nên đếm lần đóng sớm (nối chưa tới 60 giây): 3 lần trong 10 phút thì coi là bị đá, thôi tự nối để không giành
// phiên qua lại với người đang dùng nick phụ.
const KICK_CODES = new Set([3000, 3003]);

class CloseJudge {
  constructor({ rapidMs = 60000, windowMs = 600000, limit = 3 } = {}) {
    Object.assign(this, { rapidMs, windowMs, limit, rapid: [] });
  }

  judge(code, uptimeMs, now) {
    if (KICK_CODES.has(code)) return "kicked";
    if (uptimeMs < this.rapidMs) {
      this.rapid = this.rapid.filter((at) => now - at < this.windowMs);
      this.rapid.push(now);
      if (this.rapid.length >= this.limit) return "kicked";
    }
    return "retry";
  }

  reset() {
    this.rapid = [];
  }
}

// Giữ dữ liệu tin gần đây để trả lời có trích (zca-js cần cả object tin trong `quote`).
class Recent {
  constructor(limit = 200) {
    this.limit = limit;
    this.items = new Map();
  }

  add(msgId, data) {
    this.items.delete(msgId);
    this.items.set(msgId, data);
    if (this.items.size > this.limit) this.items.delete(this.items.keys().next().value);
  }

  get(msgId) {
    return msgId ? this.items.get(msgId) || null : null;
  }
}

// Giờ Việt Nam (UTC+7, không đổi giờ mùa hè) cho lịch đăng nhập lại mỗi ngày.
function vnClock(ms) {
  const shifted = new Date(ms + 7 * 3600 * 1000);
  return { day: shifted.toISOString().slice(0, 10), hour: shifted.getUTCHours(), minute: shifted.getUTCMinutes() };
}

module.exports = {
  PROTOCOL_VERSION, MAX_LINE, MAX_TEXT_OUT, ID, CODE, THREAD_USER,
  kindOf, normalize, encode, parseCommand, LineBuffer, Backoff, CloseJudge, Recent, vnClock,
};
