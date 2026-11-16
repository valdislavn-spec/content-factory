#!/usr/bin/env python3
"""Вставка формы подписки (email -> свой D1-лист через воркер links-tracker) на лендинги.

Идемпотентно: блок с id="subscribe" повторно не добавляется.
Запускается вручную и из конвейеров (add_travel_promos.py / build_us_landing.py),
чтобы после пересборки страниц форма оставалась.
"""
from __future__ import annotations

import argparse
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ENDPOINT = "https://links-tracker.valdislav-n.workers.dev/subscribe"

RU_BLOCK = """
<section id="subscribe" style="margin:40px 0 0;padding:22px 24px;border-radius:16px;background:rgba(124,58,237,.14);border:1px solid rgba(124,58,237,.4)">
<h2 style="font-size:22px;margin:0 0 8px">Новые цены — раз в неделю</h2>
<p style="margin:0 0 14px;color:#c7d2fe;font-size:15px">Сводка обновляется каждую неделю. Оставьте email — пришлём дайджест с новыми ценами и промо.</p>
<form class="sub-form" data-source="__SOURCE__" style="display:flex;gap:10px;flex-wrap:wrap;margin:0 0 10px">
<input type="email" required placeholder="ваш email" aria-label="Email" class="sub-email" style="flex:1;min-width:220px;padding:13px 16px;border-radius:12px;border:1px solid rgba(148,163,255,.35);background:rgba(255,255,255,.06);color:#eef2ff;font-size:15px">
<button type="submit" class="btn" style="border:0;cursor:pointer;padding:13px 22px">Подписаться</button>
</form>
<p class="sub-msg" style="margin:0 0 10px;font-size:14px;color:#6ee7b7;display:none"></p>
<p style="margin:0;font-size:14px;color:#8b98bf">Или в Telegram: <a href="https://t.me/GOODTRAVEL007" target="_blank" rel="noopener" style="color:#a5b4fc">@GOODTRAVEL007</a></p>
<script>
(function(){var f=document.querySelector('.sub-form');if(!f)return;
f.addEventListener('submit',function(e){e.preventDefault();
var i=f.querySelector('.sub-email'),m=document.querySelector('.sub-msg');
var p=new URLSearchParams(location.search),u=p.get('utm_source')||'',c=p.get('utm_content')||'',src=f.dataset.source+(u?':'+u+(c?'-'+c:''):'');
fetch('__ENDPOINT__',{method:'POST',headers:{'content-type':'application/json'},
body:JSON.stringify({email:i.value,lang:'ru',source:src})})
.then(function(r){return r.json()}).then(function(d){m.textContent=d.ok?'Готово — сохранили email.':(d.error||'Не получилось, попробуйте позже');m.style.display='block';if(d.ok)f.reset();})
.catch(function(){m.textContent='Ошибка сети — попробуйте позже';m.style.display='block';});});})();
</script>
</section>
"""

EN_BLOCK = """
<section id="subscribe" style="margin:40px 0 0;padding:22px 24px;border-radius:16px;background:rgba(124,58,237,.14);border:1px solid rgba(124,58,237,.4)">
<h2 style="font-size:22px;margin:0 0 8px">Get the free 2026 US winter fare cheat sheet</h2>
<p style="margin:0 0 14px;color:#c7d2fe;font-size:15px">12 winter escapes, real sample one-way fares, best months and a booking checklist. Free PDF — no spam, unsubscribe anytime.</p>
<form class="sub-form" data-source="__SOURCE__" style="display:flex;gap:10px;flex-wrap:wrap;margin:0 0 10px">
<input type="email" required placeholder="your email" aria-label="Email" class="sub-email" style="flex:1;min-width:220px;padding:13px 16px;border-radius:12px;border:1px solid rgba(148,163,255,.35);background:rgba(255,255,255,.06);color:#eef2ff;font-size:15px">
<button type="submit" class="btn" style="border:0;cursor:pointer;padding:13px 22px">Get the free PDF</button>
</form>
<p class="sub-msg" style="margin:0 0 10px;font-size:14px;color:#6ee7b7;display:none"></p>
</section>
<script>
(function(){var f=document.querySelector('.sub-form');if(!f)return;
f.addEventListener('submit',function(e){e.preventDefault();
var i=f.querySelector('.sub-email'),m=document.querySelector('.sub-msg');
var p=new URLSearchParams(location.search),u=p.get('utm_source')||'',c=p.get('utm_content')||'',src=f.dataset.source+(u?':'+u+(c?'-'+c:''):'');
fetch('__ENDPOINT__',{method:'POST',headers:{'content-type':'application/json'},
body:JSON.stringify({email:i.value,lang:'en',source:src})})
.then(function(r){return r.json()}).then(function(d){m.textContent=d.ok?'Saved — opening your PDF...':(d.error||'Something went wrong');m.style.display='block';if(d.ok){f.reset();setTimeout(function(){location.href='thanks/'},500)}})
.catch(function(){m.textContent='Network error, try later';m.style.display='block';});});})();
</script>
</section>
"""

TARGETS = {
    "flight-hotel-abroad": ("ru", "landing-abroad"),
    "nezabyvaemoe-puteshestvie": ("ru", "landing-package"),
    "flight-hotel-us": ("en", "landing-us"),
}


def block_for(lang: str, source: str) -> str:
    tmpl = RU_BLOCK if lang == "ru" else EN_BLOCK
    return tmpl.replace("__SOURCE__", source).replace("__ENDPOINT__", ENDPOINT)


def inject(path: Path, lang: str, source: str) -> bool:
    html = path.read_text(encoding="utf-8")
    if 'id="subscribe"' in html:
        return False
    block = block_for(lang, source)
    if "<footer>" in html:
        html = html.replace("<footer>", block + "<footer>", 1)
    else:
        html = html.replace("</body>", block + "</body>", 1)
    path.write_text(html, encoding="utf-8")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--page", choices=[*TARGETS, "all"], default="all")
    args = parser.parse_args()
    names = list(TARGETS) if args.page == "all" else [args.page]
    changed = 0
    for name in names:
        path = DOCS / name / "index.html"
        if not path.exists():
            print(f"{name}: нет файла")
            continue
        lang, source = TARGETS[name]
        changed += 1 if inject(path, lang, source) else 0
    print(f"форм добавлено: {changed}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
