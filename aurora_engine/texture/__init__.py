"""
Aurora Texture Codec package.

A modular, pure-Python cross-platform Xbox 360 texture codec (with an
optional native AuroraAsset.dll fast path on Windows), split into focused
submodules:

    bitops      -- byte-order helpers (8-in-16 endian swap)
    native      -- optional AuroraAsset.dll backend loader
    tiling      -- Xbox 360 2D address swizzle (tile / untile)
    header      -- 52-byte texture fetch-constant build / parse
    dxt_encode  -- BC1/DXT1 & BC3/DXT5 block encoders
    dxt_decode  -- BC1/DXT1 & BC3/DXT5 block decoders
    argb        -- raw ARGB / BGRA surface conversions
    encode      -- high-level image-bytes -> asset orchestrator
    decode      -- high-level asset -> image / PNG orchestrator

Public API (stable, re-exported here):
    encode_image / convert_image_bytes_to_asset
    decode_image / convert_asset_to_pil
    decode_image_to_png / convert_asset_to_png_bytes
"""

from aurora_engine.texture.bitops import byte_swap_16
from aurora_engine.texture.native import get_dll, _init_dll
from aurora_engine.texture.tiling import (
    xg_address_2d_tiled_offset,
    untile_xbox360_data,
    tile_xbox360_data,
)
from aurora_engine.texture.header import (
    build_xbox360_texture_header,
    parse_xbox360_texture_header,
    parse_xbox360_texture_pitch,
    _next_power_of_2,
    _compute_dxt_pitch,
)
from aurora_engine.texture.dxt_encode import (
    rgb565,
    pil_to_dxt5,
    pil_to_dxt1,
    pil_to_dxt1_blocks,
    _dequant_565,
    _bump_565,
    _fit_dxt_block,
)
from aurora_engine.texture.dxt_decode import (
    _decode_dxt1_blocks,
    _decode_dxt5_blocks,
)
from aurora_engine.texture.argb import (
    pil_to_argb,
    argb_to_pil,
    raw_argb_to_pil,
)
from aurora_engine.texture.encode import (
    convert_image_bytes_to_asset,
    encode_image,
)
from aurora_engine.texture.decode import (
    convert_asset_to_pil,
    convert_asset_to_png_bytes,
    decode_asset_to_image,
    decode_asset_to_png,
)

# Public API aliases.
decode_image = convert_asset_to_pil
decode_image_to_png = convert_asset_to_png_bytes

__all__ = [
    # High-level public API
    "encode_image",
    "decode_image",
    "decode_image_to_png",
    "convert_image_bytes_to_asset",
    "convert_asset_to_pil",
    "convert_asset_to_png_bytes",
    "decode_asset_to_image",
    "decode_asset_to_png",
    # Native backend
    "get_dll",
    # Tiling
    "xg_address_2d_tiled_offset",
    "untile_xbox360_data",
    "tile_xbox360_data",
    # Header
    "build_xbox360_texture_header",
    "parse_xbox360_texture_header",
    "parse_xbox360_texture_pitch",
    # DXT encode
    "rgb565",
    "pil_to_dxt5",
    "pil_to_dxt1",
    "pil_to_dxt1_blocks",
    # DXT decode
    "byte_swap_16",
    # ARGB
    "pil_to_argb",
    "argb_to_pil",
    "raw_argb_to_pil",
]
