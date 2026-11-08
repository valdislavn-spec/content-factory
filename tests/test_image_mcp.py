"""Тесты image-стеков: Pollinations (без ключа), HuggingFace, Leonardo (mock)."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import tools.image_mcp as img


JPEG_BYTES = b"\xff\xd8\xff\xe0" + b"\x00" * 2048  # минимально валидный по размеру


class ProviderTests(unittest.TestCase):
    def test_default_provider_is_pollinations(self):
        with mock.patch.dict(os.environ, {"LEONARDO_API_KEY": "", "HUGGINGFACE_API_KEY": ""}):
            self.assertEqual(img.available_providers(), ["pollinations"])

    def test_keys_add_providers(self):
        with mock.patch.dict(os.environ, {"LEONARDO_API_KEY": "k", "HUGGINGFACE_API_KEY": "h"}):
            providers = img.available_providers()
        self.assertIn("leonardo", providers)
        self.assertIn("huggingface", providers)

    def test_clamp(self):
        self.assertEqual(img._clamp(2000), 1536)
        self.assertEqual(img._clamp(100), 256)
        self.assertEqual(img._clamp(1024) % 8, 0)

    def test_unknown_provider(self):
        with self.assertRaises(img.ImageError):
            img.generate("x", provider="dalle")


class PollinationsTests(unittest.TestCase):
    def test_generate_builds_url_and_saves(self):
        seen = {}

        def fake_fetch(url, attempts=3):
            seen["url"] = url
            return JPEG_BYTES

        original = img._pollinations_fetch
        img._pollinations_fetch = fake_fetch
        try:
            with mock.patch.dict(os.environ, {"POLLINATIONS_TOKEN": ""}), tempfile.TemporaryDirectory() as tmp:
                result = img.generate_pollinations(
                    "editorial illustration, AI chips", 512, 768, out_dir=tmp
                )
                self.assertTrue(Path(result["file"]).is_file())
        finally:
            img._pollinations_fetch = original
        url = seen["url"]
        self.assertIn("editorial%20illustration%2C%20AI%20chips", url)
        self.assertIn("width=512", url)
        self.assertIn("height=768", url)
        self.assertIn("nologo=true", url)
        self.assertEqual(result["provider"], "pollinations")

    def test_retry_on_free_limit(self):
        calls = {"n": 0}

        def flaky_fetch(url, timeout=240):
            calls["n"] += 1
            if calls["n"] == 1:
                raise img.ImageError(
                    'HTTP 402 от image.pollinations.ai: {"error":{"code":"FREE_LIMIT"},'
                    '"message":"Free limit reached: 1 image every 45 seconds per IP. Retry after 2s"}'
                )
            return JPEG_BYTES

        with mock.patch.object(img, "_fetch", flaky_fetch), mock.patch.object(img.time, "sleep"):
            data = img._pollinations_fetch("https://example.test")
        self.assertEqual(calls["n"], 2)
        self.assertEqual(data, JPEG_BYTES)


class HuggingFaceTests(unittest.TestCase):
    def test_missing_key(self):
        with mock.patch.dict(os.environ, {"HUGGINGFACE_API_KEY": ""}):
            with self.assertRaises(img.ImageError):
                img.generate_huggingface("prompt")


class LeonardoDelegationTests(unittest.TestCase):
    def test_delegates_to_leonardo(self):
        try:
            import tools.leonardo_mcp as leo
        except ModuleNotFoundError:
            self.skipTest("tools/leonardo_mcp.py есть только в origin/main")

        with mock.patch.object(leo, "generate", return_value={"generation_id": "g1"}), \
             mock.patch.object(leo, "download_images", return_value={"files": ["/tmp/x.png"]}):
            result = img.generate("prompt", provider="leonardo")
        self.assertEqual(result["provider"], "leonardo")
        self.assertEqual(result["file"], "/tmp/x.png")


class ProtocolTests(unittest.TestCase):
    def test_tools_list(self):
        response = img.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(names, ["image_generate", "image_providers"])

    def test_providers_tool(self):
        response = img.handle({"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                               "params": {"name": "image_providers", "arguments": {}}})
        self.assertFalse(response["result"]["isError"])
        self.assertIn("pollinations", response["result"]["content"][0]["text"])

    def test_tiny_response_rejected(self):
        with self.assertRaises(img.ImageError):
            img._save(b"error", Path("/tmp/x.jpg"))


if __name__ == "__main__":
    unittest.main()
