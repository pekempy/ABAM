"""
Xbox Live Marketplace Catalog API Client
Fetches official game title information, icons, background images, banners,
and screenshots directly from Microsoft's Xbox Live CDN.
"""

from typing import Dict, List, Optional
import xml.etree.ElementTree as ET
import requests

class XboxLiveClient:
    CATALOG_URL = (
        "http://catalog-cdn.xboxlive.com/Catalog/Catalog.asmx/Query?"
        "methodName=FindGames&Names=Locale&Values={locale}&Names=LegalLocale&Values={locale}"
        "&Names=Store&Values=1&Names=PageSize&Values=100&Names=PageNum&Values=1"
        "&Names=DetailView&Values=5&Names=OfferFilterLevel&Values=1"
        "&Names=MediaIds&Values=66acd000-77fe-1000-9115-d802{title_id}"
        "&Names=UserTypes&Values=2&Names=MediaTypes&Values=1&Names=MediaTypes&Values=21"
        "&Names=MediaTypes&Values=23&Names=MediaTypes&Values=37&Names=MediaTypes&Values=46"
    )

    SEARCH_URL = "http://marketplace.xbox.com/{locale}/SiteSearch/xbox/?query={query}&PageSize=10"

    @staticmethod
    def get_title_assets(title_id: str, locale: str = "en-US") -> Dict:
        """
        Fetches title name, icons, backgrounds, banner, and screenshot URLs from Xbox Live Catalog.
        """
        formatted_id = title_id.strip().upper().zfill(8)
        url = XboxLiveClient.CATALOG_URL.format(locale=locale, title_id=formatted_id)

        result = {
            "title_id": formatted_id,
            "title_name": "",
            "icons": [],
            "backgrounds": [],
            "banners": [],
            "screenshots": []
        }

        try:
            resp = requests.get(url, timeout=12)
            if resp.status_code != 200:
                return result

            # Parse XML
            root = ET.fromstring(resp.content)
            
            # Simple XML traversal
            for elem in root.iter():
                tag = elem.tag.lower()
                if "fulltitle" in tag and elem.text and not result["title_name"]:
                    result["title_name"] = elem.text.strip()

            # Find images
            for image_elem in root.iter():
                tag = image_elem.tag.lower()
                if "image" in tag:
                    rel_type = None
                    file_url = None
                    for child in image_elem:
                        ctag = child.tag.lower()
                        if "relationshiptype" in ctag and child.text:
                            rel_type = child.text.strip()
                        elif "fileurl" in ctag and child.text:
                            file_url = child.text.strip()

                    if file_url:
                        if rel_type in ("15", "23"):
                            result["icons"].append(file_url)
                        elif rel_type == "25":
                            result["backgrounds"].append(file_url)
                        elif rel_type == "27":
                            result["banners"].append(file_url)

                if "slideshows" in tag:
                    for child in image_elem.iter():
                        ctag = child.tag.lower()
                        if "fileurl" in ctag and child.text:
                            result["screenshots"].append(child.text.strip())

            return result
        except Exception as e:
            print(f"Error querying Xbox Live API for {title_id}: {e}")
            return result
