"""
Backwards-compatibility shim.

The Aurora texture codec now lives in the modular :mod:`aurora_engine.texture`
sub-package. This module re-exports the same names it historically exposed so
existing imports (``from aurora_engine.texture_converter import ...``) keep
working. New code should import from :mod:`aurora_engine.texture` directly.
"""

from aurora_engine.texture.bitops import byte_swap_16
from aurora_engine.texture.native import _init_dll, get_dll
from aurora_engine.texture.tiling import (
    xg_address_2d_tiled_offset,
    untile_xbox360_data,
    tile_xbox360_data,
)
from aurora_engine.texture.header import (
    _next_power_of_2,
    _compute_dxt_pitch,
    build_xbox360_texture_header,
    parse_xbox360_texture_header,
    parse_xbox360_texture_pitch,
)
from aurora_engine.texture.dxt_encode import (
    _dequant_565,
    _bump_565,
    _fit_dxt_block,
    rgb565,
    pil_to_dxt5,
    pil_to_dxt1,
    pil_to_dxt1_blocks,
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

__all__ = [
    "byte_swap_16",
    "_init_dll",
    "get_dll",
    "xg_address_2d_tiled_offset",
    "untile_xbox360_data",
    "tile_xbox360_data",
    "_next_power_of_2",
    "_compute_dxt_pitch",
    "build_xbox360_texture_header",
    "parse_xbox360_texture_header",
    "parse_xbox360_texture_pitch",
    "_dequant_565",
    "_bump_565",
    "_fit_dxt_block",
    "rgb565",
    "pil_to_dxt5",
    "pil_to_dxt1",
    "pil_to_dxt1_blocks",
    "_decode_dxt1_blocks",
    "_decode_dxt5_blocks",
    "pil_to_argb",
    "argb_to_pil",
    "raw_argb_to_pil",
    "convert_image_bytes_to_asset",
    "encode_image",
    "convert_asset_to_pil",
    "convert_asset_to_png_bytes",
    "decode_asset_to_image",
    "decode_asset_to_png",
]
