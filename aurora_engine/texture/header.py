"""
Xbox 360 GPU texture fetch-constant header: build & parse.

The 52-byte header embeds a D3D texture fetch constant describing width, height,
format, endianness, tiling and pitch. These layouts were reverse-engineered from
real console-pulled Aurora .asset files.
"""

import struct
from typing import Tuple


def _next_power_of_2(n: int) -> int:
    """Returns the smallest power of 2 >= n."""
    if n <= 0:
        return 1
    n -= 1
    n |= n >> 1
    n |= n >> 2
    n |= n >> 4
    n |= n >> 8
    n |= n >> 16
    return n + 1


def _compute_dxt_pitch(width: int) -> int:
    """Computes pitch_texels for DXT textures matching official Aurora assets.
    Pattern from official assets: pitch = max(128, next_power_of_2(width)),
    except widths already aligned to 32 keep their alignment (e.g. 1280 -> 1280)."""
    if width <= 0:
        return 128
    # For widths that are exact multiples of 32 and >= 128, use width rounded up to 32
    aligned_32 = ((width + 31) // 32) * 32
    npo2 = _next_power_of_2(width)
    # Official pattern: use next-power-of-2 for most widths
    # but for 1280 (already 32-aligned), pitch = 1280 not 2048
    # The rule is: pitch = next multiple of 256 that is >= width, if that's smaller than npo2
    aligned_256 = ((width + 255) // 256) * 256
    pitch = min(npo2, aligned_256) if aligned_256 >= width else npo2
    return max(128, pitch)


def build_xbox360_texture_header(width: int, height: int, is_dxt5: bool = False, is_dxt1: bool = False, is_tiled: bool = False, pitch_texels: int = 0) -> bytes:
    """Builds valid 52-byte Xbox 360 GPU texture fetch header matching official Aurora D3DTexture layout.

    The 9-bit pitch field in fetch_0 encodes pitch_texels / 32 (i.e. pitch_raw = pitch_texels >> 5).
    This was reverse-engineered from official Aurora .asset files pulled from Xbox 360 consoles.
    """
    # The two leading words differ by format in every real sample checked:
    # (3, 1) for DXT5-linear, (0, 0) for DXT1-tiled and raw ARGB8-tiled.
    preamble_a, preamble_b = (0x00000003, 0x00000001) if is_dxt5 else (0, 0)
    header = struct.pack(">IIIIIII", preamble_a, preamble_b, 0, 0, 0, 0xFFFF0000, 0xFFFF0000)

    # TextureFormat values confirmed against real console-pulled .asset files:
    # 0x06 = ARGB8, 0x14 = BC3/DXT5, 0x12 = DXT1/BC1 (was incorrectly 0x52 here,
    # which didn't match either real assets or what the decoder checks for).
    fmt_id = 0x14 if is_dxt5 else (0x12 if is_dxt1 else 0x06)
    endian = 0x01  # Aurora specifically expects endian=1 (8-in-16) for all assets

    effective_pitch = pitch_texels if pitch_texels else _compute_dxt_pitch(width)
    # fetch_0 pitch field: 9 bits at position [30:22], encoding pitch_texels / 32
    pitch_raw = max(1, effective_pitch >> 5)
    pitch_field = (pitch_raw & 0x1FF) << 22
    # Bit 31 = tiled flag, Bit 1 = clamp policy (0x2 for linear textures)
    tiled_bit = 0x80000000 if is_tiled else 0x00000002
    fetch_0 = tiled_bit | pitch_field
    fetch_1 = (endian << 6) | (fmt_id & 0x3F)
    fetch_2 = ((height - 1) << 13) | (width - 1)
    # fetch_3/fetch_5 non-zero values only observed on real DXT5 samples; real
    # DXT1-tiled and ARGB8-tiled samples both have these fields zeroed.
    fetch_3 = 0x00000d10 if is_dxt5 else 0x00000000
    fetch_4 = 0x00000000
    fetch_5 = 0x00000a00 if is_dxt5 else 0x00000000

    fetch = struct.pack(">IIIIII", fetch_0, fetch_1, fetch_2, fetch_3, fetch_4, fetch_5)
    return header + fetch


def parse_xbox360_texture_header(header_data: bytes) -> Tuple[int, int, int, int, bool]:
    """
    Parses 52-byte Xbox 360 texture header.
    Returns (width, height, texture_format, endian, is_tiled).
    """
    if len(header_data) < 52:
        return 0, 0, 0, 0, False

    # Find the signature 0xFFFF0000 0xFFFF0000
    sig = b"\xff\xff\x00\x00\xff\xff\x00\x00"
    sig_pos = header_data.find(sig)
    if sig_pos != -1:
        fetch_start = sig_pos + 8
    else:
        fetch_start = 28 # Fallback to V1 offset

    if fetch_start + 24 > len(header_data):
        return 0, 0, 0, 0, False

    fetch_bytes = header_data[fetch_start:fetch_start+24]
    fetch_0, fetch_1, fetch_2, fetch_3, fetch_4, fetch_5 = struct.unpack(">IIIIII", fetch_bytes)

    is_tiled = bool(fetch_0 & 0x80000000)
    endian = (fetch_1 >> 6) & 0x03
    fmt_id = fetch_1 & 0x3F
    width = (fetch_2 & 0x1FFF) + 1
    height = ((fetch_2 >> 13) & 0x1FFF) + 1

    return width, height, fmt_id, endian, is_tiled


def parse_xbox360_texture_pitch(header_data: bytes) -> int:
    """Returns the base texture pitch in texels from the fetch constant."""
    if len(header_data) < 52:
        return 0

    sig = b"\xff\xff\x00\x00\xff\xff\x00\x00"
    sig_pos = header_data.find(sig)
    if sig_pos != -1:
        fetch_start = sig_pos + 8
    else:
        fetch_start = 28

    if fetch_start + 4 > len(header_data):
        return 0

    fetch_0 = struct.unpack(">I", header_data[fetch_start:fetch_start+4])[0]
    return ((fetch_0 >> 22) & 0x1FF) << 5
