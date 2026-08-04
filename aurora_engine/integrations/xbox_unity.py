"""
Xbox Unity API Scraper
Fetches cover artwork, game details, ratings, and high-res cover links from Xbox Unity.
"""

import re
from urllib.parse import parse_qs, unquote, urljoin, urlparse
from typing import Dict, List, Optional
import requests

class XboxUnityClient:
    BASE_URL = "http://xboxunity.net/api/Covers/"

    @staticmethod
    def _dedupe_results(results: List[Dict]) -> List[Dict]:
        deduped = []
        seen_urls = set()
        for item in results:
            image_url = item.get("image_url")
            if not image_url or image_url in seen_urls:
                continue
            seen_urls.add(image_url)
            deduped.append(item)
        return deduped

    @staticmethod
    def _search_duckduckgo_images(query: str, limit: int = 8) -> List[Dict]:
        """Searches DuckDuckGo static HTML results and extracts preview images from result pages."""
        if not query:
            return []

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (AuroraAssetEditor)",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            search_url = f"https://lite.duckduckgo.com/lite/?q={requests.utils.quote(query)}"
            resp = requests.get(search_url, headers=headers, timeout=10)
            resp.raise_for_status()

            link_matches = re.findall(r"href=['\"](//duckduckgo\.com/l/\?uddg=[^'\"]+)['\"]", resp.text)
            results = []
            visited_pages = set()
            for ddg_link in link_matches:
                if len(results) >= limit:
                    break
                ddg_link = urljoin("https:", ddg_link)
                parsed = urlparse(ddg_link)
                target_url = parse_qs(parsed.query).get("uddg", [""])[0]
                target_url = unquote(target_url)
                if not target_url or target_url in visited_pages:
                    continue
                visited_pages.add(target_url)

                try:
                    page = requests.get(target_url, headers=headers, timeout=10)
                    page.raise_for_status()
                    page_html = page.text
                except Exception:
                    continue

                image_url = None
                for pattern in [
                    r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
                    r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
                    r'<img[^>]+src=["\']([^"\']+\.(?:png|jpg|jpeg|webp|ico))',
                ]:
                    match = re.search(pattern, page_html, flags=re.IGNORECASE)
                    if match:
                        image_url = match.group(1)
                        break

                if not image_url:
                    continue

                image_url = urljoin(target_url, image_url)
                lowered_image_url = image_url.lower()
                parsed_image = urlparse(image_url)
                if parsed_image.path in {"", "/"}:
                    continue
                if any(token in lowered_image_url for token in [
                    '/logo.', 'generic', 'ms-icon', 'apple-touch-icon', 'favicon', '/static/'
                ]):
                    continue

                title_match = re.search(r'<title>(.*?)</title>', page_html, flags=re.IGNORECASE | re.DOTALL)
                title = title_match.group(1).strip() if title_match else query
                results.append({
                    "title_id": "",
                    "title_name": title,
                    "category": "icon",
                    "image_url": image_url,
                    "thumbnail_url": image_url,
                    "source": "DuckDuckGo Images",
                    "author": urlparse(target_url).netloc or "DuckDuckGo",
                    "rating": "Transparent Search",
                })
            return results
        except Exception:
            return []

    @staticmethod
    def _search_steamgriddb_icons(query: str, limit: int = 12) -> List[Dict]:
        """Scrapes SteamGridDB icon search results for a game title."""
        if not query:
            return []

        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (AuroraAssetEditor)",
            "Accept-Language": "en-US,en;q=0.9",
        }
        try:
            url = f"https://www.steamgriddb.com/search/icons?term={requests.utils.quote(query)}"
            resp = requests.get(url, headers=headers, timeout=15)
            resp.raise_for_status()
            html = resp.text

            image_urls = re.findall(r'https://cdn2\.steamgriddb\.com/icon(?:_thumb)?/[^"\s<>]+', html)
            if not image_urls:
                image_urls = re.findall(r'https://cdn2\.steamgriddb\.com/icon/[^"\s<>]+', html)

            results = []
            for image_url in image_urls[:limit]:
                results.append({
                    "title_id": "",
                    "title_name": f"{query} (Icon)",
                    "category": "icon",
                    "image_url": image_url,
                    "thumbnail_url": image_url,
                    "source": "SteamGridDB",
                    "author": "SteamGridDB",
                    "rating": "Game Icon",
                })
            return results
        except Exception:
            return []

    @staticmethod
    def search_covers(query: str) -> List[Dict]:
        """
        Searches Xbox Unity covers by Title ID (e.g. '415608C3') or game title string.
        Returns a list of cover metadata objects.
        """
        if not query or not query.strip():
            return []

        url = f"{XboxUnityClient.BASE_URL}{requests.utils.quote(query.strip())}"
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (AuroraAssetEditor)",
            "Accept": "application/json"
        }

        import time
        for attempt in range(3):
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                resp.raise_for_status()
                data = resp.json()
                if isinstance(data, list):
                    results = []
                    for item in data:
                        results.append({
                            "title_id": item.get("titleid", ""),
                            "title_name": item.get("name", ""),
                            "official": bool(item.get("official", False)),
                            "file_size": item.get("filesize", ""),
                            "cover_url": item.get("url", ""),
                            "front_url": item.get("front", ""),
                            "thumbnail_url": item.get("thumbnail", ""),
                            "author": item.get("author", "XboxUnity"),
                            "upload_date": item.get("uploaddate", ""),
                            "rating": item.get("rating", "N/A"),
                            "link": item.get("link", "")
                        })
                    return results
                return []
            except Exception as e:
                time.sleep(1)
                if attempt == 2:
                    print(f"Error fetching covers from Xbox Unity ({query}): {e}")
        return []

    @staticmethod
    def search_media(query: str, category: str = "boxart") -> List[Dict]:
        """
        Searches online sources for specified asset category:
        'boxart', 'background', 'icon', 'banner', 'screenshots'
        """
        if not query or not query.strip():
            return []

        results = []
        clean_name = query.strip()
        
        # 1. Boxart Category -> Search Xbox Unity
        if category == "boxart":
            unity_items = XboxUnityClient.search_covers(clean_name)
            for item in unity_items:
                results.append({
                    "title_id": item["title_id"],
                    "title_name": item["title_name"],
                    "category": "boxart",
                    "image_url": item["cover_url"],
                    "thumbnail_url": item.get("thumbnail_url") or item["cover_url"],
                    "source": "Xbox Unity",
                    "author": item.get("author", "XboxUnity"),
                    "rating": item.get("rating", "N/A")
                })
            return results

        # 2. Icon Category -> Square transparent icons & Xbox Unity thumbnails
        if category == "icon":
            # 1. Xbox Unity Cover Thumbnails (64x64 / small thumbnails)
            unity_items = XboxUnityClient.search_covers(clean_name)
            for item in unity_items:
                thumb = item.get("thumbnail_url") or item.get("cover_url")
                if thumb:
                    results.append({
                        "title_id": item["title_id"],
                        "title_name": f"{item['title_name']} (Icon)",
                        "category": "icon",
                        "image_url": thumb,
                        "thumbnail_url": thumb,
                        "source": "Xbox Unity",
                        "author": item.get("author", "XboxUnity"),
                        "rating": "64x64 Icon"
                    })

            # 2. SteamGridDB icons
            results.extend(XboxUnityClient._search_steamgriddb_icons(clean_name))

            # 3. Steam small capsule media
            try:
                steam_url = f"https://store.steampowered.com/api/storesearch/?term={requests.utils.quote(clean_name)}&l=english&cc=US"
                sresp = requests.get(steam_url, timeout=6)
                if sresp.status_code == 200:
                    sdata = sresp.json()
                    for sitem in sdata.get("items", [])[:4]:
                        app_id = sitem.get("id")
                        gname = sitem.get("name", clean_name)
                        icon_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/capsule_sm_120.jpg"
                        results.append({
                            "title_id": "",
                            "title_name": f"{gname} (Icon)",
                            "category": "icon",
                            "image_url": icon_url,
                            "thumbnail_url": icon_url,
                            "source": "Steam Media",
                            "author": "Steam",
                            "rating": "Game Icon"
                        })
            except Exception:
                pass

            # 4. DuckDuckGo transparent PNG icon search fallback
            if len(results) < 3:
                ddg_icons = XboxUnityClient._search_duckduckgo_images(f"{clean_name} game icon png")
                results.extend(ddg_icons)

            return XboxUnityClient._dedupe_results(results)

        # 3. Banner Category -> Wide 420x96 Header Banners
        if category == "banner" or category == "icon_banner":
            try:
                steam_url = f"https://store.steampowered.com/api/storesearch/?term={requests.utils.quote(clean_name)}&l=english&cc=US"
                sresp = requests.get(steam_url, timeout=6)
                if sresp.status_code == 200:
                    sdata = sresp.json()
                    for sitem in sdata.get("items", [])[:4]:
                        app_id = sitem.get("id")
                        gname = sitem.get("name", clean_name)
                        banner_url = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/header.jpg"
                        results.append({
                            "title_id": "",
                            "title_name": f"{gname} (Banner)",
                            "category": "banner",
                            "image_url": banner_url,
                            "thumbnail_url": banner_url,
                            "source": "Steam HD Media",
                            "author": "Steam",
                            "rating": "420x96 Banner"
                        })
            except Exception:
                pass

            if len(results) < 2:
                ddg_banners = XboxUnityClient._search_duckduckgo_images(f"{clean_name} xbox banner 420x96")
                results.extend(ddg_banners)

            return XboxUnityClient._dedupe_results(results)

        # 4. Background Category -> High-Res Wallpapers & Fanart
        if category == "background":
            try:
                steam_url = f"https://store.steampowered.com/api/storesearch/?term={requests.utils.quote(clean_name)}&l=english&cc=US"
                sresp = requests.get(steam_url, timeout=6)
                if sresp.status_code == 200:
                    sdata = sresp.json()
                    for sitem in sdata.get("items", [])[:4]:
                        app_id = sitem.get("id")
                        gname = sitem.get("name", clean_name)
                        burl = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{app_id}/page_bg_generated_v6.jpg"
                        results.append({
                            "title_id": "",
                            "title_name": f"{gname} (Background Wallpaper)",
                            "category": "background",
                            "image_url": burl,
                            "thumbnail_url": burl,
                            "source": "Steam HD Media",
                            "author": "Steam",
                            "rating": "1280x720 HD"
                        })
            except Exception:
                pass

            if len(results) < 2:
                ddg_bg = XboxUnityClient._search_duckduckgo_images(f"{clean_name} wallpaper HD")
                results.extend(ddg_bg)

            return XboxUnityClient._dedupe_results(results)

        # 5. Screenshots Category -> REAL Gameplay Screenshots via Steam App Details API & In-Game Search
        if category == "screenshots":
            try:
                steam_url = f"https://store.steampowered.com/api/storesearch/?term={requests.utils.quote(clean_name)}&l=english&cc=US"
                sresp = requests.get(steam_url, timeout=6)
                if sresp.status_code == 200:
                    sdata = sresp.json()
                    for sitem in sdata.get("items", [])[:2]:
                        app_id = sitem.get("id")
                        gname = sitem.get("name", clean_name)
                        
                        det_url = f"https://store.steampowered.com/api/appdetails?appids={app_id}"
                        dresp = requests.get(det_url, timeout=6)
                        if dresp.status_code == 200:
                            ddata = dresp.json()
                            app_info = ddata.get(str(app_id), {}).get("data", {})
                            screenshots_list = app_info.get("screenshots", [])
                            for ss_idx, ss_item in enumerate(screenshots_list[:8]):
                                full_url = ss_item.get("path_full")
                                thumb_url = ss_item.get("path_thumbnail") or full_url
                                if full_url:
                                    results.append({
                                        "title_id": "",
                                        "title_name": f"{gname} (Gameplay Screenshot #{ss_idx + 1})",
                                        "category": "screenshots",
                                        "image_url": full_url,
                                        "thumbnail_url": thumb_url,
                                        "source": "Steam Gameplay",
                                        "author": "Gameplay",
                                        "rating": "1080p Screenshot"
                                    })
            except Exception as e:
                print("Error searching screenshots:", e)

            # Fallback in-game screenshot search if Steam returns fewer than 4 screenshots
            if len(results) < 4:
                try:
                    search_query = f"{clean_name} xbox 360 gameplay screenshot 1080p"
                    ddg_ss = XboxUnityClient._search_duckduckgo_images(search_query, limit=6)
                    for item in ddg_ss:
                        item["category"] = "screenshots"
                        item["rating"] = "Gameplay Screenshot"
                        results.append(item)
                except Exception:
                    pass

            return XboxUnityClient._dedupe_results(results)

        return results

    @staticmethod
    def download_image(url: str) -> Optional[bytes]:
        """Downloads image bytes from specified URL."""
        if not url:
            return None
        import time
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (AuroraAssetEditor)"
        }
        for attempt in range(3):
            try:
                resp = requests.get(url, headers=headers, timeout=15)
                resp.raise_for_status()
                return resp.content
            except Exception as e:
                time.sleep(1)
                if attempt == 2:
                    print(f"Error downloading image from {url}: {e}")
        return None
