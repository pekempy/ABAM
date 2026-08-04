"""
Pure-Python DXT / BC block decoders (BC1/DXT1 and BC3/DXT5).

Input block buffers must already have the Xbox 360 8-in-16 endian swap undone
(see :func:`aurora_engine.texture.bitops.byte_swap_16`); the swap is applied
once to the whole buffer by the caller, not per-field here.
"""

import struct
from typing import Optional


def _decode_dxt1_blocks(data: bytes, width: int, height: int, source_blocks_w: Optional[int] = None) -> bytes:
    """Decode little-endian PC-layout BC1 blocks. `data` must already have the
    8-in-16 swap undone by the caller (see byte_swap_16)."""
    out = bytearray(width * height * 4)
    w_blocks = (width + 3) // 4
    if source_blocks_w is None:
        source_blocks_w = w_blocks
    h_blocks = (height + 3) // 4
    for y in range(h_blocks):
        for x in range(w_blocks):
            off = (y * source_blocks_w + x) * 8
            if off + 8 > len(data):
                break
            c0, c1 = struct.unpack_from("<HH", data, off)
            r0 = ((c0 >> 11) & 31) * 255 // 31
            g0 = ((c0 >> 5) & 63) * 255 // 63
            b0 = (c0 & 31) * 255 // 31
            r1 = ((c1 >> 11) & 31) * 255 // 31
            g1 = ((c1 >> 5) & 63) * 255 // 63
            b1 = (c1 & 31) * 255 // 31
            colors = [(b0, g0, r0, 255), (b1, g1, r1, 255), (0, 0, 0, 0), (0, 0, 0, 0)]
            if c0 > c1:
                colors[2] = ((2 * b0 + b1) // 3, (2 * g0 + g1) // 3, (2 * r0 + r1) // 3, 255)
                colors[3] = ((b0 + 2 * b1) // 3, (g0 + 2 * g1) // 3, (r0 + 2 * r1) // 3, 255)
            else:
                colors[2] = ((b0 + b1) // 2, (g0 + g1) // 2, (r0 + r1) // 2, 255)
                colors[3] = (0, 0, 0, 0)
            idx_bytes = data[off+4:off+8]
            for py in range(4):
                row = y * 4 + py
                if row >= height:
                    break
                row_idx = idx_bytes[py] if py < len(idx_bytes) else 0
                for px in range(4):
                    col = x * 4 + px
                    if col >= width:
                        break
                    dst_off = (row * width + col) * 4
                    idx = (row_idx >> (px * 2)) & 3
                    out[dst_off:dst_off+4] = bytes(colors[idx])
    return bytes(out)


def _decode_dxt5_blocks(data: bytes, width: int, height: int, source_blocks_w: Optional[int] = None) -> bytes:
    """Decode little-endian PC-layout BC3 blocks. `data` must already have the
    8-in-16 swap undone by the caller (see byte_swap_16)."""
    out = bytearray(width * height * 4)
    w_blocks = (width + 3) // 4
    if source_blocks_w is None:
        source_blocks_w = w_blocks
    h_blocks = (height + 3) // 4
    for y in range(h_blocks):
        for x in range(w_blocks):
            off = (y * source_blocks_w + x) * 16
            if off + 16 > len(data):
                break
            a0, a1 = data[off], data[off + 1]
            a_idx_bytes = data[off + 2:off + 8]
            alphas = [a0, a1, 0, 0, 0, 0, 0, 0]
            if a0 > a1:
                for i in range(2, 8):
                    alphas[i] = ((8 - i) * a0 + (i - 1) * a1) // 7
            else:
                for i in range(2, 6):
                    alphas[i] = ((6 - i) * a0 + (i - 1) * a1) // 5
                alphas[6], alphas[7] = 0, 255
            a_indices = int.from_bytes(a_idx_bytes, "little")

            c0, c1 = struct.unpack_from("<HH", data, off + 8)
            r0 = ((c0 >> 11) & 31) * 255 // 31
            g0 = ((c0 >> 5) & 63) * 255 // 63
            b0 = (c0 & 31) * 255 // 31
            r1 = ((c1 >> 11) & 31) * 255 // 31
            g1 = ((c1 >> 5) & 63) * 255 // 63
            b1 = (c1 & 31) * 255 // 31
            colors = [
                (b0, g0, r0),
                (b1, g1, r1),
                ((2 * b0 + b1) // 3, (2 * g0 + g1) // 3, (2 * r0 + r1) // 3),
                ((b0 + 2 * b1) // 3, (g0 + 2 * g1) // 3, (r0 + 2 * r1) // 3),
            ]
            c_idx_bytes = data[off + 12:off + 16]
            for py in range(4):
                row = y * 4 + py
                if row >= height:
                    break
                row_idx = c_idx_bytes[py] if py < len(c_idx_bytes) else 0
                for px in range(4):
                    col = x * 4 + px
                    if col >= width:
                        break
                    pixel_idx = py * 4 + px
                    a_val = alphas[(a_indices >> (pixel_idx * 3)) & 7]
                    c = colors[(row_idx >> (px * 2)) & 3]
                    dst_off = (row * width + col) * 4
                    out[dst_off:dst_off + 4] = bytes([c[0], c[1], c[2], a_val])
    return bytes(out)
