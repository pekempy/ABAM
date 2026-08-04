"""
Aurora Database Manager
Parses SQLite Content.db files downloaded from Xbox 360 Aurora consoles.
"""

import os
import sqlite3
from typing import Dict, List, Optional

class ContentItem:
    def __init__(
        self,
        db_id: int,
        title_id: int,
        media_id: int,
        disc_num: int,
        title_name: str,
        description: str = "",
        publisher: str = "",
        developer: str = "",
        release_date: str = "",
    ):
        self.db_id_raw = db_id
        self.title_id_raw = title_id
        self.media_id_raw = media_id
        self.disc_num = max(1, disc_num)
        self.title_name = title_name or "Unknown Title"
        self.description = description or ""
        self.publisher = publisher or ""
        self.developer = developer or ""
        self.release_date = release_date or ""

        self.db_id = f"{db_id & 0xFFFFFFFF:08X}"
        self.title_id = f"{title_id & 0xFFFFFFFF:08X}"
        self.media_id = f"{media_id & 0xFFFFFFFF:08X}"

    @property
    def folder_path(self) -> str:
        """Xbox console GameData folder name format: <TitleId>_<DbId>"""
        return f"{self.title_id}_{self.db_id}"

    @property
    def boxart_filename(self) -> str:
        return f"GC{self.title_id}.asset"

    @property
    def background_filename(self) -> str:
        return f"BK{self.title_id}.asset"

    @property
    def icon_banner_filename(self) -> str:
        return f"GL{self.title_id}.asset"

    @property
    def screenshots_filename(self) -> str:
        return f"SS{self.title_id}.asset"

    def to_dict(self) -> Dict:
        return {
            "title_name": self.title_name,
            "description": self.description,
            "publisher": self.publisher,
            "developer": self.developer,
            "release_date": self.release_date,
            "title_id": self.title_id,
            "media_id": self.media_id,
            "db_id": self.db_id,
            "disc_num": self.disc_num,
            "folder_path": self.folder_path,
            "boxart_file": self.boxart_filename,
            "background_file": self.background_filename,
            "icon_banner_file": self.icon_banner_filename,
            "screenshots_file": self.screenshots_filename,
        }

def parse_content_db(db_path: str) -> List[ContentItem]:
    """Reads SQLite database file(s) and returns a list of ContentItems with custom title names."""
    if not os.path.exists(db_path):
        raise FileNotFoundError(f"Content database file not found at: {db_path}")

    # Inspect all .db files in the same directory (e.g. Content.db, User.db, Aurora.db)
    db_dir = os.path.dirname(db_path)
    db_files = [db_path]
    if db_dir and os.path.exists(db_dir):
        for f in os.listdir(db_dir):
            full_p = os.path.join(db_dir, f)
            if f.endswith(".db") and full_p not in db_files:
                db_files.append(full_p)

    custom_titles_by_db_id = {}
    custom_titles_by_title_id = {}

    # Step 1: Gather custom titles from all database files
    for db_f in db_files:
        try:
            conn = sqlite3.connect(db_f)
            cursor = conn.cursor()
            cursor.execute("SELECT name FROM sqlite_master WHERE type='table' OR type='view'")
            tables = [row[0] for row in cursor.fetchall()]

            for ctable in ["CustomData", "ContentCustomData", "UserTitles", "ContentOverrides", "TitleOverrides"]:
                if ctable in tables:
                    cursor.execute(f"PRAGMA table_info({ctable})")
                    ccols = [r[1] for r in cursor.fetchall()]
                    cid_col = next((c for c in ["TitleId", "ContentId", "Id"] if c in ccols), "")
                    cname_col = next((c for c in ["CustomTitleName", "UserTitleName", "TitleName", "CustomName", "Name"] if c in ccols), "")
                    if cid_col and cname_col:
                        try:
                            cursor.execute(f"SELECT {cid_col}, {cname_col} FROM {ctable} WHERE {cname_col} IS NOT NULL AND {cname_col} != ''")
                            for cid, cname in cursor.fetchall():
                                if cid and cname and str(cname).strip() != "Unknown Game":
                                    clean_name = str(cname).replace('\x00', '').replace('\u200b', '').strip()
                                    target_map = custom_titles_by_title_id if cid_col == "TitleId" else custom_titles_by_db_id
                                    if isinstance(cid, int):
                                        hex_id = f"{cid & 0xFFFFFFFF:08X}"
                                        target_map[hex_id.upper()] = clean_name
                                    target_map[str(cid).strip().upper()] = clean_name
                        except Exception:
                            pass
            conn.close()
        except Exception as e:
            print(f"Note inspecting db {db_f}: {e}")

    # Step 2: Query main ContentItems records
    items = []
    conn = sqlite3.connect(db_path)
    try:
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' OR type='view'")
        tables = [row[0] for row in cursor.fetchall()]

        main_table = next((candidate for candidate in ["ContentItems", "ContentItemsView", "Titles"] if candidate in tables), None)
        if main_table is None:
            return items

        cursor.execute(f"PRAGMA table_info({main_table})")
        cols = [row[1] for row in cursor.fetchall()]

        db_id_col = next((c for c in ["Id", "ContentId", "DbId", "DatabaseId"] if c in cols), "Id")
        title_id_col = next((c for c in ["TitleId", "TitleID"] if c in cols), "TitleId")
        media_id_col = next((c for c in ["MediaId", "MediaID"] if c in cols), "MediaId")
        disc_num_col = next((c for c in ["DiscNum", "Disc", "DiscNumber"] if c in cols), None)

        name_cols = [c for c in ["CustomTitleName", "UserTitleName", "CustomName", "Name", "TitleName", "Title"] if c in cols]
        if name_cols:
            coalesce_clause = ", ".join([f"NULLIF({c}, '')" for c in name_cols])
            title_expr = f"COALESCE({coalesce_clause}, 'Unknown Game')"
        else:
            title_expr = "'Unknown Game'"

        description_col = next((c for c in ["Description", "Synopsis", "Summary"] if c in cols), None)
        publisher_col = next((c for c in ["Publisher"] if c in cols), None)
        developer_col = next((c for c in ["Developer"] if c in cols), None)
        release_date_col = next((c for c in ["ReleaseDate", "Release_Date"] if c in cols), None)

        select_cols = [db_id_col, title_id_col, media_id_col]
        if disc_num_col:
            select_cols.append(disc_num_col)
        else:
            select_cols.append("1 AS DiscNum")
        select_cols.append(title_expr)
        select_cols.append(description_col if description_col else "'' AS Description")
        select_cols.append(publisher_col if publisher_col else "'' AS Publisher")
        select_cols.append(developer_col if developer_col else "'' AS Developer")
        select_cols.append(release_date_col if release_date_col else "'' AS ReleaseDate")

        query = f"SELECT {', '.join(select_cols)} FROM {main_table}"
        cursor.execute(query)
        rows = cursor.fetchall()

        for row in rows:
            db_id, title_id, media_id, disc_num, default_title_name, description, publisher, developer, release_date = row

            db_id_hex = f"{db_id & 0xFFFFFFFF:08X}" if db_id is not None else "00000000"
            title_id_hex = f"{title_id & 0xFFFFFFFF:08X}" if title_id is not None else "00000000"

            # Check if custom title override exists
            resolved_title_name = default_title_name
            if db_id_hex.upper() in custom_titles_by_db_id:
                resolved_title_name = custom_titles_by_db_id[db_id_hex.upper()]
            elif str(db_id).upper() in custom_titles_by_db_id:
                resolved_title_name = custom_titles_by_db_id[str(db_id).upper()]
            elif title_id_hex.upper() in custom_titles_by_title_id:
                resolved_title_name = custom_titles_by_title_id[title_id_hex.upper()]
            elif str(title_id).upper() in custom_titles_by_title_id:
                resolved_title_name = custom_titles_by_title_id[str(title_id).upper()]

            item = ContentItem(
                db_id=db_id if db_id is not None else 0,
                title_id=title_id if title_id is not None else 0,
                media_id=media_id if media_id is not None else 0,
                disc_num=disc_num if disc_num is not None else 1,
                title_name=str(resolved_title_name).strip() if resolved_title_name else "Unknown Game",
                description=str(description).strip() if description else "",
                publisher=str(publisher).strip() if publisher else "",
                developer=str(developer).strip() if developer else "",
                release_date=str(release_date).strip() if release_date else "",
            )
            items.append(item)
    finally:
        conn.close()

    # Sort by title name
    items.sort(key=lambda x: x.title_name.lower())
    return items
