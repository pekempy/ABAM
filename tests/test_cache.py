import io
import os
import struct
import unittest
import shutil
import tempfile
from unittest.mock import patch
from PIL import Image

import aurora_engine.cache as cache
from aurora_engine.texture.decode import convert_asset_to_png_bytes
from aurora_engine.texture.dxt_decode import _decode_dxt1_blocks, _decode_dxt5_blocks
from aurora_engine.texture.argb import raw_argb_to_pil
from aurora_engine.texture.tiling import tile_xbox360_data

class TestCache(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.mkdtemp()
        self.patcher = patch('aurora_engine.cache.CACHE_BASE_DIR', self.temp_dir)
        self.patcher.start()

    def tearDown(self):
        self.patcher.stop()
        shutil.rmtree(self.temp_dir, ignore_errors=True)

    def test_get_cache_dir_for_game(self):
        title_id = "5345080E"
        expected_dir = os.path.join(self.temp_dir, title_id)
        res = cache.get_cache_dir_for_game(title_id)
        self.assertEqual(res, expected_dir)
        self.assertTrue(os.path.exists(res))

    def test_get_cache_dir_for_game_formatting(self):
        title_id = "   abc  "
        expected_dir = os.path.join(self.temp_dir, "00000ABC")
        res = cache.get_cache_dir_for_game(title_id)
        self.assertEqual(res, expected_dir)

    def test_get_cache_dir_for_game_preserves_folder_path_identity(self):
        folder_path = "545407F2_0000001C"
        expected_dir = os.path.join(self.temp_dir, folder_path)
        res = cache.get_cache_dir_for_game(folder_path)
        self.assertEqual(res, expected_dir)

    def test_clear_cache(self):
        # Create some temp files in the cache dir
        game_dir = cache.get_cache_dir_for_game("12345678")
        temp_file = os.path.join(game_dir, "test_file.png")
        with open(temp_file, "w") as f:
            f.write("test")
            
        self.assertTrue(os.path.exists(temp_file))
        cleared_count = cache.clear_cache()
        self.assertEqual(cleared_count, 1)
        self.assertFalse(os.path.exists(temp_file))

    def test_convert_asset_to_png_bytes_decodes_linear_dxt5_with_padded_pitch(self):
        width = 4
        height = 8
        pitch_texels = 32
        source_blocks_w = pitch_texels // 4

        header = struct.pack(
            ">IIIIIII",
            0,
            0,
            0,
            0,
            0,
            0xFFFF0000,
            0xFFFF0000,
        ) + struct.pack(
            ">IIIIII",
            ((pitch_texels >> 5) << 22) | 0x00000002,
            0x00000054,
            ((height - 1) << 13) | (width - 1),
            0,
            0,
            0,
        )

        def make_dxt5_block(color_565: int) -> bytes:
            return (
                bytes([255, 255])
                + b"\x00\x00\x00\x00\x00\x00"
                + struct.pack(">HH", color_565, 0)
                + b"\x00\x00\x00\x00"
            )

        white_block = make_dxt5_block(0xFFFF)
        black_block = make_dxt5_block(0x0000)
        padding_block = make_dxt5_block(0xF800)

        row0 = white_block + (padding_block * (source_blocks_w - 1))
        row1 = black_block + (padding_block * (source_blocks_w - 1))
        video_data = row0 + row1

        fresh_png = convert_asset_to_png_bytes(header, video_data)

        self.assertIsNotNone(fresh_png)

        img = Image.open(io.BytesIO(fresh_png)).convert("RGBA")
        self.assertEqual(img.getpixel((0, 0)), (255, 255, 255, 255))
        self.assertEqual(img.getpixel((0, height - 1)), (0, 0, 0, 255))

    def test_raw_argb_to_pil_preserves_channel_order(self):
        img = raw_argb_to_pil(bytes([255, 10, 20, 30]), 1, 1)
        self.assertEqual(img.getpixel((0, 0)), (10, 20, 30, 255))

    def test_convert_asset_to_png_bytes_decodes_fmt6_tiled_argb_surface(self):
        width = 32
        height = 32

        argb = bytearray()
        for y in range(height):
            for x in range(width):
                if x < 16:
                    argb.extend((255, 255, 0, 0))
                else:
                    argb.extend((255, 0, 255, 0))

        video_data = tile_xbox360_data(bytes(argb), width, height, 4)
        header = struct.pack(
            ">IIIIIII",
            0,
            0,
            0,
            0,
            0,
            0xFFFF0000,
            0xFFFF0000,
        ) + struct.pack(
            ">IIIIII",
            0x08000002,
            0x00000046,
            ((height - 1) << 13) | (width - 1),
            0,
            0,
            0,
        )

        fresh_png = convert_asset_to_png_bytes(header, video_data)

        self.assertIsNotNone(fresh_png)

        img = Image.open(io.BytesIO(fresh_png)).convert("RGBA")
        self.assertEqual(img.getpixel((4, 4)), (255, 0, 0, 255))
        self.assertEqual(img.getpixel((28, 4)), (0, 255, 0, 255))

    def test_decode_dxt1_blocks_handles_partial_blocks(self):
        block = struct.pack("<HH", 0xFFFF, 0x0000) + b"\x0C\x03\x00\x00"

        decoded = _decode_dxt1_blocks(block, 2, 2)

        self.assertNotEqual(decoded[:4], decoded[4:8])

    def test_decode_dxt5_blocks_handles_partial_blocks(self):
        block = bytes([0x00, 0xFF]) + b"\x01\x00\x00\x00\x00\x00" + struct.pack("<HH", 0xFFFF, 0x0000) + b"\x0C\x03\x00\x00"

        decoded = _decode_dxt5_blocks(block, 2, 2)

        self.assertNotEqual(decoded[:4], decoded[4:8])

if __name__ == "__main__":
    unittest.main()
