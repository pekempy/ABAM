"""
Raw ARGB / BGRA surface conversions between PIL images and byte buffers.
"""

from typing import Tuple
from PIL import Image


def pil_to_argb(img: Image.Image) -> Tuple[bytes, int, int]:
    """Converts PIL Image to ARGB byte array (A, R, G, B order)."""
    rgba_img = img.convert("RGBA")
    width, height = rgba_img.size
    raw_rgba = rgba_img.tobytes()

    argb_data = bytearray(width * height * 4)
    for i in range(width * height):
        r = raw_rgba[i * 4]
        g = raw_rgba[i * 4 + 1]
        b = raw_rgba[i * 4 + 2]
        a = raw_rgba[i * 4 + 3]
        # Xbox 360 ARGB32 big endian
        argb_data[i * 4] = a
        argb_data[i * 4 + 1] = r
        argb_data[i * 4 + 2] = g
        argb_data[i * 4 + 3] = b

    return bytes(argb_data), width, height


def argb_to_pil(raw_bgra: bytes, width: int, height: int) -> Image.Image:
    """Converts BGRA byte array returned by AuroraAsset.dll / Xbox 360 decoder to PIL RGBA Image."""
    rgba_data = bytearray(width * height * 4)
    for i in range(min(width * height, len(raw_bgra) // 4)):
        b = raw_bgra[i * 4]
        g = raw_bgra[i * 4 + 1]
        r = raw_bgra[i * 4 + 2]
        a = raw_bgra[i * 4 + 3]
        rgba_data[i * 4] = r
        rgba_data[i * 4 + 1] = g
        rgba_data[i * 4 + 2] = b
        rgba_data[i * 4 + 3] = a

    return Image.frombytes("RGBA", (width, height), bytes(rgba_data))


def raw_argb_to_pil(raw_argb: bytes, width: int, height: int) -> Image.Image:
    """Converts raw ARGB byte array produced by the pure-Python RGBA8 path to PIL RGBA."""
    rgba_data = bytearray(width * height * 4)
    for i in range(min(width * height, len(raw_argb) // 4)):
        a = raw_argb[i * 4]
        r = raw_argb[i * 4 + 1]
        g = raw_argb[i * 4 + 2]
        b = raw_argb[i * 4 + 3]
        rgba_data[i * 4] = r
        rgba_data[i * 4 + 1] = g
        rgba_data[i * 4 + 2] = b
        rgba_data[i * 4 + 3] = a

    return Image.frombytes("RGBA", (width, height), bytes(rgba_data))
