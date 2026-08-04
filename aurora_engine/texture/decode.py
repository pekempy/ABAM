"""
High-level decode orchestrator: Aurora asset (header + video) -> PIL image / PNG.
"""

import ctypes
import io
import struct
from typing import Optional
from PIL import Image

from aurora_engine.texture import native
from aurora_engine.texture.bitops import byte_swap_16
from aurora_engine.texture.tiling import untile_xbox360_data
from aurora_engine.texture.header import (
    parse_xbox360_texture_header,
    parse_xbox360_texture_pitch,
)
from aurora_engine.texture.dxt_decode import _decode_dxt1_blocks, _decode_dxt5_blocks
from aurora_engine.texture.argb import argb_to_pil, raw_argb_to_pil


def convert_asset_to_pil(header_data: bytes, video_data: bytes) -> Optional[Image.Image]:
    """Convert asset entry data (header + video) to a PIL RGBA image."""
    dll = native.get_dll()

    if not header_data or not video_data:
        return None

    # header_data and video_data arrive separately, but RXEA payloads are
    # shifted. Stitch them back together and locate the real boundary via the
    # RXEA payload size so headers larger than 52 bytes still parse.
    full_data = header_data + video_data
    if full_data.startswith(b"RXEA"):
        if len(full_data) > 12:
            payload_size = struct.unpack(">I", full_data[8:12])[0]
            header_size = len(full_data) - payload_size
            header_data = full_data[:header_size]
            video_data = full_data[header_size:]
            width, height, fmt_id, endian, is_tiled = parse_xbox360_texture_header(header_data)
            pitch_texels = parse_xbox360_texture_pitch(header_data)

    # Try Windows DLL first if available
    if dll:
        try:
            hd = ctypes.cast(ctypes.c_char_p(header_data), ctypes.c_void_p)
            vd = ctypes.cast(ctypes.c_char_p(video_data), ctypes.c_void_p)

            image_len = ctypes.c_int(0)
            width = ctypes.c_int(0)
            height = ctypes.c_int(0)

            res1 = dll.ConvertAssetToImage(
                hd, len(header_data), vd, len(video_data),
                None, ctypes.byref(image_len), ctypes.byref(width), ctypes.byref(height)
            )

            if res1 == 1 and image_len.value > 0 and width.value > 0 and height.value > 0:
                image_buf = ctypes.create_string_buffer(image_len.value)
                res2 = dll.ConvertAssetToImage(
                    hd, len(header_data), vd, len(video_data),
                    image_buf, ctypes.byref(image_len), ctypes.byref(width), ctypes.byref(height)
                )
                if res2 == 1:
                    return argb_to_pil(image_buf.raw[:image_len.value], width.value, height.value)
        except Exception as e:
            print(f"DLL decode failed, switching to Pure Python fallback: {e}")

    # Pure-Python fallback (all platforms)
    width, height, fmt_id, endian, is_tiled = parse_xbox360_texture_header(header_data)
    pitch_texels = parse_xbox360_texture_pitch(header_data)
    if width <= 0 or height <= 0:
        return None

    # Block payloads are stored as byte-swapped 16-bit words (the reference
    # DLL's swap-mode 0x20001, applied uniformly). Undo it once before parsing
    # with plain PC/BC semantics.
    if fmt_id == 0x12: # BC1 / DXT1
        width_blocks = (width + 3) // 4
        height_blocks = (height + 3) // 4
        source_blocks_w = width_blocks
        if is_tiled:
            linear_blocks = untile_xbox360_data(video_data, width_blocks, height_blocks, 8)
        else:
            linear_blocks = video_data
            if pitch_texels:
                source_blocks_w = max((pitch_texels + 3) // 4, width_blocks)
        linear_data = _decode_dxt1_blocks(byte_swap_16(linear_blocks), width, height, source_blocks_w=source_blocks_w)
    elif fmt_id == 0x14: # BC3 / DXT5
        width_blocks = (width + 3) // 4
        height_blocks = (height + 3) // 4
        source_blocks_w = width_blocks
        if is_tiled:
            linear_blocks = untile_xbox360_data(video_data, width_blocks, height_blocks, 16)
        else:
            linear_blocks = video_data
            if pitch_texels:
                source_blocks_w = max((pitch_texels + 3) // 4, width_blocks)
        linear_data = _decode_dxt5_blocks(byte_swap_16(linear_blocks), width, height, source_blocks_w=source_blocks_w)
    else:
        # Aurora fmt 6 surfaces are 32x32-tiled ARGB even when the tiled bit is
        # clear in the fetch constant; the 8-in-16 swap would corrupt the rows.
        linear_data = untile_xbox360_data(video_data, width, height, 4)
        return raw_argb_to_pil(linear_data, width, height)

    return argb_to_pil(linear_data, width, height)


def convert_asset_to_png_bytes(header_data: bytes, video_data: bytes) -> Optional[bytes]:
    """Converts asset entry data to PNG format bytes."""
    pil_img = convert_asset_to_pil(header_data, video_data)
    if pil_img:
        buf = io.BytesIO()
        pil_img.save(buf, format="PNG")
        return buf.getvalue()
    return None


# Public API aliases.
decode_asset_to_image = convert_asset_to_pil
decode_asset_to_png = convert_asset_to_png_bytes
