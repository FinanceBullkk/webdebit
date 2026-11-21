"""WECHAT-01 PR-W2: giải mã ảnh `.dat` của WeChat bằng dữ liệu giả (không ảnh thật, không khóa thật)."""

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
from zalo_agent import wechat_dat as dat  # noqa: E402

JPEG = b"\xff\xd8\xff\xe0" + bytes(range(256)) * 12 + b"\xff\xd9"
PNG = b"\x89PNG\r\n\x1a\n" + bytes(range(200)) * 9 + b"IEND\xaeB`\x82"
GIF = b"GIF89a" + bytes(range(97)) * 5 + b"\x3b"
WEBP = b"RIFF\x00\x10\x00\x00WEBPVP8 " + bytes(range(64))
KEY = b"0123456789abcdef"   # khóa ảnh giả, 16 ký tự như khóa của máy


class AesTest(unittest.TestCase):
    def test_fips_197_vector_and_sbox(self):
        # FIPS-197, phụ lục C.1 (AES-128): khối và khóa chuẩn.
        keys = dat.expand_key(bytes(range(16)))
        plain = bytes.fromhex("00112233445566778899aabbccddeeff")
        cipher = bytes.fromhex("69c4e0d86a7b0430d8cdb78070b4c55a")
        self.assertEqual((dat.encrypt_block(keys, plain), dat.decrypt_block(keys, cipher)), (cipher, plain))
        self.assertEqual((dat.SBOX[0x00], dat.SBOX[0x01], dat.SBOX[0x53], dat.INV_SBOX[0x63]), (0x63, 0x7C, 0xED, 0x00))
        with self.assertRaises(ValueError):
            dat.expand_key(b"ngan")


class DatTest(unittest.TestCase):
    def test_legacy_single_byte_xor_for_each_image_kind(self):
        for image, mime in ((JPEG, "image/jpeg"), (PNG, "image/png"), (GIF, "image/gif"), (WEBP, "image/webp")):
            for key in (0x00, 0x5A, 0xE3):
                with self.subTest(mime=mime, key=key):
                    self.assertEqual(dat.decode(bytes(b ^ key for b in image)), (mime, image))   # không cần khóa: suy từ chữ ký

    def test_v2_with_the_machine_key_and_xor_byte_from_the_image_end(self):
        for image, mime in ((JPEG, "image/jpeg"), (PNG, "image/png"), (GIF, "image/gif")):
            with self.subTest(mime=mime):
                packed = dat.encode_v2(image, KEY, xor_key=0x37)
                self.assertTrue(packed.startswith(dat.V2_MAGIC))
                self.assertEqual(dat.decode(packed, KEY), (mime, image))                   # byte XOR suy từ đuôi ảnh
                self.assertEqual(dat.decode(packed, KEY, xor_key=0x37), (mime, image))
        for aes_size, xor_size in ((16, 0), (1024, 0), (len(JPEG), 0), (1000, 300)):   # đã chẵn khối, không có phần XOR, cả ảnh là AES
            with self.subTest(aes_size=aes_size, xor_size=xor_size):
                self.assertEqual(dat.decode(dat.encode_v2(JPEG, KEY, 0x11, aes_size, xor_size), KEY), ("image/jpeg", JPEG))

    def test_anything_doubtful_is_none_never_a_broken_image(self):
        packed = dat.encode_v2(JPEG, KEY, xor_key=0x37)
        cases = {
            "thiếu khóa V2 (chưa quét bộ nhớ Weixin)": dat.decode(packed),
            "sai khóa": dat.decode(packed, b"fedcba9876543210"),
            "file cụt": dat.decode(packed[:40], KEY),
            "độ dài phần AES quá file": dat.decode(dat.V2_HEADER.pack(dat.V2_MAGIC, 10**6, 0) + packed[15:], KEY),
            "phần XOR quá file": dat.decode(dat.V2_HEADER.pack(dat.V2_MAGIC, 1024, 10**6) + packed[15:], KEY),
            "WEBP V2 không biết byte XOR": dat.decode(dat.encode_v2(WEBP + bytes(2000), KEY, 0x37, 32, 64), KEY),
            "rỗng": dat.decode(b""),
            "khuôn lạ": dat.decode(b"\x01\x02\x03\x04" * 20),
            "chỉ trùng một byte chữ ký": dat.decode(b"\xff\x00\x00\x00" * 20),
        }
        self.assertEqual({name: result for name, result in cases.items() if result is not None}, {})


if __name__ == "__main__":
    unittest.main()
