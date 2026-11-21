"""WECHAT-01 PR-W2: giải mã ảnh `.dat` của WeChat, chỉ stdlib (agent chạy bằng Python hệ thống, không có thư viện mã hóa).

Hai khuôn:

- **Cũ** (WeChat 3.x): cả file XOR với một byte. Byte đó suy ra từ chữ ký ảnh ở đầu file (JPEG, PNG, GIF, WEBP), không cần khóa.
- **V2** (WeChat 4.x): `07 08 56 32 08 07` + 4 byte độ dài phần AES (little endian) + 4 byte độ dài phần XOR + 1 byte đệm.
  - Phần đầu là AES-128-ECB với khóa ảnh của máy, độ dài làm tròn lên bội 16 có đệm PKCS7.
  - Giữa để nguyên; cuối XOR một byte.
  - Khóa AES là khóa của máy WeChat, suy ngoại tuyến ở `wechat_export.offline_image_key` (tên file `kvcomm` + wxid, kiểm bằng các
    hàm AES ở đây). Không có khóa thì trả None ("chưa đọc được").
  - Byte XOR không biết trước thì suy từ đuôi ảnh (JPEG kết thúc `FF D9`, PNG bằng khối IEND, GIF bằng `3B`).

Kết quả chỉ nhận khi byte đầu đúng chữ ký ảnh; sai khóa, file cụt hay khuôn lạ đều là None, không bao giờ ra ảnh hỏng.
"""
from __future__ import annotations

import struct

V2_MAGIC = b"\x07\x08\x56\x32\x08\x07"
V2_HEADER = struct.Struct("<6sIIx")   # chữ ký, độ dài phần AES, độ dài phần XOR, một byte đệm
SIGNATURES = ((b"\xff\xd8\xff", "image/jpeg"), (b"\x89PNG\r\n\x1a\n", "image/png"), (b"GIF8", "image/gif"))
ENDINGS = {"image/jpeg": b"\xff\xd9", "image/png": b"\xaeB`\x82", "image/gif": b"\x3b"}   # đuôi chắc chắn của ảnh, để suy byte XOR
MAX_BYTES = 30 * 1024 * 1024


# ---- AES-128 (FIPS-197), chỉ để giải phần đầu vài KB của ảnh V2 ----
def _tables() -> tuple[bytes, bytes]:
    """S-box và S-box ngược tính từ trường GF(2^8) (nghịch đảo nhân rồi biến đổi affine), không gõ tay bảng 256 số."""
    exp, log = [0] * 510, [0] * 256
    value = 1
    for power in range(255):   # 3 là phần tử sinh của nhóm nhân
        exp[power] = exp[power + 255] = value
        log[value] = power
        value ^= ((value << 1) ^ (0x1B if value & 0x80 else 0)) & 0xFF
    box = bytearray(256)
    for byte in range(256):
        x = exp[255 - log[byte]] if byte else 0
        result = x
        for _ in range(4):
            x = ((x << 1) | (x >> 7)) & 0xFF
            result ^= x
        box[byte] = result ^ 0x63
    inverse = bytearray(256)
    for byte, substituted in enumerate(box):
        inverse[substituted] = byte
    return bytes(box), bytes(inverse)


SBOX, INV_SBOX = _tables()


def _mul(a: int, b: int) -> int:
    result = 0
    while b:
        if b & 1:
            result ^= a
        a = ((a << 1) ^ (0x1B if a & 0x80 else 0)) & 0xFF
        b >>= 1
    return result


def expand_key(key: bytes) -> list[bytes]:
    """11 khóa vòng của AES-128."""
    if len(key) != 16:
        raise ValueError("AES-128 cần khóa 16 byte")
    words = [list(key[i:i + 4]) for i in range(0, 16, 4)]
    rcon = 1
    for i in range(4, 44):
        word = list(words[i - 1])
        if i % 4 == 0:
            word = [SBOX[b] for b in word[1:] + word[:1]]
            word[0] ^= rcon
            rcon = _mul(rcon, 2)
        words.append([a ^ b for a, b in zip(words[i - 4], word, strict=True)])
    return [bytes(byte for word in words[r * 4:r * 4 + 4] for byte in word) for r in range(11)]


def _mix(state: list[int], coefficients: tuple[int, int, int, int]) -> list[int]:
    out = []
    for column in range(4):
        a = state[column * 4:column * 4 + 4]
        out += [_mul(a[0], coefficients[(0 - row) % 4]) ^ _mul(a[1], coefficients[(1 - row) % 4])
                ^ _mul(a[2], coefficients[(2 - row) % 4]) ^ _mul(a[3], coefficients[(3 - row) % 4]) for row in range(4)]
    return out


def encrypt_block(keys: list[bytes], block: bytes) -> bytes:
    state = [b ^ k for b, k in zip(block, keys[0], strict=True)]
    for round_no in range(1, 11):
        state = [SBOX[b] for b in state]
        state = [state[(i + 4 * (i % 4)) % 16] for i in range(16)]   # dịch hàng r sang trái r ô
        if round_no != 10:
            state = _mix(state, (2, 3, 1, 1))
        state = [b ^ k for b, k in zip(state, keys[round_no], strict=True)]
    return bytes(state)


def decrypt_block(keys: list[bytes], block: bytes) -> bytes:
    state = [b ^ k for b, k in zip(block, keys[10], strict=True)]
    for round_no in range(9, -1, -1):
        state = [state[(i - 4 * (i % 4)) % 16] for i in range(16)]   # dịch hàng r sang phải r ô
        state = [INV_SBOX[b] for b in state]
        state = [b ^ k for b, k in zip(state, keys[round_no], strict=True)]
        if round_no != 0:
            state = _mix(state, (14, 11, 13, 9))
    return bytes(state)


# ---- khuôn file ----
def sniff(data: bytes) -> str | None:
    for signature, mime in SIGNATURES:
        if data.startswith(signature):
            return mime
    return "image/webp" if data[:4] == b"RIFF" and data[8:12] == b"WEBP" else None


def _legacy(data: bytes) -> tuple[str, bytes] | None:
    """Khuôn cũ: thử từng chữ ký ảnh, byte XOR là byte đầu file XOR byte đầu chữ ký; mọi byte còn lại của chữ ký phải khớp."""
    for signature, mime in (*SIGNATURES, (b"RIFF", "image/webp")):
        key = data[0] ^ signature[0]
        if len(data) > 12 and all(data[i] ^ key == byte for i, byte in enumerate(signature)):
            plain = bytes(b ^ key for b in data)
            if sniff(plain) == mime:
                return mime, plain
    return None


def _xor_key(tail: bytes, mime: str) -> int | None:
    ending = ENDINGS.get(mime)
    if not ending or len(tail) < len(ending):
        return None
    key = tail[-1] ^ ending[-1]
    return key if all(tail[-len(ending) + i] ^ key == byte for i, byte in enumerate(ending)) else None


def _v2(data: bytes, aes_key: bytes | None, xor_key: int | None) -> tuple[str, bytes] | None:
    if aes_key is None or len(data) < V2_HEADER.size + 16:
        return None
    _, aes_size, xor_size = V2_HEADER.unpack_from(data)
    body = data[V2_HEADER.size:]
    aligned = aes_size + 16 - aes_size % 16   # PKCS7: đã chẵn khối vẫn có một khối đệm
    if aligned > len(body) or xor_size > len(body) - aligned:
        return None
    keys = expand_key(aes_key)
    head = b"".join(decrypt_block(keys, body[i:i + 16]) for i in range(0, aligned, 16))
    pad = head[-1]
    if not 1 <= pad <= 16 or head[-pad:] != bytes([pad]) * pad:
        return None   # sai khóa: đệm PKCS7 không đúng
    head = head[:-pad]
    mime = sniff(head)
    if mime is None:
        return None
    tail = body[len(body) - xor_size:] if xor_size else b""
    if tail:
        key = xor_key if xor_key is not None else _xor_key(tail, mime)
        if key is None:
            return None
        tail = bytes(b ^ key for b in tail)
    return mime, head + body[aligned:len(body) - xor_size] + tail


def decode(data: bytes, aes_key: bytes | None = None, xor_key: int | None = None) -> tuple[str, bytes] | None:
    """(kiểu ảnh, byte ảnh) hoặc None khi không giải được: thiếu khóa V2, sai khóa, file cụt, khuôn lạ."""
    if not data or len(data) > MAX_BYTES:
        return None
    if data.startswith(V2_MAGIC):
        return _v2(data, aes_key, xor_key)
    return _legacy(data)


def encode_v2(image: bytes, aes_key: bytes, xor_key: int, aes_size: int = 1024, xor_size: int = 64) -> bytes:
    """Dựng file V2 từ ảnh (chỉ cho test, cùng khuôn với file WeChat ghi)."""
    aes_size, xor_size = min(aes_size, len(image)), min(xor_size, max(len(image) - aes_size, 0))
    head = image[:aes_size]
    pad = 16 - len(head) % 16
    keys = expand_key(aes_key)
    cipher = b"".join(encrypt_block(keys, (head + bytes([pad]) * pad)[i:i + 16]) for i in range(0, len(head) + pad, 16))
    middle = image[aes_size:len(image) - xor_size]
    tail = bytes(b ^ xor_key for b in image[len(image) - xor_size:]) if xor_size else b""
    return V2_HEADER.pack(V2_MAGIC, aes_size, xor_size) + cipher + middle + tail
