#!/usr/bin/env python3
"""Генерация изображения через Leonardo.ai и скачивание в assets/generated.

    export LEONARDO_API_KEY=...        # https://app.leonardo.ai/api-access
    python scripts/leonardo_image.py "cinematic illustration of AI chips" \
        --width 1024 --height 1024 --num 2

По умолчанию: модель Lucid Origin, стиль Dynamic, 1 изображение 1024x1024.
--dry-run показывает payload без вызова API.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

import tools.leonardo_mcp as API  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("prompt", nargs="?", default="", help="текстовый промпт")
    parser.add_argument("--prompt", dest="prompt_opt", default="")
    parser.add_argument("--model", default="", help="modelId (по умолчанию Lucid Origin)")
    parser.add_argument("--width", type=int, default=1024)
    parser.add_argument("--height", type=int, default=1024)
    parser.add_argument("--num", type=int, default=1)
    parser.add_argument("--style-uuid", default="")
    parser.add_argument("--alchemy", action="store_true")
    parser.add_argument("--contrast", type=float, default=3.5)
    parser.add_argument("--out-dir", default="")
    parser.add_argument("--timeout", type=int, default=180)
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    prompt = (args.prompt or args.prompt_opt).strip()
    if not prompt:
        parser.error("нужен промпт: python scripts/leonardo_image.py \"...\"")
    payload = API.build_payload(
        prompt, args.model, args.width, args.height, args.num, args.style_uuid,
        args.alchemy, args.contrast,
    )
    if args.dry_run:
        print(json.dumps({"dry_run": True, "payload": payload}, ensure_ascii=False, indent=2))
        return 0
    try:
        job = API.generate(
            prompt, args.model, args.width, args.height, args.num,
            args.style_uuid, args.alchemy, args.contrast,
        )
        print(f"generation_id: {job['generation_id']}")
        result = API.download_images(
            str(job["generation_id"]), out_dir=args.out_dir, timeout=args.timeout
        )
    except API.LeonardoError as exc:
        print(f"Ошибка Leonardo: {exc}")
        return 2
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
