"""
Aurora Engine REST API Server
Built with FastAPI. Serves backend endpoints for asset parsing, image processing,
FTP Xbox synchronization, and online cover search.
"""

import base64
import copy
import io
import os
import tempfile
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, Response
from pydantic import BaseModel

from aurora_engine.asset_parser import AssetType, AuroraAssetFile
from aurora_engine.cache import (
    cache_asset_file,
    clear_cache,
    clear_cached_asset,
    get_cached_png_bytes,
    load_cached_asset,
    normalize_cache_key,
)
from aurora_engine.db_manager import parse_content_db
from aurora_engine import demo_data
from aurora_engine.integrations.ftp_client import AuroraFtpClient
from aurora_engine.integrations.internet_archive import InternetArchiveClient
from aurora_engine.integrations.xbox_live import XboxLiveClient
from aurora_engine.integrations.xbox_unity import XboxUnityClient
from aurora_engine.texture.decode import convert_asset_to_pil, convert_asset_to_png_bytes
from aurora_engine.texture.encode import convert_image_bytes_to_asset

PREVIEW_HEADERS = {
    "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
    "Pragma": "no-cache",
    "Expires": "0",
}

def get_game_cache_key(title_id: str, db_id: Optional[str] = None, folder_path: Optional[str] = None) -> str:
    if folder_path:
        return normalize_cache_key(folder_path)
    clean_title = (title_id or "00000000").strip().upper().zfill(8)
    clean_db = (db_id or "").strip().upper().zfill(8) if db_id else ""
    if clean_db and clean_db != "00000000":
        return f"{clean_title}_{clean_db}"
    return normalize_cache_key(clean_title)

app = FastAPI(title="Aurora Better Asset Manager Engine", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global State Management
CURRENT_ASSETS: Dict[str, AuroraAssetFile] = {
    "boxart": AuroraAssetFile(),
    "background": AuroraAssetFile(),
    "icon_banner": AuroraAssetFile(),
    "screenshots": AuroraAssetFile(),
}

CURRENT_GAME_INFO = {
    "title_name": "No Game Selected",
    "description": "",
    "publisher": "",
    "developer": "",
    "release_date": "",
    "title_id": "00000000",
    "media_id": "00000000",
    "db_id": "00000000",
    "disc_num": 1,
    "folder_path": "00000000_00000000"
}

FTP_CLIENT = AuroraFtpClient()

# Pre-edit snapshots of individual asset entries, keyed by
# f"{cache_key}|{category}|{entry_index}". A value of None means the slot was
# empty before the first edit. Used by /api/asset/revert to undo local edits.
ASSET_ENTRY_BACKUPS: Dict[str, Optional[Any]] = {}

def _backup_entry_once(cache_key: str, category: str, target_entry: int, asset_obj: AuroraAssetFile):
    """Snapshots an asset entry before its first edit so it can be reverted later."""
    key = f"{cache_key}|{category}|{target_entry}"
    if key in ASSET_ENTRY_BACKUPS:
        return
    if 0 <= target_entry < len(asset_obj.entries):
        entry = asset_obj.entries[target_entry]
        ASSET_ENTRY_BACKUPS[key] = copy.deepcopy(entry) if entry.size > 0 else None
    else:
        ASSET_ENTRY_BACKUPS[key] = None

class FtpConfigModel(BaseModel):
    ip: str = ""
    username: str = "xboxftp"
    password: str = "xboxftp"
    port: int = 21

class FtpSyncPayloadModel(BaseModel):
    ip: str = ""
    username: str = "xboxftp"
    password: str = "xboxftp"
    port: int = 21
    title_id: Optional[str] = None
    db_id: Optional[str] = None
    title_name: Optional[str] = None
    media_id: Optional[str] = None
    # Restricts the push to just these asset categories (e.g. only the ones the
    # user actually changed), instead of re-uploading every populated category
    # for the game. None/omitted preserves the old "sync everything populated"
    # behavior for callers that still want a full sync.
    categories: Optional[List[str]] = None

class SetGameInfoModel(BaseModel):
    title_name: str
    description: str = ""
    publisher: str = ""
    developer: str = ""
    release_date: str = ""
    title_id: str
    media_id: str = "00000000"
    db_id: str = "00000001"
    disc_num: int = 1

@app.get("/api/status")
def get_status():
    return {
        "status": "online",
        "game": CURRENT_GAME_INFO,
        "ftp_configured": bool(FTP_CLIENT.ip) or demo_data.is_demo_mode(),
        "ftp_ip": FTP_CLIENT.ip,
        "demo_mode": demo_data.is_demo_mode()
    }

class LibraryStatusPayload(BaseModel):
    games: List[Dict[str, Any]]

@app.post("/api/library/asset-status")
def get_library_asset_status(payload: LibraryStatusPayload):
    """
    For each game in the library, checks the local disk cache and returns which
    asset types exist (boxart, background, icon_banner, screenshots count).
    """
    if demo_data.is_demo_mode():
        return demo_data.get_demo_asset_status(payload.games)

    from aurora_engine.cache import CACHE_BASE_DIR

    results = []
    for game in payload.games:
        title_id = (game.get("title_id") or "").strip().upper().zfill(8)
        if not title_id or title_id == "00000000":
            continue

        cache_key = get_game_cache_key(title_id, game.get("db_id"), game.get("folder_path"))
        game_dir = os.path.join(CACHE_BASE_DIR, cache_key)

        def _asset_exists(prefix: str) -> bool:
            path = os.path.join(game_dir, f"{prefix}{title_id}.asset")
            if os.path.exists(path) and os.path.getsize(path) >= 64:
                return True
            # Also accept any file starting with that prefix in game_dir
            if os.path.isdir(game_dir):
                for fn in os.listdir(game_dir):
                    if fn.upper().startswith(prefix.upper()) and fn.lower().endswith(".asset"):
                        p = os.path.join(game_dir, fn)
                        if os.path.getsize(p) >= 64:
                            return True
            return False

        def _screenshot_count() -> int:
            path = os.path.join(game_dir, f"SS{title_id}.asset")
            if not os.path.exists(path) or os.path.getsize(path) < 64:
                return 0
            try:
                with open(path, "rb") as f:
                    data = f.read()
                asset = AuroraAssetFile(data)
                return asset.screenshot_count
            except Exception:
                return 0

        def _gl_asset_status() -> dict:
            path = os.path.join(game_dir, f"GL{title_id}.asset")
            if not os.path.exists(path) or os.path.getsize(path) < 64:
                return {"has_icon": False, "has_banner": False}
            try:
                with open(path, "rb") as f:
                    data = f.read()
                asset = AuroraAssetFile(data)
                return {
                    "has_icon": asset.entries[AssetType.ICON].size > 0,
                    "has_banner": asset.entries[AssetType.BANNER].size > 0,
                }
            except Exception:
                return {"has_icon": False, "has_banner": False}

        gl = _gl_asset_status()
        results.append({
            "title_id": title_id,
            "db_id": (game.get("db_id") or "00000001").strip().upper().zfill(8),
            "title_name": game.get("title_name", "Unknown"),
            "has_boxart": _asset_exists("GC"),
            "has_background": _asset_exists("BK"),
            "has_icon": gl["has_icon"],
            "has_banner": gl["has_banner"],
            "screenshot_count": _screenshot_count(),
        })

    total = len(results)
    missing_any = sum(
        1 for r in results
        if not r["has_boxart"] or not r["has_background"]
        or not r["has_icon"] or not r["has_banner"] or r["screenshot_count"] == 0
    )
    return {
        "success": True,
        "total": total,
        "missing_any": missing_any,
        "complete": total - missing_any,
        "results": results
    }

@app.post("/api/game/set-info")
def set_game_info(data: SetGameInfoModel):
    title_id_hex = data.title_id.strip().upper().zfill(8)
    db_id_hex = data.db_id.strip().upper().zfill(8)
    media_id_hex = data.media_id.strip().upper().zfill(8)

    CURRENT_GAME_INFO["title_name"] = data.title_name
    CURRENT_GAME_INFO["description"] = data.description or ""
    CURRENT_GAME_INFO["publisher"] = data.publisher or ""
    CURRENT_GAME_INFO["developer"] = data.developer or ""
    CURRENT_GAME_INFO["release_date"] = data.release_date or ""
    CURRENT_GAME_INFO["title_id"] = title_id_hex
    CURRENT_GAME_INFO["media_id"] = media_id_hex
    CURRENT_GAME_INFO["db_id"] = db_id_hex
    CURRENT_GAME_INFO["disc_num"] = data.disc_num
    CURRENT_GAME_INFO["folder_path"] = f"{title_id_hex}_{db_id_hex}"

    # Auto-load cached assets from disk if available for instant UI rendering.
    # Always reset each slot first so a previously-edited game's in-memory asset
    # never leaks into a newly-selected game that has no cached asset of its own.
    cache_key = get_game_cache_key(title_id_hex, db_id_hex, CURRENT_GAME_INFO["folder_path"])
    for cat in CURRENT_ASSETS:
        cached_asset = load_cached_asset(cache_key, title_id_hex, cat)
        CURRENT_ASSETS[cat] = cached_asset if cached_asset else AuroraAssetFile()

    return {"status": "success", "game": CURRENT_GAME_INFO}

@app.post("/api/ftp/config")
def set_ftp_config(cfg: FtpConfigModel):
    FTP_CLIENT.save_settings(cfg.ip, cfg.username, cfg.password, cfg.port)
    return {"status": "success", "message": f"FTP settings saved for {cfg.ip}"}

@app.get("/api/ftp/config")
def get_ftp_config():
    return {
        "ip": FTP_CLIENT.ip,
        "username": FTP_CLIENT.username,
        "password": FTP_CLIENT.password,
        "port": FTP_CLIENT.port
    }

@app.post("/api/ftp/test")
def test_ftp_connection(cfg: FtpConfigModel):
    if demo_data.is_demo_mode():
        return {"success": True, "message": "Demo mode: simulated Xbox console connection OK."}
    client = AuroraFtpClient(cfg.ip, cfg.username, cfg.password, cfg.port)
    ok, msg = client.connect()
    client.disconnect()
    return {"success": ok, "message": msg}

@app.post("/api/ftp/download-db")
def download_content_db(cfg: FtpConfigModel):
    if demo_data.is_demo_mode():
        games = demo_data.get_demo_games()
        return {
            "success": True,
            "message": f"Demo mode: loaded {len(games)} fake games for UI/UX testing.",
            "count": len(games),
            "games": games
        }

    client = AuroraFtpClient(cfg.ip, cfg.username, cfg.password, cfg.port)
    temp_dir = tempfile.gettempdir()
    db_path = os.path.join(temp_dir, "aurora_content.db")

    if os.path.exists(db_path):
        try:
            os.remove(db_path)
        except Exception:
            pass

    ok, msg = client.download_content_db(db_path)
    client.disconnect()

    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    # Parse Content.db
    items = parse_content_db(db_path)
    return {
        "success": True,
        "message": f"Successfully loaded {len(items)} games from Xbox console database!",
        "count": len(items),
        "games": [item.to_dict() for item in items]
    }

@app.post("/api/db/parse-file")
async def parse_local_db_file(file: UploadFile = File(...)):
    contents = await file.read()
    temp_dir = tempfile.gettempdir()
    db_path = os.path.join(temp_dir, f"uploaded_{file.filename}")

    with open(db_path, "wb") as f:
        f.write(contents)

    try:
        items = parse_content_db(db_path)
        return {
            "success": True,
            "count": len(items),
            "games": [item.to_dict() for item in items]
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse database file: {str(e)}")

class PushTitleNameModel(BaseModel):
    ip: str = ""
    username: str = "xboxftp"
    password: str = "xboxftp"
    port: int = 21
    title_id: str
    title_id_int: Optional[int] = None
    db_id: Optional[str] = None
    db_id_int: Optional[int] = None
    new_name: str
    description: Optional[str] = None

@app.post("/api/ftp/pull-title-name")
def ftp_pull_title_name(cfg: FtpConfigModel):
    """Downloads Content.db from console and returns the current title names for all games."""
    if demo_data.is_demo_mode():
        games = demo_data.get_demo_games()
        return {
            "success": True,
            "message": f"Demo mode: pulled {len(games)} fake title names.",
            "games": games
        }

    client = AuroraFtpClient(cfg.ip, cfg.username, cfg.password, cfg.port)
    temp_dir = tempfile.gettempdir()
    db_path = os.path.join(temp_dir, "aurora_content_pull.db")

    ok, msg = client.pull_title_name(db_path)
    client.disconnect()

    if not ok:
        raise HTTPException(status_code=400, detail=msg)

    items = parse_content_db(db_path)
    return {
        "success": True,
        "message": f"Pulled {len(items)} title names from console!",
        "games": [item.to_dict() for item in items]
    }

@app.post("/api/ftp/push-title-name")
def ftp_push_title_name(payload: PushTitleNameModel):
    """Modifies CustomTitleName in Content.db on the console for the specified game."""
    if not payload.new_name.strip():
        raise HTTPException(status_code=400, detail="New title name cannot be empty.")

    if demo_data.is_demo_mode():
        CURRENT_GAME_INFO["title_name"] = payload.new_name.strip()
        if payload.description is not None:
            CURRENT_GAME_INFO["description"] = payload.description
        return {"success": True, "message": f"Demo mode: renamed game to '{payload.new_name.strip()}' (not sent to any console)."}

    if not payload.ip:
        raise HTTPException(status_code=400, detail="Xbox console FTP IP is required.")

    client = AuroraFtpClient(payload.ip, payload.username, payload.password, payload.port)
    ok, msg = client.connect()
    if not ok:
        client.disconnect()
        raise HTTPException(status_code=400, detail=msg)

    temp_dir = tempfile.gettempdir()
    db_path = os.path.join(temp_dir, "aurora_content_push.db")

    # Resolve title_id to integer
    title_id_int = payload.title_id_int
    if title_id_int is None:
        try:
            title_id_int = int(payload.title_id, 16)
        except ValueError:
            client.disconnect()
            raise HTTPException(status_code=400, detail=f"Invalid hex TitleID: {payload.title_id}")

    db_id_int = payload.db_id_int
    if db_id_int is None and payload.db_id:
        try:
            db_id_int = int(payload.db_id, 16)
        except ValueError:
            client.disconnect()
            raise HTTPException(status_code=400, detail=f"Invalid hex DB ID: {payload.db_id}")

    ok, msg = client.push_title_name(
        title_id_int, payload.new_name.strip(), db_path, db_id=db_id_int,
        description=payload.description,
    )
    client.disconnect()

    if not ok:
        # If the local DB was edited but upload was blocked by Aurora's lock,
        # return a partial-success so the UI can offer a manual download
        local_exists = os.path.exists(db_path)
        if local_exists and "manually copy" in msg:
            return {
                "success": False,
                "partial": True,
                "message": msg,
                "download_url": "/api/ftp/download-modified-db"
            }
        raise HTTPException(status_code=400, detail=msg)

    # Update local state immediately
    CURRENT_GAME_INFO["title_name"] = payload.new_name.strip()
    if payload.description is not None:
        CURRENT_GAME_INFO["description"] = payload.description

    return {"success": True, "message": msg}

@app.get("/api/ftp/download-modified-db")
def download_modified_db():
    """Serves the locally-modified Content.db so the user can copy it to the console manually."""
    db_path = os.path.join(tempfile.gettempdir(), "aurora_content_push.db")
    if not os.path.exists(db_path):
        raise HTTPException(status_code=404, detail="No modified Content.db found. Push a title name first.")
    from fastapi.responses import FileResponse
    return FileResponse(
        db_path,
        media_type="application/octet-stream",
        filename="Content.db"
    )

@app.post("/api/asset/upload-file")
async def upload_asset_file(category: str = Form(...), file: UploadFile = File(...)):
    """Loads an .asset binary file into memory for editing and caches to disk."""
    contents = await file.read()
    try:
        asset_obj = AuroraAssetFile(contents)
        if category in CURRENT_ASSETS:
            CURRENT_ASSETS[category] = asset_obj
            cache_asset_file(CURRENT_GAME_INFO["folder_path"], CURRENT_GAME_INFO["title_id"], category, asset_obj)
        return {
            "status": "success",
            "category": category,
            "summary": asset_obj.get_summary()
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid asset file: {str(e)}")

@app.get("/api/asset/preview/{category}/{asset_index}")
def get_asset_preview(category: str, asset_index: int, title: Optional[str] = None, db: Optional[str] = None):
    """Renders PNG preview image of stored asset entry (served instantly from disk cache if present)."""
    if category not in CURRENT_ASSETS:
        raise HTTPException(status_code=404, detail="Category not found.")

    requested_title = (title or "").strip().upper().zfill(8) if title else None
    requested_db = (db or "").strip().upper().zfill(8) if db else None
    target_title_id = (requested_title or CURRENT_GAME_INFO.get("title_id", "00000000") or "00000000").strip().upper().zfill(8)
    target_cache_key = get_game_cache_key(target_title_id, requested_db)
    current_cache_key = get_game_cache_key(
        CURRENT_GAME_INFO.get("title_id", "00000000"),
        CURRENT_GAME_INFO.get("db_id", "00000000"),
        CURRENT_GAME_INFO.get("folder_path"),
    )

    # 1. Fast path: check local disk cache for pre-rendered PNG preview
    cached_png = get_cached_png_bytes(target_cache_key, category, asset_index)
    if cached_png:
        return Response(content=cached_png, media_type="image/png", headers=PREVIEW_HEADERS)

    # 2. Load cached .asset binary for the requested title if available
    asset_obj = load_cached_asset(target_cache_key, target_title_id, category)
    if asset_obj is None:
        if requested_title and target_cache_key != current_cache_key:
            if demo_data.is_demo_mode():
                demo_png = demo_data.demo_preview_png(category, asset_index, target_title_id)
                if demo_png:
                    return Response(content=demo_png, media_type="image/png", headers=PREVIEW_HEADERS)
            transparent_png = (
                b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01\xe2!\xbc3\x00\x00\x00\x00IEND\xaeB`\x82"
            )
            return Response(content=transparent_png, media_type="image/png", headers=PREVIEW_HEADERS)
        asset_obj = CURRENT_ASSETS[category]

    # 3. Memory path: convert stored asset entry to PNG
    non_empty_entries = [e for e in asset_obj.entries if e.size > 0]
    target_entry = None
    if 0 <= asset_index < len(asset_obj.entries) and asset_obj.entries[asset_index].size > 0:
        target_entry = asset_obj.entries[asset_index]
    elif 0 <= asset_index < len(non_empty_entries):
        target_entry = non_empty_entries[asset_index]

    if target_entry and target_entry.size > 0:
        png_bytes = convert_asset_to_png_bytes(target_entry.texture_header, target_entry.video_data)
        if png_bytes:
            return Response(content=png_bytes, media_type="image/png", headers=PREVIEW_HEADERS)

    # Demo mode: serve generated placeholder art when no real asset is present
    if demo_data.is_demo_mode():
        demo_png = demo_data.demo_preview_png(category, asset_index, target_title_id)
        if demo_png:
            return Response(content=demo_png, media_type="image/png", headers=PREVIEW_HEADERS)

    # Transparent fallback pixel
    transparent_png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\x0cIDATx\x9cc`\x00\x00\x00\x02\x00\x01\xe2!\xbc\x33\x00\x00\x00\x00IEND\xaeB`\x82"
    )
    return Response(content=transparent_png, media_type="image/png", headers=PREVIEW_HEADERS)

def resolve_target_entry_index(category: str, asset_index: int) -> int:
    """Maps category and frontend asset_index to the exact Aurora AssetType entry index."""
    if category == "boxart":
        return 2  # AssetType.BOXART
    elif category == "background":
        return 4  # AssetType.BACKGROUND
    elif category == "icon_banner":
        return 1 if asset_index == 1 else 0  # 0=Icon, 1=Banner
    elif category == "screenshots":
        return 5 + asset_index  # 0=Entry 5, 1=Entry 6, etc.
    return asset_index

def _get_target_game_and_asset(category: str, title_id: Optional[str], db_id: Optional[str]):
    """Returns (game_info_dict, AuroraAssetFile) for target title_id & category safely."""
    title_id_clean = (title_id or "").strip().upper().zfill(8)
    curr_title_id = (CURRENT_GAME_INFO.get("title_id") or "").strip().upper().zfill(8)

    if title_id_clean and title_id_clean != "00000000" and title_id_clean == curr_title_id:
        return CURRENT_GAME_INFO, CURRENT_ASSETS.get(category)

    if title_id_clean and title_id_clean != "00000000":
        folder_path = get_game_cache_key(title_id_clean, db_id or "00000001", None)
        game_info = {
            "title_id": title_id_clean,
            "db_id": (db_id or "00000001").strip().upper().zfill(8),
            "folder_path": folder_path,
            "title_name": title_id_clean,
        }
        from aurora_engine.cache import load_cached_asset_file
        asset_obj = load_cached_asset_file(folder_path, title_id_clean, category)
        if not asset_obj:
            asset_obj = AuroraAssetFile()
        return game_info, asset_obj

    return CURRENT_GAME_INFO, CURRENT_ASSETS.get(category)

def _assert_game_context(title_id: Optional[str], db_id: Optional[str]):
    """Compatibility assertion for UI operations."""
    pass

@app.post("/api/asset/replace-image")
async def replace_asset_image(
    category: str = Form(...),
    asset_index: int = Form(...),
    compress: bool = Form(True),
    file: UploadFile = File(...),
    title_id: Optional[str] = Form(None),
    db_id: Optional[str] = Form(None),
):
    """Replaces image for an asset entry with a newly uploaded PNG/JPG image."""
    game_info, asset_obj = _get_target_game_and_asset(category, title_id, db_id)
    if not asset_obj:
        asset_obj = AuroraAssetFile()

    img_bytes = await file.read()
    try:
        target_entry = resolve_target_entry_index(category, asset_index)
        existing_entry = asset_obj.entries[target_entry] if 0 <= target_entry < len(asset_obj.entries) else None
        existing_header = existing_entry.texture_header if existing_entry and existing_entry.size > 0 else None

        header, video, width, height = convert_image_bytes_to_asset(img_bytes, compress=compress, existing_header=existing_header)
        _backup_entry_once(game_info["folder_path"], category, target_entry, asset_obj)
        asset_obj.set_entry_data(target_entry, header, video, width, height)
        cache_asset_file(game_info["folder_path"], game_info["title_id"], category, asset_obj)

        return {
            "status": "success",
            "category": category,
            "asset_index": asset_index,
            "target_entry": target_entry,
            "width": width,
            "height": height,
            "data_size": len(video)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process image: {str(e)}")

@app.post("/api/asset/replace-image-url")
def replace_asset_image_url(
    category: str = Form(...),
    asset_index: int = Form(...),
    url: str = Form(...),
    compress: bool = Form(True),
    title_id: Optional[str] = Form(None),
    db_id: Optional[str] = Form(None),
):
    """Fetches image from URL and sets it as asset entry image."""
    game_info, asset_obj = _get_target_game_and_asset(category, title_id, db_id)
    if not asset_obj:
        asset_obj = AuroraAssetFile()

    img_bytes = XboxUnityClient.download_image(url)
    if not img_bytes:
        raise HTTPException(status_code=400, detail="Failed to download image from URL.")

    try:
        target_entry = resolve_target_entry_index(category, asset_index)
        existing_entry = asset_obj.entries[target_entry] if 0 <= target_entry < len(asset_obj.entries) else None
        existing_header = existing_entry.texture_header if existing_entry and existing_entry.size > 0 else None

        header, video, width, height = convert_image_bytes_to_asset(img_bytes, compress=compress, existing_header=existing_header)
        _backup_entry_once(game_info["folder_path"], category, target_entry, asset_obj)
        asset_obj.set_entry_data(target_entry, header, video, width, height)
        cache_asset_file(game_info["folder_path"], game_info["title_id"], category, asset_obj)

        return {
            "status": "success",
            "category": category,
            "asset_index": asset_index,
            "target_entry": target_entry,
            "width": width,
            "height": height,
            "data_size": len(video)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to process image from URL: {str(e)}")

class AssetRevertModel(BaseModel):
    category: str
    asset_index: int = 0

@app.post("/api/asset/revert")
def revert_asset(payload: AssetRevertModel):
    """Reverts a previously-edited asset entry to its pre-edit state (undo local change)."""
    category = payload.category
    if category not in CURRENT_ASSETS:
        raise HTTPException(status_code=404, detail="Category not found.")

    target_entry = resolve_target_entry_index(category, payload.asset_index)
    cache_key = CURRENT_GAME_INFO["folder_path"]
    title_id = CURRENT_GAME_INFO["title_id"]
    bkey = f"{cache_key}|{category}|{target_entry}"
    asset_obj = CURRENT_ASSETS[category]

    reverted = False
    if bkey in ASSET_ENTRY_BACKUPS:
        backup = ASSET_ENTRY_BACKUPS.pop(bkey)
        if backup is None:
            asset_obj.remove_entry(target_entry)
        else:
            asset_obj.entries[target_entry] = copy.deepcopy(backup)
        reverted = True
    else:
        # No pre-edit snapshot available (e.g. server was restarted). Best effort:
        # clear the slot so the local edit no longer overrides the default art.
        asset_obj.remove_entry(target_entry)

    # Rewrite disk cache cleanly: drop any stale files, then re-cache if anything remains.
    clear_cached_asset(cache_key, title_id, category)
    if any(e.size > 0 for e in asset_obj.entries):
        cache_asset_file(cache_key, title_id, category, asset_obj)

    return {
        "status": "success",
        "reverted": reverted,
        "category": category,
        "asset_index": payload.asset_index,
        "target_entry": target_entry,
    }

@app.get("/api/asset/download/{category}")
def download_asset_binary(category: str):
    """Generates and downloads compiled .asset binary file."""
    if category not in CURRENT_ASSETS:
        raise HTTPException(status_code=404, detail="Category not found.")

    asset_obj = CURRENT_ASSETS[category]
    binary_bytes = asset_obj.pack()

    title_id = CURRENT_GAME_INFO.get("title_id", "00000000")
    prefix_map = {
        "boxart": f"GC{title_id}.asset",
        "background": f"BK{title_id}.asset",
        "icon_banner": f"GL{title_id}.asset",
        "screenshots": f"SS{title_id}.asset"
    }

    filename = prefix_map.get(category, f"Asset_{title_id}.asset")
    return Response(
        content=binary_bytes,
        media_type="application/octet-stream",
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )

@app.post("/api/ftp/sync-game-assets")
def ftp_sync_game_assets(payload: FtpSyncPayloadModel):
    """Uploads active asset files directly to Xbox 360 console via FTP."""
    if payload.title_id and payload.title_id != "00000000":
        title_id_hex = payload.title_id.strip().upper().zfill(8)
        db_id_hex = (payload.db_id or "00000001").strip().upper().zfill(8)
        media_id_hex = (payload.media_id or "00000000").strip().upper().zfill(8)

        CURRENT_GAME_INFO["title_name"] = payload.title_name or CURRENT_GAME_INFO.get("title_name", "Game")
        CURRENT_GAME_INFO["title_id"] = title_id_hex
        CURRENT_GAME_INFO["media_id"] = media_id_hex
        CURRENT_GAME_INFO["db_id"] = db_id_hex
        CURRENT_GAME_INFO["folder_path"] = f"{title_id_hex}_{db_id_hex}"

    folder = CURRENT_GAME_INFO["folder_path"]
    title_id = CURRENT_GAME_INFO["title_id"]

    if demo_data.is_demo_mode():
        return {"status": "complete", "results": [
            {"file": f"GC{title_id}.asset", "success": True, "message": "Demo mode: simulated upload."},
            {"file": f"BK{title_id}.asset", "success": True, "message": "Demo mode: simulated upload."},
            {"file": f"GL{title_id}.asset", "success": True, "message": "Demo mode: simulated upload."},
            {"file": f"SS{title_id}.asset", "success": True, "message": "Demo mode: simulated upload."},
        ]}

    client = AuroraFtpClient(payload.ip, payload.username, payload.password, payload.port)
    ok, msg = client.connect()
    if not ok:
        client.disconnect()
        raise HTTPException(status_code=400, detail=msg)

    results = []
    category_files = [
        ("boxart", f"GC{title_id}.asset"),
        ("background", f"BK{title_id}.asset"),
        ("icon_banner", f"GL{title_id}.asset"),
        ("screenshots", f"SS{title_id}.asset"),
    ]

    # When the caller tells us which categories actually changed, only push
    # those -- otherwise every category with any in-memory data gets
    # re-uploaded on every push, even ones nothing was queued for.
    if payload.categories is not None:
        wanted = set(payload.categories)
        category_files = [(cat, fname) for cat, fname in category_files if cat in wanted]

    for cat, fname in category_files:
        asset_obj = CURRENT_ASSETS[cat]
        if asset_obj.data_size > 0 or any(e.size > 0 for e in asset_obj.entries):
            data = asset_obj.pack()
            succ, umsg = client.upload_asset_file(folder, fname, data)
            results.append({"file": fname, "success": succ, "message": umsg})

    client.disconnect()
    return {"status": "complete", "results": results}

@app.post("/api/ftp/pull-game-assets")
def ftp_pull_game_assets(payload: FtpSyncPayloadModel):
    """Downloads and parses existing asset files for current game directly from Xbox console via FTP."""
    if payload.title_id and payload.title_id != "00000000":
        title_id_hex = payload.title_id.strip().upper().zfill(8)
        db_id_hex = (payload.db_id or "00000001").strip().upper().zfill(8)
        media_id_hex = (payload.media_id or "00000000").strip().upper().zfill(8)

        CURRENT_GAME_INFO["title_name"] = payload.title_name or CURRENT_GAME_INFO.get("title_name", "Game")
        CURRENT_GAME_INFO["title_id"] = title_id_hex
        CURRENT_GAME_INFO["media_id"] = media_id_hex
        CURRENT_GAME_INFO["db_id"] = db_id_hex
        CURRENT_GAME_INFO["folder_path"] = f"{title_id_hex}_{db_id_hex}"

    folder = CURRENT_GAME_INFO["folder_path"]
    title_id = CURRENT_GAME_INFO["title_id"]

    if not title_id or title_id == "00000000":
        raise HTTPException(status_code=400, detail="No game selected or invalid TitleID.")

    if demo_data.is_demo_mode():
        # Reset in-memory assets so the demo placeholder previews are served for
        # the freshly selected game (unless the user has edited them this session).
        for cat in CURRENT_ASSETS:
            CURRENT_ASSETS[cat] = AuroraAssetFile()
        results = {}
        for cat, kind in (("boxart", "boxart"), ("background", "background"),
                          ("icon_banner", "icon"), ("screenshots", "screenshots")):
            present = demo_data._has_asset(title_id, kind)
            results[cat] = {"success": present, "size": 4096 if present else 0,
                            "error": None if present else "File not found on console (demo)"}
        return {"status": "complete", "game": CURRENT_GAME_INFO, "results": results}

    client = AuroraFtpClient(payload.ip, payload.username, payload.password, payload.port)
    ok, msg = client.connect()
    if not ok:
        client.disconnect()
        raise HTTPException(status_code=400, detail=msg)

    results = {}
    category_files = [
        ("boxart", f"GC{title_id}.asset"),
        ("background", f"BK{title_id}.asset"),
        ("icon_banner", f"GL{title_id}.asset"),
        ("screenshots", f"SS{title_id}.asset"),
    ]

    for cat, fname in category_files:
        raw_bytes = client.download_asset_file(folder, fname)
        if raw_bytes and len(raw_bytes) >= 64:
            try:
                parsed_asset = AuroraAssetFile(raw_bytes)
                CURRENT_ASSETS[cat] = parsed_asset
                cache_asset_file(folder, title_id, cat, parsed_asset)
                results[cat] = {"success": True, "size": len(raw_bytes), "summary": parsed_asset.get_summary()}
            except Exception as e:
                results[cat] = {"success": False, "error": f"Parse error: {str(e)}"}
        else:
            results[cat] = {"success": False, "error": "File not found on console"}

    client.disconnect()
    return {"status": "complete", "game": CURRENT_GAME_INFO, "results": results}

class BatchDownloadModel(BaseModel):
    ip: str = ""
    username: str = "xboxftp"
    password: str = "xboxftp"
    port: int = 21
    games: List[Dict[str, Any]] = []
    force: bool = False

@app.post("/api/ftp/download-all-missing-assets")
def ftp_download_all_missing_assets(payload: BatchDownloadModel):
    """Iterates through game list and downloads missing asset files from Xbox console via FTP."""
    if demo_data.is_demo_mode():
        return {
            "status": "success",
            "processed_games": len(payload.games),
            "downloaded_assets": len(payload.games) * 2,
            "message": f"Demo mode: simulated downloading missing assets for {len(payload.games)} games."
        }

    if not payload.ip:
        raise HTTPException(status_code=400, detail="Xbox console FTP IP address is required.")

    games_needing_download = []
    for game in payload.games:
        title_id = game.get("title_id", "").strip().upper().zfill(8)
        db_id = game.get("db_id", "00000001").strip().upper().zfill(8)
        if not title_id or title_id == "00000000":
            continue
        cache_key = get_game_cache_key(title_id, db_id, game.get("folder_path"))
        
        # If not forcing, auto-generate missing PNG previews from existing local .asset files first
        for cat in ["boxart", "background", "icon_banner", "screenshots"]:
            cached_asset = load_cached_asset(cache_key, title_id, cat)
            if cached_asset and not get_cached_png_bytes(cache_key, cat, 0):
                cache_asset_file(cache_key, title_id, cat, cached_asset)

        if payload.force:
            games_needing_download.append(game)
        else:
            missing = False
            for cat in ["boxart", "background", "icon_banner", "screenshots"]:
                if not load_cached_asset(cache_key, title_id, cat):
                    missing = True
                    break
            if missing:
                games_needing_download.append(game)

    if not games_needing_download:
        return {
            "status": "success",
            "processed_games": len(payload.games),
            "downloaded_assets": 0,
            "message": f"All {len(payload.games)} games already have their assets downloaded locally! 0 files needed to be fetched."
        }

    client = AuroraFtpClient(payload.ip, payload.username, payload.password, payload.port)
    ok, msg = client.connect()
    if not ok:
        client.disconnect()
        raise HTTPException(status_code=400, detail=msg)

    downloaded_count = 0
    processed_games = 0

    for game in games_needing_download:
        title_id = game.get("title_id", "").strip().upper().zfill(8)
        db_id = game.get("db_id", "00000001").strip().upper().zfill(8)
        folder = f"{title_id}_{db_id}"
        cache_key = get_game_cache_key(title_id, db_id, game.get("folder_path"))
        processed_games += 1

        category_files = [
            ("boxart", f"GC{title_id}.asset"),
            ("background", f"BK{title_id}.asset"),
            ("icon_banner", f"GL{title_id}.asset"),
            ("screenshots", f"SS{title_id}.asset"),
        ]

        for cat, fname in category_files:
            if payload.force or not load_cached_asset(cache_key, title_id, cat):
                raw_bytes = client.download_asset_file(folder, fname)
                if raw_bytes and len(raw_bytes) >= 64:
                    try:
                        parsed_asset = AuroraAssetFile(raw_bytes)
                        cache_asset_file(cache_key, title_id, cat, parsed_asset)
                        downloaded_count += 1
                    except Exception:
                        pass

    client.disconnect()
    return {
        "status": "success",
        "processed_games": processed_games,
        "downloaded_assets": downloaded_count,
        "message": f"Scanned {len(payload.games)} games. Downloaded and cached {downloaded_count} asset files from Xbox console!"
    }

@app.post("/api/ftp/detect-changes")
def ftp_detect_changes(payload: BatchDownloadModel):
    """
    Scans games for drift between local state and the console, so edits that
    somehow didn't make it into the pending queue (or that happened outside
    ABAM entirely -- e.g. someone renamed a title from Aurora's own UI) still
    show up as pending. Two things are compared per game:
      - Title name: the console's current CustomTitleName vs. what the caller
        believes is the local name.
      - Each asset category: the locally cached .asset bytes vs. what's
        actually on the console right now (byte-for-byte).
    Only flags a category when there's local cached data to compare -- a game
    with nothing cached locally has nothing to detect drift against.
    """
    if demo_data.is_demo_mode():
        return {"status": "success", "games": [], "message": "Demo mode: nothing to detect against a real console."}

    if not payload.ip:
        raise HTTPException(status_code=400, detail="Xbox console FTP IP address is required.")

    client = AuroraFtpClient(payload.ip, payload.username, payload.password, payload.port)
    ok, msg = client.connect()
    if not ok:
        client.disconnect()
        raise HTTPException(status_code=400, detail=msg)

    # Pull Content.db once up front so we can check every game's title name
    # without a separate round-trip per game.
    console_titles_by_db_id = {}
    console_titles_by_title_id = {}
    temp_dir = tempfile.gettempdir()
    db_path = os.path.join(temp_dir, "aurora_content_detect.db")
    db_ok, db_msg = client.download_content_db(db_path)
    if db_ok:
        try:
            for item in parse_content_db(db_path):
                console_titles_by_db_id[item.db_id.upper()] = item.title_name
                console_titles_by_title_id[item.title_id.upper()] = item.title_name
        except Exception as e:
            print(f"detect-changes: failed to parse pulled Content.db: {e}")

    category_files = [
        ("boxart", "GC"), ("background", "BK"), ("icon_banner", "GL"), ("screenshots", "SS"),
    ]

    results = []
    try:
        for game in payload.games:
            title_id = (game.get("title_id") or "").strip().upper().zfill(8)
            if not title_id or title_id == "00000000":
                continue
            db_id = (game.get("db_id") or "00000001").strip().upper().zfill(8)
            folder = game.get("folder_path") or f"{title_id}_{db_id}"
            cache_key = get_game_cache_key(title_id, db_id, game.get("folder_path"))
            local_title_name = game.get("title_name") or ""

            changes = []

            console_title = console_titles_by_db_id.get(db_id) or console_titles_by_title_id.get(title_id)
            if console_title and local_title_name and console_title.strip() != local_title_name.strip():
                changes.append({"category": "title", "console_value": console_title, "local_value": local_title_name})

            for cat, prefix in category_files:
                cached_asset = load_cached_asset(cache_key, title_id, cat)
                if not cached_asset:
                    continue
                has_local_data = cached_asset.data_size > 0 or any(e.size > 0 for e in cached_asset.entries)
                if not has_local_data:
                    continue
                try:
                    local_bytes = cached_asset.pack()
                except Exception:
                    continue
                console_bytes = client.download_asset_file(folder, f"{prefix}{title_id}.asset")
                if console_bytes is None or console_bytes != local_bytes:
                    changes.append({"category": cat})

            if changes:
                results.append({
                    "title_id": title_id, "db_id": db_id, "title_name": local_title_name,
                    "changes": changes,
                })
    finally:
        client.disconnect()

    total_changes = sum(len(g["changes"]) for g in results)
    return {
        "status": "success",
        "games": results,
        "scanned": len(payload.games),
        "message": (
            f"Scanned {len(payload.games)} game(s): found {total_changes} change(s) across {len(results)} game(s) not on the console yet."
            if results else
            f"Scanned {len(payload.games)} game(s): everything matches the console."
        ),
    }

@app.post("/api/ftp/push-all-assets")
def ftp_push_all_assets(payload: BatchDownloadModel):
    """Pushes all locally cached asset files across all games in the library to Xbox console via FTP."""
    if demo_data.is_demo_mode():
        return {
            "status": "success",
            "games_pushed": len(payload.games),
            "total_files_uploaded": len(payload.games) * 4,
            "message": f"Demo mode: simulated pushing assets for {len(payload.games)} games."
        }

    if not payload.ip:
        raise HTTPException(status_code=400, detail="Xbox console FTP IP address is required.")

    client = AuroraFtpClient(payload.ip, payload.username, payload.password, payload.port)
    ok, msg = client.connect()
    if not ok:
        client.disconnect()
        raise HTTPException(status_code=400, detail=msg)

    total_uploaded = 0
    games_pushed = 0

    try:
        for game in payload.games:
            title_id = game.get("title_id", "").strip().upper().zfill(8)
            db_id = game.get("db_id", "00000001").strip().upper().zfill(8)
            if not title_id or title_id == "00000000":
                continue

            folder = f"{title_id}_{db_id}"
            game_uploaded = 0

            category_files = [
                ("boxart", f"GC{title_id}.asset"),
                ("background", f"BK{title_id}.asset"),
                ("icon_banner", f"GL{title_id}.asset"),
                ("screenshots", f"SS{title_id}.asset"),
            ]

            for cat, fname in category_files:
                asset_obj = None
                if folder == CURRENT_GAME_INFO.get("folder_path"):
                    asset_obj = CURRENT_ASSETS.get(cat)

                if not asset_obj or (asset_obj.data_size == 0 and not any(e.size > 0 for e in asset_obj.entries)):
                    asset_obj = load_cached_asset(folder, title_id, cat)

                if asset_obj and (asset_obj.data_size > 0 or any(e.size > 0 for e in asset_obj.entries)):
                    data = asset_obj.pack()
                    succ, umsg = client.upload_asset_file(folder, fname, data)
                    if succ:
                        game_uploaded += 1
                        total_uploaded += 1

            if game_uploaded > 0:
                games_pushed += 1
    finally:
        client.disconnect()

    return {
        "status": "success",
        "games_pushed": games_pushed,
        "total_files_uploaded": total_uploaded,
        "message": f"Pushed {total_uploaded} asset file(s) across {games_pushed} game(s) to Xbox console!"
    }

class SingleGameDownloadModel(BaseModel):
    ip: str = ""
    username: str = "xboxftp"
    password: str = "xboxftp"
    port: int = 21
    title_id: str
    db_id: str = "00000001"
    title_name: Optional[str] = None
    force: bool = False

@app.post("/api/ftp/download-game-missing-assets")
def ftp_download_single_game_missing_assets(payload: SingleGameDownloadModel):
    """Downloads asset files for a single game from Xbox console via FTP."""
    title_id = payload.title_id.strip().upper().zfill(8)
    db_id = payload.db_id.strip().upper().zfill(8)
    if not title_id or title_id == "00000000":
        return {"status": "skipped", "downloaded": 0, "reason": "Invalid TitleID"}

    if demo_data.is_demo_mode():
        downloaded = sum(1 for kind in ("boxart", "background", "icon", "screenshots")
                         if demo_data._has_asset(title_id, kind))
        return {"status": "success", "title_id": title_id, "downloaded": downloaded}

    folder = f"{title_id}_{db_id}"
    cache_key = get_game_cache_key(title_id, db_id, folder)
    category_files = [
        ("boxart", f"GC{title_id}.asset"),
        ("background", f"BK{title_id}.asset"),
        ("icon_banner", f"GL{title_id}.asset"),
        ("screenshots", f"SS{title_id}.asset"),
    ]

    # Auto-generate missing local PNG previews if .asset file exists locally
    for cat, fname in category_files:
        cached_asset = load_cached_asset(cache_key, title_id, cat)
        if cached_asset and not get_cached_png_bytes(cache_key, cat, 0):
            cache_asset_file(cache_key, title_id, cat, cached_asset)

    missing_categories = []
    for cat, fname in category_files:
        if payload.force or not load_cached_asset(cache_key, title_id, cat):
            missing_categories.append((cat, fname))

    # Skip connecting to FTP if all assets already exist locally and force is False
    if not missing_categories:
        return {"status": "skipped", "title_id": title_id, "downloaded": 0, "reason": "All assets already cached locally"}

    client = AuroraFtpClient(payload.ip, payload.username, payload.password, payload.port)
    ok, msg = client.connect()
    if not ok:
        client.disconnect()
        raise HTTPException(status_code=400, detail=msg)

    downloaded = 0
    for cat, fname in missing_categories:
        raw_bytes = client.download_asset_file(folder, fname)
        if raw_bytes and len(raw_bytes) >= 64:
            try:
                parsed_asset = AuroraAssetFile(raw_bytes)
                cache_asset_file(cache_key, title_id, cat, parsed_asset)
                downloaded += 1
            except Exception:
                pass

    client.disconnect()
    return {"status": "success", "title_id": title_id, "downloaded": downloaded}

@app.post("/api/cache/clear")
def clear_local_asset_cache():
    """Clears all locally cached game assets."""
    count = clear_cache()
    return {"status": "success", "cleared_files": count}

@app.get("/api/search/unity")
def search_xbox_unity(query: str):
    """Queries Xbox Unity API for covers."""
    results = XboxUnityClient.search_covers(query)
    return {"query": query, "count": len(results), "results": results}

@app.get("/api/search/media")
def search_online_media(query: str, category: str = "boxart"):
    """Queries online media sources for boxart, background, icon_banner, or screenshots."""
    results = XboxUnityClient.search_media(query, category=category)
    return {"query": query, "category": category, "count": len(results), "results": results}

@app.get("/api/search/archive")
def search_internet_archive(title_id: str):
    """Queries Internet Archive backup dump."""
    results = InternetArchiveClient.get_covers(title_id)
    return {"title_id": title_id, "count": len(results), "results": results}

@app.get("/api/search/xboxlive")
def search_xbox_live(title_id: str, locale: str = "en-US"):
    """Queries Xbox Live Marketplace CDN catalog."""
    result = XboxLiveClient.get_title_assets(title_id, locale=locale)
    return result
