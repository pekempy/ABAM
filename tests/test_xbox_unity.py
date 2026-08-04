import unittest
from unittest.mock import Mock, patch

from aurora_engine.integrations.xbox_unity import XboxUnityClient


class TestXboxUnityClient(unittest.TestCase):
    @patch("aurora_engine.integrations.xbox_unity.requests.get")
    def test_search_media_icon_uses_duckduckgo_images(self, mock_get):
        unity_resp = Mock()
        unity_resp.status_code = 200
        unity_resp.raise_for_status.return_value = None
        unity_resp.json.return_value = [{
            "titleid": "5345080E",
            "name": "Alpha Protocol",
            "thumbnail": "http://assets.xboxunity.net/api/boxartsm/225"
        }]

        mock_get.return_value = unity_resp

        results = XboxUnityClient.search_media("Alpha Protocol", category="icon")

        self.assertGreaterEqual(len(results), 1)
        self.assertEqual(results[0]["source"], "Xbox Unity")
        self.assertEqual(results[0]["image_url"], "http://assets.xboxunity.net/api/boxartsm/225")


if __name__ == "__main__":
    unittest.main()