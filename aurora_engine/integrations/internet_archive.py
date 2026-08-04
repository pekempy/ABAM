"""
Internet Archive Cover Dump Integration
Fallback repository for Xbox Unity cover dumps hosted on archive.org.
"""

re = None  # Lazy imported if needed
import re
from typing import Dict, List, Optional
import requests

class InternetArchiveClient:
    BASE_URL = "https://archive.org/download/xboxunity-covers-fulldump_202311/xboxunity-covers-fulldump/"

    @staticmethod
    def get_covers(title_id: str) -> List[Dict]:
        """
        Parses folder listings for a given Title ID from Archive.org.
        """
        if not title_id:
            return []

        title_folder = title_id.strip().upper()
        folder_url = f"{InternetArchiveClient.BASE_URL}{title_folder}/"
        results = []

        try:
            resp = requests.get(folder_url, timeout=12)
            if resp.status_code != 200:
                return []

            pattern = r'<a href="([^"]+)/">([^"]+)/</a>'
            matches = re.findall(pattern, resp.text)
            for href, text in matches:
                if href == text:
                    cover_url = f"{folder_url}{href}/boxart.png"
                    results.append({
                        "title_id": title_folder,
                        "variant": href,
                        "cover_url": cover_url,
                        "source": "Internet Archive Dump"
                    })
            return results
        except Exception as e:
            print(f"Error checking Internet Archive for {title_id}: {e}")
            return []

    @staticmethod
    def download_image(url: str) -> Optional[bytes]:
        """Downloads cover image bytes from Archive.org."""
        try:
            resp = requests.get(url, timeout=15)
            resp.raise_for_status()
            return resp.content
        except Exception as e:
            print(f"Error downloading cover from Archive.org ({url}): {e}")
            return None
