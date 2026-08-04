"""
Optional native AuroraAsset.dll backend (Windows only).

On Windows, if AuroraAsset.dll can be located it is loaded via ctypes and used
as the fast path for encoding/decoding. On every other platform (and on Windows
without the DLL) the pure-Python codec in this package is used instead.
"""

import ctypes
import os
import platform

_DLL = None
_DLL_LOADED = False


def _init_dll():
    """Locates and loads AuroraAsset.dll once (Windows only); no-op elsewhere."""
    global _DLL, _DLL_LOADED
    if _DLL_LOADED:
        return
    _DLL_LOADED = True

    if platform.system() == "Windows":
        possible_paths = [
            os.path.join(os.path.dirname(__file__), "..", "..", "!old", "AuroraAssetEditor", "AuroraAsset.dll"),
            os.path.join(os.path.dirname(__file__), "..", "..", "AuroraAssetEditor", "AuroraAsset.dll"),
            os.path.join(os.path.dirname(__file__), "..", "..", "AuroraAsset.dll"),
            "AuroraAsset.dll",
        ]
        for dll_path in possible_paths:
            abs_path = os.path.abspath(dll_path)
            if os.path.exists(abs_path):
                try:
                    _DLL = ctypes.CDLL(abs_path)
                    _DLL.ConvertImageToAsset.argtypes = [
                        ctypes.c_void_p, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                        ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                        ctypes.c_void_p, ctypes.POINTER(ctypes.c_int)
                    ]
                    _DLL.ConvertImageToAsset.restype = ctypes.c_int

                    _DLL.ConvertAssetToImage.argtypes = [
                        ctypes.c_void_p, ctypes.c_int,
                        ctypes.c_void_p, ctypes.c_int,
                        ctypes.c_void_p, ctypes.POINTER(ctypes.c_int),
                        ctypes.POINTER(ctypes.c_int), ctypes.POINTER(ctypes.c_int)
                    ]
                    _DLL.ConvertAssetToImage.restype = ctypes.c_int
                    print("Loaded AuroraAsset.dll via ctypes (Windows native mode)")
                    break
                except Exception as e:
                    print(f"DLL load failed: {e}")


def get_dll():
    """Returns the loaded native DLL handle, or None if unavailable.

    Lazily triggers the one-time load on first call so callers don't need to
    invoke ``_init_dll()`` themselves.
    """
    _init_dll()
    return _DLL
