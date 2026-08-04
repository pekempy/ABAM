import os
import sqlite3
import tempfile
import unittest
from unittest.mock import patch, MagicMock

try:
    from fastapi.testclient import TestClient
    from aurora_engine.server import app
    HAS_TEST_CLIENT = True
except Exception:
    HAS_TEST_CLIENT = False

from aurora_engine.db_manager import parse_content_db
from aurora_engine.asset_parser import AuroraAssetFile
from aurora_engine.integrations.ftp_client import AuroraFtpClient

class TestServer(unittest.TestCase):
    def setUp(self):
        if HAS_TEST_CLIENT:
            self.client = TestClient(app)

    def test_parse_content_db_handles_missing_contentitems_table(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute("CREATE TABLE Titles (Id INTEGER, TitleId INTEGER, MediaId INTEGER, UserTitleName TEXT)")
            conn.commit()
            conn.close()

            items = parse_content_db(db_path)
            self.assertEqual(items, [])
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_status_endpoint(self):
        if not HAS_TEST_CLIENT:
            self.skipTest("FastAPI TestClient dependencies not available")
        response = self.client.get("/api/status")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("status"), "online")
        self.assertIn("game", data)

    def test_ftp_config_endpoint(self):
        if not HAS_TEST_CLIENT:
            self.skipTest("FastAPI TestClient dependencies not available")
        response = self.client.get("/api/ftp/config")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertIn("ip", data)
        self.assertIn("username", data)
        self.assertIn("port", data)

    def test_preview_endpoint_does_not_reuse_current_asset_for_other_titles(self):
        if not HAS_TEST_CLIENT:
            self.skipTest("FastAPI TestClient dependencies not available")

        response = self.client.get("/api/asset/preview/boxart/2?title=11111111")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers.get("content-type"), "image/png")
        self.assertEqual(len(response.content), 67)

    def test_preview_endpoint_uses_db_id_scoped_cache_for_shared_title_ids(self):
        if not HAS_TEST_CLIENT:
            self.skipTest("FastAPI TestClient dependencies not available")

        png_a = b"png-a"
        png_b = b"png-b"

        with patch("aurora_engine.server.get_cached_png_bytes") as mock_png, \
             patch("aurora_engine.server.load_cached_asset", return_value=None), \
             patch.dict("aurora_engine.server.CURRENT_GAME_INFO", {
                 "title_name": "Test",
                 "title_id": "545407F2",
                 "media_id": "00000000",
                 "db_id": "00000007",
                 "disc_num": 1,
                 "folder_path": "545407F2_00000007",
             }, clear=True), \
             patch.dict("aurora_engine.server.CURRENT_ASSETS", {"boxart": AuroraAssetFile(), "background": AuroraAssetFile(), "icon_banner": AuroraAssetFile(), "screenshots": AuroraAssetFile()}, clear=True):
            mock_png.side_effect = lambda cache_key, category, asset_index: png_a if cache_key == "545407F2_00000007" else (png_b if cache_key == "545407F2_0000001C" else None)

            response_a = self.client.get("/api/asset/preview/boxart/2?title=545407F2&db=00000007")
            response_b = self.client.get("/api/asset/preview/boxart/2?title=545407F2&db=0000001C")

        self.assertEqual(response_a.status_code, 200)
        self.assertEqual(response_b.status_code, 200)
        self.assertEqual(response_a.content, png_a)
        self.assertEqual(response_b.content, png_b)

    def test_push_title_name_updates_only_matching_db_id(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            source_db = os.path.join(temp_dir, "source.db")
            working_db = os.path.join(temp_dir, "working.db")

            conn = sqlite3.connect(source_db)
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE ContentItems (Id INTEGER, TitleId INTEGER, MediaId INTEGER, UserTitleName TEXT)"
            )
            shared_title_id = int("454108C0", 16)
            cursor.execute(
                "INSERT INTO ContentItems (Id, TitleId, MediaId, UserTitleName) VALUES (?, ?, ?, ?)",
                (1, shared_title_id, 0, "Dragon Age: Origins")
            )
            cursor.execute(
                "INSERT INTO ContentItems (Id, TitleId, MediaId, UserTitleName) VALUES (?, ?, ?, ?)",
                (2, shared_title_id, 0, "Dragon Age: Origins Awakening")
            )
            conn.commit()
            conn.close()

            client = AuroraFtpClient()
            client.ftp = MagicMock()

            def fake_download(destination_path):
                import shutil
                shutil.copyfile(source_db, destination_path)
                return True, "ok"

            client.download_content_db = fake_download

            ok, msg = client.push_title_name(shared_title_id, "Updated Awakening", working_db, db_id=2)

            self.assertTrue(ok, msg)

            conn = sqlite3.connect(working_db)
            cursor = conn.cursor()
            cursor.execute("SELECT Id, UserTitleName FROM ContentItems ORDER BY Id")
            rows = cursor.fetchall()
            conn.close()

            self.assertEqual(rows, [(1, "Dragon Age: Origins"), (2, "Updated Awakening")])

    def test_parse_content_db_prefers_db_id_override_for_shared_title_ids(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE ContentItems (Id INTEGER, TitleId INTEGER, MediaId INTEGER, Name TEXT)"
            )
            cursor.execute(
                "CREATE TABLE ContentCustomData (ContentId INTEGER, UserTitleName TEXT)"
            )

            shared_title_id = int("545407F2", 16)
            cursor.execute(
                "INSERT INTO ContentItems (Id, TitleId, MediaId, Name) VALUES (?, ?, ?, ?)",
                (101, shared_title_id, 0, "Grand Theft Auto IV")
            )
            cursor.execute(
                "INSERT INTO ContentItems (Id, TitleId, MediaId, Name) VALUES (?, ?, ?, ?)",
                (202, shared_title_id, 0, "Grand Theft Auto Episodes")
            )
            cursor.execute(
                "INSERT INTO ContentCustomData (ContentId, UserTitleName) VALUES (?, ?)",
                (101, "GTA IV")
            )
            cursor.execute(
                "INSERT INTO ContentCustomData (ContentId, UserTitleName) VALUES (?, ?)",
                (202, "GTA Liberty City Stories")
            )
            conn.commit()
            conn.close()

            items = parse_content_db(db_path)
            names_by_db_id = {item.db_id: item.title_name for item in items}

            self.assertEqual(names_by_db_id["00000065"], "GTA IV")
            self.assertEqual(names_by_db_id["000000CA"], "GTA Liberty City Stories")
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_parse_content_db_returns_extended_metadata_fields(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE ContentItems (Id INTEGER, TitleId INTEGER, MediaId INTEGER, DiscNum INTEGER, TitleName TEXT, Description TEXT, Publisher TEXT, Developer TEXT, ReleaseDate TEXT)"
            )
            cursor.execute(
                "INSERT INTO ContentItems (Id, TitleId, MediaId, DiscNum, TitleName, Description, Publisher, Developer, ReleaseDate) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (1, int("415608C3", 16), int("66ACD000", 16), 1, "Halo 3", "Finish the Fight", "Microsoft", "Bungie", "2007-09-25")
            )
            conn.commit()
            conn.close()

            items = parse_content_db(db_path)

            self.assertEqual(len(items), 1)
            self.assertEqual(items[0].description, "Finish the Fight")
            self.assertEqual(items[0].publisher, "Microsoft")
            self.assertEqual(items[0].developer, "Bungie")
            self.assertEqual(items[0].release_date, "2007-09-25")
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

    def test_parse_content_db_preserves_distinct_titles_from_contentitems(self):
        with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
            db_path = tmp.name

        try:
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            cursor.execute(
                "CREATE TABLE ContentItems (Id INTEGER, TitleId INTEGER, MediaId INTEGER, DiscNum INTEGER, TitleName TEXT)"
            )

            shared_title_id = int("454108C0", 16)
            cursor.execute(
                "INSERT INTO ContentItems (Id, TitleId, MediaId, DiscNum, TitleName) VALUES (?, ?, ?, ?, ?)",
                (46, shared_title_id, int("2E6F7560", 16), 1, "Dragon Age: Origins Awakening")
            )
            cursor.execute(
                "INSERT INTO ContentItems (Id, TitleId, MediaId, DiscNum, TitleName) VALUES (?, ?, ?, ?, ?)",
                (47, shared_title_id, int("33E76565", 16), 1, "Dragon Age: Origins")
            )
            conn.commit()
            conn.close()

            items = parse_content_db(db_path)
            names_by_db_id = {item.db_id: item.title_name for item in items}

            self.assertEqual(names_by_db_id["0000002E"], "Dragon Age: Origins Awakening")
            self.assertEqual(names_by_db_id["0000002F"], "Dragon Age: Origins")
        finally:
            if os.path.exists(db_path):
                os.remove(db_path)

if __name__ == "__main__":
    unittest.main()
