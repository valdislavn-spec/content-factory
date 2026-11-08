#!/usr/bin/env python3
"""Генерация изображения без ключа (Pollinations) или через Leonardo/HF.

    python scripts/image_gen.py "editorial illustration, AI chips, blue light"
    python scripts/image_gen.py "..." --provider huggingface --width 768 --height 768
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tools.image_mcp as API  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?")
    parser.add_argument("--provider", default="pollinations",
                        choices=["pollinations", "huggingface", "leonardo"])
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--model", default="")
    parser.add_argument("--seed", type=int, default=None)
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()
    if not args.prompt:
        parser.error('нужен промпт: python scripts/image_gen.py "..."')
    if args.dry_run:
        print(json.dumps({"dry_run": True, "provider": args.provider, "prompt": args.prompt,
                          "available": API.available_providers()}, ensure_ascii=False, indent=2))
        return 0
    try:
        result = API.generate(args.prompt, args.provider, args.width, args.height,
                              args.model, args.seed, args.out_dir)
    except API.ImageError as exc:
        print(f"Ошибка: {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
