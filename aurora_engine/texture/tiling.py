"""
Xbox 360 GPU (Xenos) 2D texture tiling / untiling.

The console stores textures in a 2D address-swizzled (macro/micro tiled) layout.
These helpers convert between that swizzled layout and a plain linear one.
"""


def xg_address_2d_tiled_offset(x: int, y: int, width_in_blocks: int, log_bpp: int) -> int:
    """
    Xbox 360 GPU (Xenos) 2D Tiled Address Swizzle Formula.
    Computes exact memory offset for block coordinate (x, y).
    """
    aligned_w = (width_in_blocks + 31) & ~31

    tile_h_bits = 7 - log_bpp
    tile_h = 1 << tile_h_bits

    macro_x = x >> 5
    macro_y = y >> tile_h_bits
    macro_stride = aligned_w >> 5
    macro_offset = (macro_y * macro_stride + macro_x) << 12

    rx = x & 31
    ry = y & (tile_h - 1)

    in_tile = 0
    out_bit = 0
    for bit in range(5):
        in_tile |= ((rx >> bit) & 1) << out_bit
        out_bit += 1
        if bit < tile_h_bits:
            in_tile |= ((ry >> bit) & 1) << out_bit
            out_bit += 1

    return macro_offset + (in_tile << log_bpp)


def untile_xbox360_data(data: bytes, width: int, height: int, bytes_per_pixel: int) -> bytes:
    """Untiles Xbox 360 2D swizzled pixel/block payload to linear layout."""
    aligned_w = (width + 31) & ~31
    aligned_h = (height + 31) & ~31
    log_bpp = 2 if bytes_per_pixel == 4 else (3 if bytes_per_pixel == 8 else (4 if bytes_per_pixel == 16 else 0))

    out = bytearray(width * height * bytes_per_pixel)
    data_len = len(data)

    for y in range(height):
        for x in range(width):
            src_offset = xg_address_2d_tiled_offset(x, y, aligned_w, log_bpp)
            dst_offset = (y * width + x) * bytes_per_pixel
            if src_offset + bytes_per_pixel <= data_len:
                out[dst_offset : dst_offset + bytes_per_pixel] = data[src_offset : src_offset + bytes_per_pixel]

    return bytes(out)


def tile_xbox360_data(data: bytes, width: int, height: int, bytes_per_pixel: int) -> bytes:
    """Tiles linear pixel/block payload into Xbox 360 2D swizzled layout."""
    aligned_w = (width + 31) & ~31
    aligned_h = (height + 31) & ~31
    log_bpp = 2 if bytes_per_pixel == 4 else (3 if bytes_per_pixel == 8 else (4 if bytes_per_pixel == 16 else 0))

    total_tiled_bytes = aligned_w * aligned_h * bytes_per_pixel
    out = bytearray(total_tiled_bytes)

    for y in range(height):
        for x in range(width):
            src_offset = (y * width + x) * bytes_per_pixel
            dst_offset = xg_address_2d_tiled_offset(x, y, aligned_w, log_bpp)
            if dst_offset + bytes_per_pixel <= total_tiled_bytes:
                out[dst_offset : dst_offset + bytes_per_pixel] = data[src_offset : src_offset + bytes_per_pixel]

    return bytes(out)
