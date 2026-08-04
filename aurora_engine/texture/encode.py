"""
High-level encode orchestrator: image file bytes -> Aurora asset (header + video).
"""

import ctypes
import io
from typing import Optional, Tuple
from PIL import Image

from aurora_engine.texture import native
from aurora_engine.texture.argb import pil_to_argb
from aurora_engine.texture.tiling import tile_xbox360_data
from aurora_engine.texture.header import build_xbox360_texture_header, _compute_dxt_pitch
from aurora_engine.texture.dxt_encode import pil_to_dxt5


def convert_image_bytes_to_asset(
    img_bytes: bytes, compress: bool = True, existing_header: Optional[bytes] = None
) -> Tuple[bytes, bytes, int, int]:
    """
    Convert image file bytes (PNG/JPG/WEBP) to Aurora asset format.

    Produces DXT5-linear when compress=True, else raw ARGB8-tiled -- the two
    formats the reference AuroraAsset.dll emits (DXT4_5 0x1a200054 / raw
    8_8_8_8 0x18280086). It never reproduces DXT1-tiled: re-encoding as
    DXT1-tiled renders as a barcode on real hardware. ``existing_header`` is
    accepted for API compatibility but no longer affects the output format.
    """
    dll = native.get_dll()

    img = Image.open(io.BytesIO(img_bytes))
    width, height = img.size

    # Try Windows DLL first if available
    if dll:
        try:
            argb_bytes, w, h = pil_to_argb(img)
            header_len = ctypes.c_int(0)
            video_len = ctypes.c_int(0)

            pd = ctypes.cast(ctypes.c_char_p(argb_bytes), ctypes.c_void_p)
            res1 = dll.ConvertImageToAsset(
                pd, len(argb_bytes), width, height, 1 if compress else 0,
                None, ctypes.byref(header_len), None, ctypes.byref(video_len)
            )

            if res1 == 1 and header_len.value > 0 and video_len.value > 0:
                header_buf = ctypes.create_string_buffer(header_len.value)
                video_buf = ctypes.create_string_buffer(video_len.value)

                res2 = dll.ConvertImageToAsset(
                    pd, len(argb_bytes), width, height, 1 if compress else 0,
                    header_buf, ctypes.byref(header_len), video_buf, ctypes.byref(video_len)
                )
                if res2 == 1:
                    return header_buf.raw[:header_len.value], video_buf.raw[:video_len.value], width, height
        except Exception as e:
            print(f"DLL conversion failed, switching to Pure Python fallback: {e}")

    # Pure-Python fallback (all platforms)
    if not compress:
        # Raw ARGB8. Real fmt-6 samples are physically 32x32-tiled but leave the
        # header's tiled bit clear; the decoder always untiles fmt 6 regardless,
        # so match that convention when writing.
        argb_bytes, w, h = pil_to_argb(img)
        tiled_payload = tile_xbox360_data(argb_bytes, w, h, 4)
        header_bytes = build_xbox360_texture_header(w, h, is_tiled=False)
        return header_bytes, tiled_payload, w, h

    # DXT5 (BC3) linear-pitch: what the reference DLL emits for compressed
    # output and the most common format across real console assets.
    pitch_texels = _compute_dxt_pitch(width)
    # Official Aurora assets pad payload height to next multiple of 128 texels.
    padded_height = ((height + 127) // 128) * 128
    dxt5_payload, w, h = pil_to_dxt5(img, target_pitch_texels=pitch_texels, target_height=padded_height)
    header_bytes = build_xbox360_texture_header(w, h, is_dxt5=True, is_dxt1=False, is_tiled=False, pitch_texels=pitch_texels)

    return header_bytes, dxt5_payload, w, h


# Public API alias.
encode_image = convert_image_bytes_to_asset
