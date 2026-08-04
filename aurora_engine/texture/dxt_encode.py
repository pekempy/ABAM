"""
Pure-Python DXT / BC block encoders (BC1/DXT1 and BC3/DXT5).

Endpoint fitting uses PCA (principal-axis) selection + nearest-palette
assignment to match production encoders (squish/stb_dxt) and the reference
AuroraAsset.dll far better than a naive per-channel bounding box.
"""

import struct
from typing import Tuple
from PIL import Image

from aurora_engine.texture.bitops import byte_swap_16


def _dequant_565(c565: int) -> Tuple[int, int, int]:
    """Mirrors the decoder's RGB565 -> RGB888 expansion so encoder-side error
    minimization matches what the console will actually display."""
    r = ((c565 >> 11) & 31) * 255 // 31
    g = ((c565 >> 5) & 63) * 255 // 63
    b = (c565 & 31) * 255 // 31
    return r, g, b


def _bump_565(c565: int, increase: bool) -> int:
    """Nudge a packed RGB565 color one step within a single channel's own field,
    moving the packed integer strictly up (increase=True) or down, without
    carrying across field boundaries.

    A naive c565 +/- 1 can carry between fields and corrupt an unrelated
    channel (e.g. 0xFFDF + 1 rolls blue 31->0 and carries into green), which
    turned near-white pixels yellow on the c0==c1 collision path.
    """
    r5 = (c565 >> 11) & 0x1F
    g6 = (c565 >> 5) & 0x3F
    b5 = c565 & 0x1F
    if increase:
        if b5 < 31:
            b5 += 1
        elif g6 < 63:
            g6 += 1
        elif r5 < 31:
            r5 += 1
    else:
        if b5 > 0:
            b5 -= 1
        elif g6 > 0:
            g6 -= 1
        elif r5 > 0:
            r5 -= 1
    return (r5 << 11) | (g6 << 5) | b5


def _fit_dxt_block(r_vals: list, g_vals: list, b_vals: list) -> Tuple[Tuple[int, int, int], Tuple[int, int, int], list]:
    """Fit a DXT 4-color block to 16 RGB samples via PCA endpoint selection plus
    nearest-palette assignment.

    A per-channel bounding box picks corners of the RGB cube that rarely occur
    in the block, causing banding/ringing at sharp edges. Fitting along the
    block's dominant axis of color variation (as squish/stb_dxt do) tracks the
    reference output far more closely. Returns (c0_rgb, c1_rgb, indices) where
    indices[i] in 0..3 selects the palette entry (0=c0, 1=c1, 2=2/3 c0 + 1/3
    c1, 3=1/3 c0 + 2/3 c1).
    """
    n = len(r_vals)
    mr = sum(r_vals) / n
    mg = sum(g_vals) / n
    mb = sum(b_vals) / n

    cxx = cxy = cxz = cyy = cyz = czz = 0.0
    for r, g, b in zip(r_vals, g_vals, b_vals):
        dr, dg, db = r - mr, g - mg, b - mb
        cxx += dr * dr; cxy += dr * dg; cxz += dr * db
        cyy += dg * dg; cyz += dg * db; czz += db * db

    # Power iteration to find the dominant eigenvector of the 3x3 covariance
    # matrix (the axis the block's colors vary along the most).
    vx = max(r_vals) - min(r_vals)
    vy = max(g_vals) - min(g_vals)
    vz = max(b_vals) - min(b_vals)
    if vx == vy == vz == 0:
        # Flat block: every pixel is identical, endpoints don't matter.
        rgb = (int(mr), int(mg), int(mb))
        return rgb, rgb, [0] * n
    for _ in range(6):
        nx = cxx * vx + cxy * vy + cxz * vz
        ny = cxy * vx + cyy * vy + cyz * vz
        nz = cxz * vx + cyz * vy + czz * vz
        norm = (nx * nx + ny * ny + nz * nz) ** 0.5
        if norm < 1e-6:
            break
        vx, vy, vz = nx / norm, ny / norm, nz / norm

    tmin = tmax = None
    for r, g, b in zip(r_vals, g_vals, b_vals):
        t = (r - mr) * vx + (g - mg) * vy + (b - mb) * vz
        if tmin is None or t < tmin:
            tmin = t
        if tmax is None or t > tmax:
            tmax = t

    def clamp255(v):
        return max(0, min(255, round(v)))

    c_hi = (clamp255(mr + vx * tmax), clamp255(mg + vy * tmax), clamp255(mb + vz * tmax))
    c_lo = (clamp255(mr + vx * tmin), clamp255(mg + vy * tmin), clamp255(mb + vz * tmin))

    def rgb565(r, g, b):
        return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

    c0 = rgb565(*c_hi)
    c1 = rgb565(*c_lo)
    if c0 == c1:
        return c_hi, c_lo, [0] * n

    # Build the 4-entry palette with the same dequantization the decoder uses,
    # then assign each pixel to its nearest entry by Euclidean distance.
    r0, g0, b0 = _dequant_565(c0)
    r1, g1, b1 = _dequant_565(c1)
    palette = [
        (r0, g0, b0),
        (r1, g1, b1),
        ((2 * r0 + r1) // 3, (2 * g0 + g1) // 3, (2 * b0 + b1) // 3),
        ((r0 + 2 * r1) // 3, (g0 + 2 * g1) // 3, (b0 + 2 * b1) // 3),
    ]

    indices = []
    for r, g, b in zip(r_vals, g_vals, b_vals):
        best_idx, best_dist = 0, None
        for idx, (pr, pg, pb) in enumerate(palette):
            dr, dg, db = r - pr, g - pg, b - pb
            dist = dr * dr + dg * dg + db * db
            if best_dist is None or dist < best_dist:
                best_dist, best_idx = dist, idx
        indices.append(best_idx)

    return c_hi, c_lo, indices


def rgb565(r, g, b):
    return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)


def pil_to_dxt5(img: Image.Image, target_pitch_texels: int = 0, target_height: int = 0) -> Tuple[bytes, int, int]:
    """Encodes PIL image to native Xbox 360 DXT5 (BC3) linear block payload matching official Aurora assets."""
    w, h = img.size
    rgba_img = img.convert("RGBA")
    rgba_data = rgba_img.tobytes()

    w_blocks = (w + 3) // 4
    h_blocks = (h + 3) // 4

    pitch_blocks = max((target_pitch_texels + 3) // 4, w_blocks) if target_pitch_texels else w_blocks
    eff_h_blocks = max((target_height + 3) // 4, h_blocks) if target_height else h_blocks

    payload = bytearray(pitch_blocks * eff_h_blocks * 16)
    stride = w * 4

    def rgb565(r, g, b):
        return ((r >> 3) << 11) | ((g >> 2) << 5) | (b >> 3)

    for b_y in range(h_blocks):
        y = b_y * 4
        for b_x in range(w_blocks):
            x = b_x * 4
            block_idx = (b_y * pitch_blocks + b_x) * 16

            r_vals, g_vals, b_vals, a_vals = [], [], [], []
            for py in range(4):
                iy = min(y + py, h - 1)
                row_off = iy * stride
                for px in range(4):
                    ix = min(x + px, w - 1)
                    off = row_off + ix * 4
                    r_vals.append(rgba_data[off])
                    g_vals.append(rgba_data[off + 1])
                    b_vals.append(rgba_data[off + 2])
                    a_vals.append(rgba_data[off + 3])

            # Alpha block (8 bytes)
            min_a, max_a = min(a_vals), max(a_vals)
            if min_a == max_a:
                payload[block_idx] = max_a
                payload[block_idx + 1] = min_a
            else:
                a0, a1 = max_a, min_a
                payload[block_idx] = a0
                payload[block_idx + 1] = a1
                range_a = a0 - a1
                a_idx_int = 0
                for i, a_val in enumerate(a_vals):
                    idx = round((a0 - a_val) * 7 / range_a)
                    idx = max(0, min(7, idx))
                    code = 0 if idx == 0 else (1 if idx == 7 else idx + 1)
                    a_idx_int |= (code << (i * 3))
                payload[block_idx + 2 : block_idx + 8] = a_idx_int.to_bytes(6, "little")

            # Color block (8 bytes): PCA endpoint fit (see _fit_dxt_block).
            c0_rgb, c1_rgb, indices = _fit_dxt_block(r_vals, g_vals, b_vals)
            c0 = rgb565(*c0_rgb)
            c1 = rgb565(*c1_rgb)
            if c0 == c1:
                if c0 > 0:
                    c1 = _bump_565(c0, increase=False)
                else:
                    c0 = _bump_565(c1, increase=True)
                # Endpoints collapsed to one 565 value; every pixel maps to 0.
                indices = [0] * 16

            # Plain little-endian PC layout; the whole buffer gets the 8-in-16
            # swap applied once at the end (see byte_swap_16 below).
            struct.pack_into("<HH", payload, block_idx + 8, c0, c1)

            c_idx_bytes = bytearray(4)
            for py in range(4):
                row_idx = 0
                for px in range(4):
                    row_idx |= (indices[py * 4 + px] << (px * 2))
                c_idx_bytes[py] = row_idx

            payload[block_idx + 12 : block_idx + 16] = c_idx_bytes

    return byte_swap_16(bytes(payload)), w, h


def pil_to_dxt1(img: Image.Image) -> Tuple[bytes, int, int]:
    width, height = img.size
    aligned_w = (width + 3) & ~3
    aligned_h = (height + 3) & ~3
    if width != aligned_w or height != aligned_h:
        try:
            resample_filter = Image.Resampling.BILINEAR
        except AttributeError:
            resample_filter = Image.BILINEAR
        img = img.resize((aligned_w, aligned_h), resample_filter)
        width, height = aligned_w, aligned_h

    rgb_data = img.convert("RGB").tobytes()
    blocks = bytearray((width // 4) * (height // 4) * 8)

    stride = width * 3
    out_idx = 0
    for y in range(0, height, 4):
        for x in range(0, width, 4):
            min_r, min_g, min_b = 255, 255, 255
            max_r, max_g, max_b = 0, 0, 0

            # Find min and max colors
            for py in range(4):
                off = (y + py) * stride + x * 3
                for px in range(4):
                    r, g, b = rgb_data[off], rgb_data[off+1], rgb_data[off+2]
                    if r < min_r: min_r = r
                    if g < min_g: min_g = g
                    if b < min_b: min_b = b
                    if r > max_r: max_r = r
                    if g > max_g: max_g = g
                    if b > max_b: max_b = b
                    off += 3

            c0 = rgb565(max_r, max_g, max_b)
            c1 = rgb565(min_r, min_g, min_b)

            # DXT1 rules: c0 > c1 means opaque block.
            if c0 <= c1:
                if c0 == c1:
                    if c1 < 65535: c0 = c1 + 1
                    else: c1 = c0 - 1
                else:
                    c0, c1 = c1, c0

            struct.pack_into(">HH", blocks, out_idx, c0, c1)

            idx_word = 0
            bit_pos = 0
            dir_r = max_r - min_r
            dir_g = max_g - min_g
            dir_b = max_b - min_b
            dir_sq = dir_r**2 + dir_g**2 + dir_b**2
            if dir_sq == 0: dir_sq = 1

            for py in range(4):
                off = (y + py) * stride + x * 3
                for px in range(4):
                    r, g, b = rgb_data[off], rgb_data[off+1], rgb_data[off+2]
                    dot = (max_r - r) * dir_r + (max_g - g) * dir_g + (max_b - b) * dir_b
                    ratio = (dot * 3 + (dir_sq >> 1)) // dir_sq
                    if ratio <= 0: idx = 0
                    elif ratio == 1: idx = 2
                    elif ratio == 2: idx = 3
                    else: idx = 1

                    idx_word |= (idx << bit_pos)
                    bit_pos += 2
                    off += 3

            struct.pack_into("<I", blocks, out_idx + 4, idx_word)
            out_idx += 8

    return bytes(blocks), width, height


def pil_to_dxt1_blocks(img: Image.Image, w_blocks: int, h_blocks: int) -> bytes:
    """Encodes a PIL image to a tight (no pitch padding) grid of w_blocks x h_blocks
    DXT1/BC1 blocks using the same PCA endpoint fit as pil_to_dxt5, forcing opaque
    4-color mode (c0 > c1) since Aurora artwork never uses DXT1's punch-through
    alpha. Used for the tiled DXT1 path, where tile_xbox360_data handles the 32x32
    tile padding itself."""
    w, h = img.size
    rgba_data = img.convert("RGBA").tobytes()
    stride = w * 4
    blocks = bytearray(w_blocks * h_blocks * 8)

    for b_y in range(h_blocks):
        y = b_y * 4
        for b_x in range(w_blocks):
            x = b_x * 4
            block_idx = (b_y * w_blocks + b_x) * 8

            r_vals, g_vals, b_vals = [], [], []
            for py in range(4):
                iy = min(y + py, h - 1)
                row_off = iy * stride
                for px in range(4):
                    ix = min(x + px, w - 1)
                    off = row_off + ix * 4
                    r_vals.append(rgba_data[off])
                    g_vals.append(rgba_data[off + 1])
                    b_vals.append(rgba_data[off + 2])

            c_hi, c_lo, indices = _fit_dxt_block(r_vals, g_vals, b_vals)
            c0 = rgb565(*c_hi)
            c1 = rgb565(*c_lo)
            # DXT1 rules: c0 > c1 selects opaque 4-color interpolation. Aurora
            # artwork is always opaque, so force that mode rather than the
            # 3-color + transparent mode (c0 <= c1).
            if c0 <= c1:
                if c0 == c1:
                    if c1 > 0:
                        c1 = _bump_565(c1, increase=False)
                    else:
                        c0 = _bump_565(c0, increase=True)
                else:
                    c0, c1 = c1, c0
                    indices = [1 if i == 0 else (0 if i == 1 else i) for i in indices]

            # Plain little-endian PC layout; swapped once at the end (see pil_to_dxt5).
            struct.pack_into("<HH", blocks, block_idx, c0, c1)
            idx_word = 0
            for i, idx in enumerate(indices):
                idx_word |= (idx << (i * 2))
            struct.pack_into("<I", blocks, block_idx + 4, idx_word)

    return byte_swap_16(bytes(blocks))
