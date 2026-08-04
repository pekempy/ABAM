"""
Aurora Asset Local Cache Manager
Stores .asset binary files and extracted PNG previews locally on disk.
Keeps game library loading fast, responsive, and persistent across sessions.
"""

import os
from typing import Dict, Optional, Tuple
from aurora_engine.asset_parser import AuroraAssetFile
from aurora_engine.texture.decode import convert_asset_to_png_bytes

CACHE_BASE_DIR = os.path.expanduser("~/.aurora_asset_editor/cache")

def normalize_cache_key(cache_key: str) -> str:
    """Normalizes cache directory keys for TitleID or Aurora folder-path identities."""
    clean_key = (cache_key or "").strip().upper()
    if not clean_key:
        return "00000000"
    if "_" in clean_key:
        return clean_key
    return clean_key.zfill(8)

def get_cache_dir_for_game(cache_key: str) -> str:
    """Returns local cache directory path for specified game cache key."""
    clean_id = normalize_cache_key(cache_key)
    game_dir = os.path.join(CACHE_BASE_DIR, clean_id)
    os.makedirs(game_dir, exist_ok=True)
    return game_dir

def cache_asset_file(cache_key: str, title_id: str, category: str, asset_obj: AuroraAssetFile):
    """Saves binary .asset file and extracted PNG preview images to local disk cache."""
    if not cache_key or not title_id or title_id == "00000000":
        return

    clean_title_id = title_id.strip().upper().zfill(8)
    game_dir = get_cache_dir_for_game(cache_key)
    prefix_map = {
        "boxart": f"GC{clean_title_id}.asset",
        "background": f"BK{clean_title_id}.asset",
        "icon_banner": f"GL{clean_title_id}.asset",
        "screenshots": f"SS{clean_title_id}.asset"
    }

    filename = prefix_map.get(category, f"{category}.asset")
    asset_file_path = os.path.join(game_dir, filename)

    # Save binary .asset file
    try:
        data = asset_obj.pack()
        with open(asset_file_path, "wb") as f:
            f.write(data)
    except Exception as e:
        print(f"Failed to cache asset binary for {cache_key} / {category}: {e}")

    # Extract & Save PNG preview images for fast loading
    try:
        non_empty_count = 0
        for idx, entry in enumerate(asset_obj.entries):
            if entry.size > 0:
                png_bytes = convert_asset_to_png_bytes(entry.texture_header, entry.video_data)
                if png_bytes:
                    png_name = f"{category}_{non_empty_count}.png"
                    png_path = os.path.join(game_dir, png_name)
                    with open(png_path, "wb") as f:
                        f.write(png_bytes)
                    non_empty_count += 1
    except Exception as e:
        print(f"Failed to cache PNG preview for {cache_key} / {category}: {e}")

def load_cached_asset(cache_key: str, title_id: str, category: str) -> Optional[AuroraAssetFile]:
    """Loads a cached .asset file from local disk if present."""
    if not cache_key or not title_id or title_id == "00000000":
        return None

    clean_key = normalize_cache_key(cache_key)
    clean_title_id = title_id.strip().upper().zfill(8)
    prefix_map = {
        "boxart": f"GC{clean_title_id}.asset",
        "background": f"BK{clean_title_id}.asset",
        "icon_banner": f"GL{clean_title_id}.asset",
        "screenshots": f"SS{clean_title_id}.asset",
    }

    filename = prefix_map.get(category)
    if not filename:
        return None

    asset_file_path = os.path.join(CACHE_BASE_DIR, clean_key, filename)
    if os.path.exists(asset_file_path):
        try:
            with open(asset_file_path, "rb") as f:
                raw_bytes = f.read()
            return AuroraAssetFile(raw_bytes)
        except Exception as e:
            print(f"Error loading cached asset file {asset_file_path}: {e}")

    return None

def get_cached_png_bytes(cache_key: str, category: str, asset_index: int) -> Optional[bytes]:
    """Retrieves pre-extracted PNG preview bytes from local disk cache."""
    if not cache_key:
        return None

    clean_key = normalize_cache_key(cache_key)
    png_path = os.path.join(CACHE_BASE_DIR, clean_key, f"{category}_{asset_index}.png")

    if os.path.exists(png_path):
        try:
            with open(png_path, "rb") as f:
                return f.read()
        except Exception:
            pass

    # Map raw entry indices to 0-indexed logical files
    raw_to_logical = {
        "boxart": {2: 0},
        "background": {4: 0},
        "screenshots": {5: 0, 6: 1, 7: 2, 8: 3},
        "icon_banner": {0: 0, 1: 1},
    }
    logical_idx = raw_to_logical.get(category, {}).get(asset_index)
    if logical_idx is not None:
        alt_path = os.path.join(CACHE_BASE_DIR, clean_key, f"{category}_{logical_idx}.png")
        if os.path.exists(alt_path):
            try:
                with open(alt_path, "rb") as f:
                    return f.read()
            except Exception:
                pass

    return None

def clear_cache() -> int:
    """Clears all local asset cache files."""
    count = 0
    if os.path.exists(CACHE_BASE_DIR):
        import shutil
        for root, dirs, files in os.walk(CACHE_BASE_DIR):
            count += len(files)
        shutil.rmtree(CACHE_BASE_DIR, ignore_errors=True)
        os.makedirs(CACHE_BASE_DIR, exist_ok=True)
    return count

def clear_cached_asset(cache_key: str, title_id: str, category: str) -> int:
    """Deletes the cached .asset binary and PNG previews for a single game category."""
    if not cache_key or not title_id or title_id == "00000000":
        return 0

    clean_key = normalize_cache_key(cache_key)
    clean_title_id = title_id.strip().upper().zfill(8)
    game_dir = os.path.join(CACHE_BASE_DIR, clean_key)
    if not os.path.isdir(game_dir):
        return 0

    prefix_map = {
        "boxart": f"GC{clean_title_id}.asset",
        "background": f"BK{clean_title_id}.asset",
        "icon_banner": f"GL{clean_title_id}.asset",
        "screenshots": f"SS{clean_title_id}.asset",
    }
    removed = 0
    asset_name = prefix_map.get(category)
    if asset_name:
        p = os.path.join(game_dir, asset_name)
        if os.path.exists(p):
            try:
                os.remove(p); removed += 1
            except Exception:
                pass
    try:
        for f in os.listdir(game_dir):
            if f.startswith(f"{category}_") and f.endswith(".png"):
                try:
                    os.remove(os.path.join(game_dir, f)); removed += 1
                except Exception:
                    pass
    except Exception:
        pass
    return removed
