import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import main


class ConfigTests(unittest.TestCase):
    def test_split_csv_trims_empty_values(self):
        self.assertEqual(main.split_csv(" a, ,b,, c "), ["a", "b", "c"])

    def test_normalize_channel_url(self):
        self.assertEqual(
            main.normalize_channel_id("https://www.youtube.com/channel/UCabc123/videos"),
            "UCabc123",
        )

    def test_channels_from_file_accepts_strings_and_objects(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "channels.json"
            path.write_text(json.dumps(["UCone", {"name": "Two", "channel_id": "UCtwo"}]))
            channels = main.channels_from_file(path)
        self.assertEqual([channel.channel_id for channel in channels], ["UCone", "UCtwo"])
        self.assertEqual(channels[1].name, "Two")

    def test_channels_from_env_pairs_names(self):
        with patch.dict(os.environ, {"YOUTUBE_CHANNEL_IDS": "UCone,UCtwo", "YOUTUBE_CHANNEL_NAMES": "One,Two"}, clear=False):
            channels = main.channels_from_env()
        self.assertEqual([(channel.channel_id, channel.name) for channel in channels], [("UCone", "One"), ("UCtwo", "Two")])


if __name__ == "__main__":
    unittest.main()
