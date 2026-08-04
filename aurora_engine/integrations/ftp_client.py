"""
Aurora Xbox 360 FTP Client
Connects to Xbox 360 console running Aurora dashboard, handles SITE REVISION check,
downloads Content.db, and syncs asset files.
"""

from ftplib import FTP, error_perm
import io
import json
import os
from typing import List, Optional, Tuple

LOCKED_DB_HINT = (
    "Aurora currently has Content.db open/locked, so it can't be read over FTP. "
    "Please exit Aurora on the console -- into a game, a homebrew app, or the "
    "default dashboard -- and try again."
)

def _is_lock_error(exc: Exception) -> bool:
    """Best-effort detection of a 'file is locked/in use' FTP failure, as opposed
    to a genuine connection/permission/missing-file problem. The Xbox 360 FTP
    servers used by Aurora (ftpdll/slimftpd-derived) report this as a 550
    permission-denied response while Aurora itself holds Content.db open."""
    if isinstance(exc, error_perm):
        return True
    msg = str(exc).lower()
    return any(kw in msg for kw in ("550", "lock", "being used", "sharing violation", "access is denied"))

class AuroraFtpClient:
    def __init__(self, ip: str = "", username: str = "xbox", password: str = "xbox", port: int = 7564):
        self.ip = ip
        self.username = username
        self.password = password
        self.port = port
        self.ftp: Optional[FTP] = None
        self._aurora_root_cache: Optional[str] = None
        self.load_settings()

    def load_settings(self):
        """Loads FTP settings from local ftp.json configuration file if available."""
        config_path = os.path.expanduser("~/.aurora_asset_editor/ftp.json")
        if os.path.exists(config_path):
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    self.ip = cfg.get("ip", self.ip)
                    self.username = cfg.get("username", self.username)
                    self.password = cfg.get("password", self.password)
                    self.port = int(cfg.get("port", self.port or 7564))
            except Exception as e:
                print(f"Error reading ftp.json: {e}")

    def save_settings(self, ip: str, username: str, password: str, port: int):
        """Saves FTP settings to user home folder."""
        self.ip = ip.strip()
        self.username = username.strip()
        self.password = password.strip()
        self.port = port

        config_dir = os.path.expanduser("~/.aurora_asset_editor")
        os.makedirs(config_dir, exist_ok=True)
        config_path = os.path.join(config_dir, "ftp.json")

        with open(config_path, "w", encoding="utf-8") as f:
            json.dump({
                "ip": self.ip,
                "username": self.username,
                "password": self.password,
                "port": self.port
            }, f, indent=2)

    def connect(self) -> Tuple[bool, str]:
        """Establishes FTP connection and verifies Aurora dashboard via SITE REVISION."""
        if not self.ip:
            return False, "IP address is empty. Please enter your Xbox 360 console IP address."

        try:
            self.ftp = FTP()
            self.ftp.connect(self.ip, self.port, timeout=6)
            if self.username:
                self.ftp.login(self.username, self.password)
            else:
                self.ftp.login()  # Try pure anonymous login if no username provided
            self.ftp.set_pasv(True)

            # Test Aurora site revision command
            try:
                reply = self.ftp.sendcmd("SITE REVISION")
                return True, f"Connected to Aurora! {reply}"
            except Exception:
                return True, "Connected to FTP server (SITE REVISION command not returned)."
        except TimeoutError:
            self.ftp = None
            return False, f"Connection timed out. Check if Xbox console is powered on and IP '{self.ip}' is correct."
        except Exception as e:
            self.ftp = None
            return False, f"Connection failed: {str(e)}"

    def is_connected(self) -> bool:
        if not self.ftp:
            return False
        try:
            self.ftp.voidcmd("NOOP")
            return True
        except Exception:
            return False

    def ensure_connected(self) -> Tuple[bool, str]:
        if not self.is_connected():
            return self.connect()
        return True, "Already connected."

    def _check_flash_safety(self, path: str):
        if "flash" in str(path).lower():
            raise Exception("SECURITY BLOCK: Attempted to access Xbox Flash memory. This path is strictly blocklisted to prevent console bricks.")

    def _get_aurora_root(self) -> str:
        log_file = os.path.expanduser("~/.aurora_asset_editor/ftp_scan.log")
        def debug_log(msg):
            try:
                with open(log_file, "a") as f:
                    f.write(msg + "\n")
            except: pass

        debug_log("=== STARTING _get_aurora_root ===")

        if self._aurora_root_cache:
            self._check_flash_safety(self._aurora_root_cache)
            debug_log(f"Using cache: {self._aurora_root_cache}")
            return self._aurora_root_cache
            
        # 1. Dynamic shallow scan of physical bypass drives (fHdd, fUsb0) to find exact Aurora version folders
        for drive in ["/fHdd", "/fUsb0", "/Hdd1", "/Usb0"]:
            try:
                self._check_flash_safety(drive)
                
                # Check root level and common subdirectories
                dirs_to_scan = [drive, f"{drive}/Apps", f"{drive}/Games", f"{drive}/Applications"]
                for scan_dir in dirs_to_scan:
                    try:
                        self.ftp.cwd(scan_dir)
                        folders = self.ftp.nlst()
                        debug_log(f"Scanned {scan_dir}, found {len(folders)} items")
                        for folder in folders:
                            debug_log(f"  Raw item: {folder}")
                            folder = folder.replace('\\', '/').rstrip('/')
                            folder_name = os.path.basename(folder)
                            if "aurora" in folder_name.lower() or "freestyle" in folder_name.lower():
                                test_path = f"{scan_dir}/{folder_name}"
                                debug_log(f"  Matched Aurora folder! Trying test_path: {test_path}")
                                try:
                                    self.ftp.cwd(test_path + "/Data/DataBases")
                                    self._aurora_root_cache = test_path
                                    debug_log(f"  SUCCESS! Returning {test_path}")
                                    return test_path
                                except Exception as e:
                                    debug_log(f"  FAILED cwd to {test_path + '/Data/DataBases'}: {e}")
                                    # Restore directory to continue scanning
                                    self.ftp.cwd(scan_dir)
                    except Exception as e:
                        debug_log(f"Failed to scan {scan_dir}: {e}")
            except Exception as e:
                debug_log(f"Failed on drive {drive}: {e}")
                continue

        # 2. Check common hardcoded physical paths as a fallback
        common_paths = [
            "/fHdd/Aurora", "/fHdd/Apps/Aurora", "/fHdd/Games/Aurora", "/fHdd/Freestyle",
            "/Hdd1/Aurora", "/Hdd1/Apps/Aurora", "/Hdd1/Games/Aurora", "/Hdd1/Freestyle",
            "/fUsb0/Aurora", "/fUsb0/Apps/Aurora", "/Usb0/Aurora", "/Usb0/Apps/Aurora"
        ]
        debug_log("Dynamic scan failed. Falling back to common_paths.")
        for p in common_paths:
            try:
                self._check_flash_safety(p)
                self.ftp.cwd(p + "/Data/DataBases")
                self._aurora_root_cache = p
                debug_log(f"SUCCESS in common_paths! Returning {p}")
                return p
            except Exception:
                continue

        # 3. Fallback to the virtual /Game/ mount (often read-only or volatile on ftpdll)
        try:
            self.ftp.cwd("/Game/Data/DataBases")
            self._aurora_root_cache = "/Game"
            return "/Game"
        except Exception:
            pass

        self._aurora_root_cache = "/Game"
        return "/Game"

    def download_content_db(self, destination_path: str) -> Tuple[bool, str]:
        """Downloads Content.db and related database files from Xbox console path /Game/Data/DataBases/"""
        ok, msg = self.ensure_connected()
        if not ok:
            return False, msg

        try:
            db_dir = f"{self._get_aurora_root()}/Data/DataBases"
            self.ftp.cwd(db_dir)

            dest_dir = os.path.dirname(destination_path) or tempfile.gettempdir()

            # 1. Download Content.db directly to destination_path
            try:
                with open(destination_path, "wb") as f:
                    self.ftp.retrbinary("RETR Content.db", f.write)
            except Exception as e:
                if _is_lock_error(e):
                    return False, f"{LOCKED_DB_HINT}\nFTP error: {e}"
                raise

            # 2. Download any extra .db files (User.db, Aurora.db) to dest_dir
            try:
                files = self.ftp.nlst()
                for fname in files:
                    if fname.lower().endswith(".db") and fname.lower() != "content.db":
                        out_p = os.path.join(dest_dir, fname)
                        with open(out_p, "wb") as out_f:
                            self.ftp.retrbinary(f"RETR {fname}", out_f.write)
            except Exception as e:
                print("Note downloading extra db files:", e)

            return True, "Content.db successfully downloaded from Xbox console!"
        except Exception as e:
            if _is_lock_error(e):
                return False, f"{LOCKED_DB_HINT}\nFTP error: {e}"
            return False, f"Failed to download Content.db: {str(e)}"

    def download_asset_file(self, folder_path: str, filename: str) -> Optional[bytes]:
        """Downloads specified asset file from /Game/Data/GameData/<folder_path>/<filename>"""
        ok, _ = self.ensure_connected()
        if not ok:
            return None

        try:
            target_dir = f"{self._get_aurora_root()}/Data/GameData/{folder_path}"
            self.ftp.cwd(target_dir)

            buf = io.BytesIO()
            self.ftp.retrbinary(f"RETR {filename}", buf.write)
            return buf.getvalue()
        except Exception as e:
            print(f"Error downloading asset {filename} from {folder_path}: {e}")
            return None

    def upload_asset_file(self, folder_path: str, filename: str, data: bytes) -> Tuple[bool, str]:
        """Uploads asset file bytes to /Game/Data/GameData/<folder_path>/<filename> and clears stale texture caches."""
        ok, msg = self.ensure_connected()
        if not ok:
            return False, msg

        try:
            target_dir = f"{self._get_aurora_root()}/Data/GameData/{folder_path}"
            try:
                self.ftp.cwd(target_dir)
            except Exception:
                # Directory may need to be created
                self._mkd_recursive(target_dir)
                self.ftp.cwd(target_dir)

            buf = io.BytesIO(data)
            self.ftp.storbinary(f"STOR {filename}", buf)

            # Purge any stale cached PNG/DDS renders for this asset (e.g. GC<TitleID>.png)
            base_name = os.path.splitext(filename)[0]
            for ext in [".png", ".dds", ".cache", ".bmp"]:
                try:
                    self.ftp.delete(f"{base_name}{ext}")
                except Exception:
                    pass

            return True, f"Successfully uploaded {filename}!"
        except Exception as e:
            return False, f"Upload failed: {str(e)}"

    def _mkd_recursive(self, path: str):
        """Recursively creates remote FTP directory structure if missing."""
        parts = path.strip("/").split("/")
        curr = ""
        for part in parts:
            if not part: continue
            curr += f"/{part}"
            try:
                self.ftp.cwd(curr)
            except Exception:
                try:
                    self.ftp.mkd(curr)
                    self.ftp.cwd(curr)
                except Exception:
                    pass

    def pull_title_name(self, destination_path: str) -> Tuple[bool, str]:
        """Downloads Content.db from the console to read the current title name."""
        return self.download_content_db(destination_path)

    def push_title_name(
        self, title_id: int, new_name: str, destination_path: str,
        db_id: Optional[int] = None, description: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Downloads Content.db, updates the title name (and optionally the synopsis)
        for the given Aurora row in whatever column / table Aurora uses on this
        build, then uploads the modified DB back.

        Strategy (in priority order):
          1. Update CustomTitleName / UserTitleName / CustomName / TitleName in ContentItems
          2. Upsert a row in CustomData / ContentCustomData / UserTitles / TitleOverrides
             (Aurora reads these tables to override the displayed title)

        ``description``, if given, is written best-effort to a Description /
        Synopsis / Summary column on ContentItems if the build's schema has
        one. Not every Aurora build exposes a synopsis field, so failure to
        write it does not fail the whole push -- only the title write is
        required.
        """
        import sqlite3

        ok, msg = self.download_content_db(destination_path)
        if not ok:
            return False, f"Could not download Content.db: {msg}"

        # Prefer columns that Aurora treats as user-editable overrides
        TITLE_COLS_PRIORITY = [
            "CustomTitleName", "UserTitleName", "CustomName",
            "TitleName", "Name", "Title"
        ]
        # Tables where Aurora stores user-supplied custom names (tried in order)
        CUSTOM_TABLES = [
            "CustomData", "ContentCustomData", "UserTitles",
            "TitleOverrides", "ContentOverrides",
        ]

        title_id_hex = f"{title_id & 0xFFFFFFFF:08X}"
        db_id_hex = f"{db_id & 0xFFFFFFFF:08X}" if db_id is not None else ""
        written = False
        detail = ""

        try:
            conn = sqlite3.connect(destination_path)
            cursor = conn.cursor()

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
            real_tables = [row[0] for row in cursor.fetchall()]

            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' OR type='view'")
            tables = [row[0] for row in cursor.fetchall()]

            # ── Strategy 1: update column in ContentItems / real database table ──────────
            main_table = "ContentItems" if "ContentItems" in real_tables else (
                next((t for t in real_tables if "Content" in t or "Title" in t), None)
            )
            if main_table:
                cursor.execute(f"PRAGMA table_info({main_table})")
                cols = [r[1] for r in cursor.fetchall()]
                write_col = next((c for c in TITLE_COLS_PRIORITY if c in cols), None)

                if write_col:
                    # Prefer Aurora's unique row ID when available; fall back to TitleId.
                    match_targets = []
                    if db_id is not None:
                        for candidate in ["Id", "ContentId", "DbId", "DatabaseId"]:
                            if candidate in cols:
                                match_targets.append((candidate, db_id, db_id_hex))
                                break
                    for candidate in ["TitleId", "ContentId", "Id"]:
                        if candidate in cols:
                            target = (candidate, title_id, title_id_hex)
                            if target not in match_targets:
                                match_targets.append(target)
                            break

                    for id_col, raw_value, hex_value in match_targets:
                        cursor.execute(
                            f"UPDATE {main_table} SET {write_col} = ? WHERE {id_col} = ?",
                            (new_name, raw_value)
                        )
                        if cursor.rowcount == 0 and hex_value:
                            cursor.execute(
                                f"UPDATE {main_table} SET {write_col} = ? WHERE UPPER(HEX({id_col})) = ?",
                                (new_name, hex_value)
                            )
                        if cursor.rowcount > 0:
                            written = True
                            detail = f"Updated '{write_col}' in {main_table} via {id_col}."
                            break

            # ── Strategy 2: upsert into a dedicated custom-names table ────────────────
            if not written:
                for ctable in CUSTOM_TABLES:
                    if ctable not in tables:
                        continue
                    cursor.execute(f"PRAGMA table_info({ctable})")
                    ccols = [r[1] for r in cursor.fetchall()]
                    cid_col = next((c for c in ["TitleId", "ContentId", "Id"] if c in ccols), None)
                    cname_col = next((c for c in TITLE_COLS_PRIORITY if c in ccols), None)
                    if not cid_col or not cname_col:
                        continue
                    use_db_id = db_id is not None and cid_col in ["Id", "ContentId", "DbId", "DatabaseId"]
                    lookup_value = db_id if use_db_id else title_id

                    # Upsert: update existing or insert new row
                    cursor.execute(
                        f"UPDATE {ctable} SET {cname_col} = ? WHERE {cid_col} = ?",
                        (new_name, lookup_value)
                    )
                    if cursor.rowcount == 0:
                        try:
                            cursor.execute(
                                f"INSERT INTO {ctable} ({cid_col}, {cname_col}) VALUES (?, ?)",
                                (lookup_value, new_name)
                            )
                        except Exception:
                            pass
                    if cursor.rowcount > 0:
                        written = True
                        detail = f"Upserted '{cname_col}' in {ctable} via {cid_col}."
                        break

            if not written:
                # Last resort: dump available tables & columns for diagnostics
                schema_info = []
                for t in tables:
                    cursor.execute(f"PRAGMA table_info({t})")
                    schema_info.append(f"{t}({', '.join(r[1] for r in cursor.fetchall())})")
                conn.close()
                return False, (
                    f"Could not find a writable title column in Content.db for TitleId {title_id_hex}.\n"
                    f"Schema: {'; '.join(schema_info)}"
                )

            description_written = False
            if description is not None:
                try:
                    desc_tables = [t for t in ["ContentItems", "ContentCustomData", "CustomData", "Titles"] if t in real_tables]
                    if not desc_tables and main_table:
                        desc_tables = [main_table]

                    for desc_table in desc_tables:
                        cursor.execute(f"PRAGMA table_info({desc_table})")
                        desc_cols = [r[1] for r in cursor.fetchall()]
                        desc_col = next((c for c in ["Description", "Synopsis", "Summary"] if c in desc_cols), None)
                        if desc_col:
                            desc_targets = []
                            if db_id is not None:
                                for candidate in ["Id", "ContentId", "DbId", "DatabaseId"]:
                                    if candidate in desc_cols:
                                        desc_targets.append((candidate, db_id, db_id_hex))
                                        break
                            for candidate in ["TitleId", "ContentId", "Id"]:
                                if candidate in desc_cols:
                                    target = (candidate, title_id, title_id_hex)
                                    if target not in desc_targets:
                                        desc_targets.append(target)
                                    break
                            for id_col, raw_value, hex_value in desc_targets:
                                cursor.execute(
                                    f"UPDATE {desc_table} SET {desc_col} = ? WHERE {id_col} = ?",
                                    (description, raw_value)
                                )
                                if cursor.rowcount == 0 and hex_value:
                                    cursor.execute(
                                        f"UPDATE {desc_table} SET {desc_col} = ? WHERE UPPER(HEX({id_col})) = ?",
                                        (description, hex_value)
                                    )
                                if cursor.rowcount > 0:
                                    description_written = True
                                    break
                        if description_written:
                            break
                except Exception as e:
                    print(f"Note updating description: {e}")

            conn.commit()
            conn.close()

        except Exception as e:
            return False, f"Failed to modify Content.db locally: {e}"

        # Upload the modified database back to the console.
        # Aurora holds Content.db open while running, so we can't overwrite it directly
        # (FTP 550 "Could not create file"). Strategy:
        #   1. STOR to a temp name Content.db.new
        #   2. Try SITE CHMOD 666 or just RNFR/RNTO to swap it in atomically
        #   3. If rename also fails, return the local path so caller can offer a download
        db_dir = f"{self._get_aurora_root()}/Data/DataBases"
        temp_name = "Content.db.new"
        try:
            self.ftp.cwd(db_dir)
        except Exception as e:
            return False, f"Local DB updated, but could not navigate to {db_dir} on console: {e}\nLocal file: {destination_path}"

        # Step 1: Upload to temp name
        try:
            with open(destination_path, "rb") as f:
                self.ftp.storbinary(f"STOR {temp_name}", f)
        except Exception as e:
            return False, (
                f"Local DB updated successfully, but FTP upload blocked.\n"
                f"{LOCKED_DB_HINT}\n"
                f"Or manually copy: {destination_path} → {db_dir}/Content.db\n"
                f"FTP error: {e}"
            )

        # Step 2: Rename temp → Content.db
        try:
            # slimftpd (ftpdll) does not support overwriting existing files via RENAME, so we must delete first
            try:
                self.ftp.delete("Content.db")
            except Exception:
                pass
            self.ftp.rename(temp_name, "Content.db")
            desc_note = ""
            if description is not None:
                desc_note = " Synopsis updated too." if description_written else " (No synopsis column on this Aurora build -- synopsis not pushed.)"
            return True, f"Title updated to '{new_name}' and Content.db pushed to console! ({detail}){desc_note}"
        except Exception as rename_err:
            # Rename failed — temp file is on console but not active
            # Try deleting the orphaned temp file silently
            try:
                self.ftp.delete(temp_name)
            except Exception:
                pass
            return False, (
                f"Uploaded temp file but rename failed -- Aurora still has Content.db locked.\n"
                f"{LOCKED_DB_HINT}\n"
                f"Or manually copy: {destination_path} → {db_dir}/Content.db\n"
                f"Rename error: {rename_err}"
            )

    def disconnect(self):
        if self.ftp:
            try:
                self.ftp.quit()
            except Exception:
                pass
            self.ftp = None
