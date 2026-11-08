"""Тесты Leonardo.ai MCP-сервера (без сети)."""
import json
import tempfile
import unittest
from pathlib import Path

import tools.leonardo_mcp as leo


class PayloadTests(unittest.TestCase):
    def test_default_payload(self):
        payload = leo.build_payload("a mountain lake")
        self.assertEqual(payload["modelId"], leo.DEFAULT_MODEL_ID)
        self.assertEqual(payload["styleUUID"], leo.DEFAULT_STYLE_UUID)
        self.assertEqual(payload["width"], 1024)
        self.assertEqual(payload["height"], 1024)
        self.assertEqual(payload["num_images"], 1)
        self.assertEqual(payload["contrast"], 3.5)

    def test_dimensions_clamped_and_aligned(self):
        payload = leo.build_payload("x", width=2000, height=300)
        self.assertEqual(payload["width"], 1536)
        self.assertEqual(payload["height"], 512)
        self.assertEqual(payload["width"] % 8, 0)

    def test_num_images_limited(self):
        self.assertEqual(leo.build_payload("x", num_images=99)["num_images"], 4)
        self.assertEqual(leo.build_payload("x", num_images=0)["num_images"], 1)

    def test_empty_prompt_rejected(self):
        with self.assertRaises(leo.LeonardoError):
            leo.build_payload("   ")


class ApiTests(unittest.TestCase):
    def test_generate_returns_generation_id(self):
        calls = {}

        def fake_request(method, path, payload=None, timeout=60):
            calls.update(method=method, path=path, payload=payload)
            return {"sdGenerationJob": {"generationId": "gen-123"}}

        original = leo._request
        leo._request = fake_request
        try:
            result = leo.generate("cat", width=768, height=768)
        finally:
            leo._request = original
        self.assertEqual(calls["path"], "/generations")
        self.assertEqual(calls["method"], "POST")
        self.assertEqual(result["generation_id"], "gen-123")
        self.assertEqual(calls["payload"]["width"], 768)

    def test_generation_parses_images(self):
        def fake_request(method, path, payload=None, timeout=60):
            return {
                "generations_by_pk": {
                    "id": "g1",
                    "status": "COMPLETE",
                    "generated_images": [
                        {"url": "https://cdn.example/a.png"},
                        {"url": "https://cdn.example/b.png"},
                    ],
                }
            }

        original = leo._request
        leo._request = fake_request
        try:
            result = leo.generation("g1")
        finally:
            leo._request = original
        self.assertEqual(result["status"], "COMPLETE")
        self.assertEqual(len(result["images"]), 2)

    def test_wait_for_generation_loops_until_complete(self):
        states = [
            {"status": "PENDING", "images": [], "generation_id": "g"},
            {"status": "COMPLETE", "images": ["u"], "generation_id": "g"},
        ]

        def fake_generation(generation_id):
            return states.pop(0)

        original = leo.generation
        leo.generation = fake_generation
        try:
            result = leo.wait_for_generation("g", timeout=30, interval=1, sleep=lambda _: None)
        finally:
            leo.generation = original
        self.assertEqual(result["status"], "COMPLETE")

    def test_download_images_writes_files(self):
        downloaded = []

        def fake_wait(generation_id, timeout=180):
            return {"status": "COMPLETE", "images": ["https://cdn.example/x.png"], "generation_id": "g"}

        def fake_download(url, target, timeout=120):
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(b"png")
            downloaded.append(str(target))
            return target

        original_wait, original_download = leo.wait_for_generation, leo._download
        leo.wait_for_generation, leo._download = fake_wait, fake_download
        try:
            with tempfile.TemporaryDirectory() as tmp:
                result = leo.download_images("gen-1", out_dir=tmp)
                self.assertEqual(result["status"], "COMPLETE")
                self.assertEqual(len(result["files"]), 1)
                self.assertTrue(Path(result["files"][0]).is_file())
        finally:
            leo.wait_for_generation, leo._download = original_wait, original_download


class ProtocolTests(unittest.TestCase):
    def test_tools_list(self):
        response = leo.handle({"jsonrpc": "2.0", "id": 1, "method": "tools/list"})
        names = [tool["name"] for tool in response["result"]["tools"]]
        self.assertEqual(
            names,
            [
                "leonardo_generate",
                "leonardo_generation",
                "leonardo_download",
                "leonardo_list_models",
            ],
        )

    def test_missing_key_is_clear(self):
        response = leo.handle(
            {
                "jsonrpc": "2.0",
                "id": 2,
                "method": "tools/call",
                "params": {"name": "leonardo_generate", "arguments": {"prompt": "x"}},
            }
        )
        self.assertTrue(response["result"]["isError"])
        self.assertIn("LEONARDO_API_KEY", response["result"]["content"][0]["text"])


if __name__ == "__main__":
    unittest.main()
