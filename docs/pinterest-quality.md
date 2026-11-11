# Pinterest pin quality: design system, specs and QA

This document describes how the content factory renders Pinterest pins, which
quality gates are enforced automatically, and how to verify a batch before it
is imported into Pinterest.  It is the reference for the v5 design engine
(`content_factory/brand/design.py`) and the sample batch in
`docs/assets/pins-v5/`.

Pinterest is a visual search engine: a pin has to survive thumbnail size, carry
one idea, disclose affiliate links, and be legible for low-vision users.  The
old renderers placed text at hard-coded coordinates and could overflow or leave
bright photo areas behind thin text; v5 makes those rules executable.

---

## 1. Non-negotiable spec

| Property | Requirement | Where enforced |
|---|---|---|
| Canvas | **1000×1500 px**, 2:3 portrait | `design.PIN_SIZE`, `render_pin`, tests |
| Format | RGB PNG (or photo JPEG source → PNG output) | renderer, samples |
| Safe margins | **≥ 64 px** on all sides; design default **72 px** | `design.SAFE_MARGIN`, `MIN_SAFE_MARGIN`, layout validator |
| Minimum font size | **≥ 24 px** for every text block | `design.MIN_FONT_SIZE`, layout validator |
| Body contrast | **≥ 4.5:1** (WCAG AA normal text) | measured per block in `PinMetrics`, renderer raises |
| Heading contrast | **≥ 3.0:1** (WCAG AA large text) | measured headline contrast |
| Headline | ≤ **3 lines**, auto-wrapped, auto-shrunk (never clipped) | `fit_text`, layout engine |
| Subtitle | ≤ 3 lines, auto-shrunk to ≥ 32 px | layout engine |
| Bullets / cards | ≤ **3 cards**, ≤ 2 lines each, dropped only if the pin cannot fit | layout engine + `dropped` metadata |
| CTA | **always present** ("Read more" fallback) | layout validator |
| Disclosure | **always present** in the footer (`Ad · affiliate link` or `Save this guide`) | layout validator + payload |
| Photo attribution | required for CC BY / CC BY-SA photos, `Photo: author · license · Wikimedia` (license preserved if truncated) | `format_attribution`, photo renderer |
| QR code | optional; rendered only when a destination URL is passed | `make_qr_image` (segno), footer |
| Pinterest title | **≤ 100 chars**, non-empty | `build_pinterest_payload`, CSV validator |
| Pinterest description | **≤ 500 chars**, non-empty, contains CTA **and** disclosure | payload builder, CSV validator |
| Alt text | **≤ 500 chars**, non-empty, descriptive | payload builder |
| Board | required, mapped per niche (`Travel ideas`, `Crypto`, `AI tools`, `Sports`, `Pins`) | `board_for_niche`, CSV validator |
| Keywords | required, non-empty, each ≤ 64 chars, total ≤ 320 chars | `keywords_for`, CSV validator |
| Media URL | absolute `http(s)` image URL (`.png/.jpg/.jpeg/.webp/.gif`) | payload + CSV validator |
| Link | absolute `http(s)`; required for affiliate pins | payload + CSV validator |

---

## 2. Design system (`content_factory/brand/design.py`)

The module has a **pure layer** (stdlib only: tokens, colour/contrast math,
gradient/cover/scrim math, text auto-fit, layout engine, payload/CSV helpers)
and a **render layer** that imports Pillow lazily.  That is why the design tests
run in the normal venv, while image rendering is optional.

### 2.1 Tokens

| Group | Values |
|---|---|
| Canvas | 1000×1500; safe margin 72 (floor 64) |
| Colours | ink `#0B0B10`, cream `#F7F2E9`, muted `#B0B8C6`, white `#FFFFFF` |
| Niche themes | travel `#FF7A45`, crypto `#F0B90B`, ai `#4C9AFF`, sports `#2ECC71`, default `#4F8CFF` — each with a 3-stop dark gradient |
| Type scale | display 136 / headline 112 / subtitle 44 / body 34 / caption 26 / micro 24 / CTA 36 / tag 24 / brand 24 |
| Type fits | headline 136→64 (fallback 56→24 with warning), subtitle 44→32, bullets 34→26, CTA 38→26, footer 26/24 |
| Shape | card radius 28, pill radius 40, small radius 14, QR card radius 18 |
| Spacing | 40 / 28 / 24 / 32 / 28 / 24 px gaps (auto-reduced when needed) |
| Cards / CTA | card height ≥ 72, CTA height ≥ 76, CTA horizontal padding 36 |
| Footer | 140 px (196 px with QR), inner padding 22, QR card 172 px |
| Shadow | offset 6 px, alpha 56 |

Fonts: `assets/fonts/Inter.ttf` (sans) and `assets/fonts/PlayfairDisplay.ttf`
(display) — both already used by the rest of the factory.

### 2.2 Layout engine (`layout_pin`)

1. **Fit text first.** `fit_text` greedily wraps words (honouring explicit
   `\n`), tests font sizes from large to small, and returns the largest size
   that fits the width and line budget.  A word wider than the box at the
   minimum size raises `TextOverflowError` instead of being clipped.
2. **Compose blocks:** header (keyword pill left, brand mark right), headline,
   accent rule, subtitle, bullet cards, CTA pill, footer band (disclosure,
   attribution, site, optional QR).
3. **Overflow passes, in priority order:** reduce inter-block spacing →
   shrink subtitle → drop trailing bullets (recorded in `dropped`) → shrink the
   headline (fallback sizes; recorded as a warning).  If nothing fits,
   `LayoutOverflowError` is raised — the renderer never produces clipped text.
4. **Bottom anchor:** CTA and footer stick to the bottom safe margin; spare
   vertical space is used to optically centre the content column (capped at
   180 px) instead of leaving one large gap.
5. **Validate:** every rect is inside the safe area, no top-level blocks
   overlap, each text line's measured width ≤ its box, CTA + disclosure exist,
   min font ≥ 24, margins ≥ 64.
6. **Measure while rendering:** for each text block the renderer samples the
   actual background pixels under the text (photo scrim, gradient, cards,
   footer band) and computes the worst-case WCAG contrast.  If a photo area is
   too bright, a soft dark panel is composited behind the text and the ratio is
   re-measured; if it still fails, rendering raises `QualityError`.

### 2.3 Backgrounds and components

* **Gradient variant**: vertical 3-stop niche gradient + two soft radial accent
  glows (no hard ellipse edges).
* **Photo variant**: `cover_box` centre-crops the photo to 1000×1500 (no
  distortion), then a vertical contrast scrim (alpha 0.88 → 0.52 → 0.70) keeps
  the headline/subtitle legible while the middle of the photo stays visible.
* **Components**: keyword pill (ink fill, accent border, cream text), brand
  mark (`CF` monogram + letterspaced wordmark), headline in Playfair Display,
  accent rule, subtitle, rounded bullet cards with accent check icons, CTA pill
  in the niche accent (text colour chosen for maximum contrast, always ≥ 4.5),
  footer band with disclosure + attribution + site + optional QR.

### 2.4 Pinterest payload helper

`build_pinterest_payload` produces the `POST /v5/pins` object and validates it:

* `title` ≤ 100 chars (word-boundary ellipsis);
* `description` ≤ 500 chars, **always** ends with the CTA and the disclosure —
  the base description is trimmed first so the CTA/disclosure are never lost;
* `alt_text` ≤ 500 chars;
* `media_source.source_type = "image_url"` + absolute URL;
* `link` **always** present: partner URL for affiliate pins, hub fallback for
  guide pins; must be an active https URL (see 2.5);
* `validate_pinterest_payload` returns a list of problems; invalid payloads
  raise `PinterestPayloadError`.

`build_csv_row` / `validate_csv_row(s)` normalise sidecars into the Business
Hub import CSV and enforce the same limits plus board/keywords/media checks;
`--strict` turns warnings (missing affiliate disclosure, duplicate titles/URLs,
non-standard board names) into errors.

### 2.5 Ссылки: только активные

Пин без рабочей ссылки — потерянный клик. Правила:

* **никаких заглушек**: `is.gd`/`v.gd`, `example.com`, `localhost` и любые
  нерабочие сокращатели запрещены;
* только `https://`, длина ≤ 500 символов, без пробелов;
* партнёрские пины берут ссылку из `config/affiliate_links.yaml`
  (`programs.<name>.partner_url`), а не хардкодят её в скрипте;
* если партнёрской ссылки нет — используется hub (`https://valdislavn-spec.github.io/content-factory/`),
  он тоже проверяется;
* батч не собирается, пока ссылки не проверены: `--check-links` у
  `build_photo_pins.py` и `build_pinterest_csv.py`;
* независимая проверка артефактов — `scripts/check_links.py`.

Маппинг v5-батча:

| Пин | Программа | Ссылка |
|---|---|---|
| bali-budget-qr | aviasales | `https://aviasales.tpk.ro/2ZW95Xpf` |
| dubai-weekend-qr | aviasales | `https://aviasales.tpk.ro/2ZW95Xpf` |
| winter-sun-qr | aviasales | `https://aviasales.tpk.ro/2ZW95Xpf` |
| europe-under-300-qr | aviasales | `https://aviasales.tpk.ro/2ZW95Xpf` |
| travel-esim-qr | yesim | `https://yesim.tpk.ro/aU7AT4LC` |
| car-rental-qr | localrent | `https://localrent.tpk.ro/vGHu8Vuj` |
| flight-compensation-qr | airhelp | `https://airhelp.tpk.ro/WbJKruUg` |
| gradient/*.png | — (hub fallback) | `https://valdislavn-spec.github.io/content-factory/` |

Проверка:

```bash
# офлайн: заглушки, схемы, домены
python3 scripts/check_links.py

# + живые HTTP-статусы (после публикации картинок/страниц)
python3 scripts/check_links.py --live --json /tmp/pins-links.json
```

`check_links.py` сканирует sidecar-JSON и CSV батча (`link`, `image_url`,
`Media URL`), печатает таблицу статусов и выходит с кодом 1, если есть
мёртвые/заглушечные ссылки — удобно встроить в CI перед импортом.

---

## 3. Rendering workflow

Use the DSH python (Pillow 12) for images and install `segno` for QR codes:

```bash
# 1) Photo pins (real Commons photos, scrim, attribution, QR, payload sidecars)
#    --check-links live-проверяет партнёрские ссылки до рендера
PYTHONPATH=/tmp/segno /Users/vd/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3 \
  scripts/build_photo_pins.py --out docs/assets/pins-v5 --check-links

# 2) Gradient pins from config/pins.yaml (no AI key needed)
PYTHONPATH=/tmp/segno /Users/vd/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3 \
  scripts/generate_pins.py --out docs/assets/pins-v5/gradient --limit 2 --no-ai

# 3) QA report (metrics/gates из sidecar-ов)
PYTHONPATH=/tmp/segno /Users/vd/.dsh/dsh-runtimes/dsh-primary-runtime/dependencies/python/bin/python3 \
  scripts/build_pin_qa_report.py --pins docs/assets/pins-v5

# 4) Build and validate the Pinterest import CSV (links: offline + live)
python3 scripts/build_pinterest_csv.py --pins docs/assets/pins-v5 --out docs/pinterest-import-v5.csv --strict --check-links

# 5) Independent link audit (offline; --live после публикации)
python3 scripts/check_links.py --live

# 6) Quality gates
PYTHONPATH=/tmp/cfdeps:. python3 -m pytest -q tests/test_brand_design.py tests/test_pins.py tests/test_pin_links.py
```

`scripts/generate_pins.py` keeps the original CLI (`--out`, `--limit`,
`--no-ai`, `--date`, `--rotate`, `--config`) and `config/pins.yaml`
compatibility, and still uses Hugging Face backgrounds when
`HUGGINGFACE_API_KEY`/`HF_TOKEN` is present (falling back to the gradient).
Each sidecar now also contains `board`, `keywords`, `variant` and a measured
`metrics` block.  `scripts/build_photo_pins.py` keeps `--photos`/`--out` and
adds `--limit`/`--no-qr`.

---

## 4. Samples: `docs/assets/pins-v5/` (v5 batch)

Nine fresh 1000×1500 pins (7 photo + 2 gradient) with JSON payloads and
measured metrics.  All numbers below are read back from each PNG/JSON pair.

| sample | variant | px | KB | min font | min body contrast | min heading contrast | margins L/T/R/B | title / desc chars |
|---|---|---|---|---|---|---|---|---|
| `bali-budget-qr.png` | photo | 1000×1500 | 1970 | 24 | 6.60 | 8.54 | 72/72/72/72 | 54 / 149 |
| `dubai-weekend-qr.png` | photo | 1000×1500 | 925 | 24 | 6.49 | 8.53 | 72/72/72/72 | 55 / 143 |
| `winter-sun-qr.png` | photo | 1000×1500 | 1167 | 24 | 5.76 | 6.77 | 72/72/72/72 | 44 / 147 |
| `europe-under-300-qr.png` | photo | 1000×1500 | 1381 | 24 | 7.53 | 10.99 | 72/72/72/72 | 45 / 148 |
| `travel-esim-qr.png` | photo | 1000×1500 | 1054 | 24 | 5.73 | 7.43 | 72/72/72/72 | 46 / 152 |
| `car-rental-qr.png` | photo | 1000×1500 | 929 | 24 | 6.46 | 8.16 | 72/72/72/72 | 58 / 153 |
| `flight-compensation-qr.png` | photo | 1000×1500 | 847 | 24 | 9.20 | 9.03 | 72/72/72/72 | 51 / 163 |
| `gradient/01-europe-for-under-300.png` | gradient | 1000×1500 | 91 | 24 | 7.59 | 16.92 | 72/72/72/72 | 35 / 148 |
| `gradient/02-bali-on-a-budget.png` | gradient | 1000×1500 | 85 | 24 | 9.34 | 16.92 | 72/72/72/72 | 37 / 125 |

Machine-readable batch summary: `docs/assets/pins-v5/qa-report.json`
(`summary.passed == summary.samples`, min body/heading contrast, min margin,
max title/description lengths).

Every row: 2:3 RGBA→RGB PNG, no text block wider than its box, CTA + disclosure
present, footer QR in the photo batch, valid Pinterest payload
(`validate_pinterest_payload` returns no problems) and a non-empty board/keyword
list.  `python3 scripts/build_pinterest_csv.py --pins docs/assets/pins-v5
--strict` writes 9 rows (7 photo + 2 gradient) with **0 warnings, 0 errors**.

Sidecars look like this (`bali-budget-qr.json`):

```json
{
  "image_url": "https://valdislavn-spec.github.io/content-factory/assets/pins-v5/bali-budget-qr.png",
  "niche": "travel",
  "affiliate": true,
  "disclosure": "Ad · affiliate link",
  "board": "Travel ideas",
  "keywords": ["travel tips", "city breaks", "bali", "..."],
  "variant": "photo",
  "pin": {"board_id": "<BOARD_ID>", "title": "...", "description": "...", "alt_text": "...",
          "link": "https://aviasales.tpk.ro/2ZW95Xpf", "media_source": {"source_type": "image_url", "url": "..."}},
  "metrics": {"min_font_size": 24, "min_body_contrast": 6.6, "min_heading_contrast": 8.54,
              "margins": {"left": 72, "top": 72, "right": 72, "bottom": 72},
              "blocks": [{"role": "headline", "font_size": 136, "line_width": 698, "box_width": 856, ...}]}
}
```

---

## 5. Before / after

Committed v4 output (`docs/assets/pins/photo/*.png`, `docs/assets/pins/*.png`)
versus the new v5 batch (`docs/assets/pins-v5/`):

| Aspect | v4 (`scripts/build_photo_pins.py` before) | v5 (`content_factory/brand/design.py`) |
|---|---|---|
| Layout | hard-coded y positions, text could run under the CTA/QR | flex layout with safe-area validator; overflow raises |
| Text fit | wrap + `[:3]` slice (could clip) | `fit_text` wrap + max-lines + shrink to ≥ 24 px, or raise |
| Min font | 20 px (attribution) / 22 px (tag) | 24 px everywhere |
| Contrast | dark overlay only, never measured; bright photo areas could fail | scrim + per-block worst-case measurement, auto contrast panels, renderer raises below 4.5 / 3.0 |
| Margins | 64 px hard-coded | 72 px designed, validated ≥ 64 |
| Brand | none | `CF` monogram + letterspaced `CONTENT FACTORY` wordmark |
| Headline | fixed 124 px, could overflow 3 lines | auto-fit Playfair ≤ 3 lines, optical centering |
| Footer | plain text lines; "Ad" + attribution at 20 px | rounded footer band: disclosure (accent), attribution (license preserved), site, optional QR card |
| Payload | title/description truncated blindly | validated title ≤ 100 / description ≤ 500 (CTA + disclosure kept), alt text, board, keywords |
| CSV | silent truncation, no checks | validation errors block the CSV; `--strict` for warnings |
| Verification | manual eyeballing | `tests/test_brand_design.py` + measured `metrics` in every sidecar |

Note: the old v4 files remain in place (they are referenced by published
CSV/pins); v5 is a separate, non-overwriting batch.

---

## 6. QA checklist (run before importing a batch)

Automated (required):

- [ ] `PYTHONPATH=/tmp/cfdeps:. python3 -m pytest -q tests` is green.
- [ ] `PYTHONPATH=/tmp/cfdeps:. python3 -m pytest -q tests/test_brand_design.py`
      passes (pure layout/design + Pillow render gates when available).
- [ ] `python3 scripts/build_photo_pins.py --out <dir>` exits 0 (quality gates
      would raise otherwise).
- [ ] `python3 scripts/build_pinterest_csv.py --pins <dir> --out <csv> --strict`
      exits 0 with 0 errors/warnings.
- [ ] `python3 scripts/check_links.py --live` exits 0 (all `link`/`image_url` are active).
- [ ] Sidecar `pin.link` — https, не `is.gd`/`example.com`, совпадает с партнёрской ссылкой.
- [ ] Every PNG in the batch is 1000×1500 and has a matching JSON sidecar with
      `metrics.violations()` empty (no overflow, min font ≥ 24, body contrast
      ≥ 4.5, heading ≥ 3.0, margins ≥ 64).

Manual (spot-check the images, not just the numbers):

- [ ] Headline readable in a 2:3 thumbnail; one idea per pin.
- [ ] No text sits on a busy/photo detail without a scrim (the engine samples,
      but check the composition looks intentional).
- [ ] CTA and disclosure visually present; affiliate pins show `Ad · affiliate
      link`.
- [ ] Photo attribution present and license correct (CC BY / CC BY-SA need
      author + license; update `docs/assets/photos/credits.json` if reusing).
- [ ] QR code (if used) scans to the same destination as `pin.link`.
- [ ] Title/description read naturally, primary keyword early, no clickbait,
      promise matches the landing page.
- [ ] Media URL is publicly reachable on GitHub Pages (200, correct content
      type) before the CSV import.
- [ ] No duplicate creative/title in the batch (validator warns; rotate
      backgrounds and headlines instead of re-publishing).

---

## 7. Risks and limitations

- **Photos are a fixed asset pool.** `car.jpg` is a park/road photo rather than a
  car; the design system cannot fix subject relevance.  Replace assets in
  `docs/assets/photos/` (and `credits.json`) when better CC photos are found.
- **Layout degradation is intentional and recorded.** Very long text can drop
  trailing bullets (`dropped`) or shrink the headline below the recommended
  64 px (fallback sizes down to 24 px, with a warning).  Review
  `metrics.warnings` when a batch shows these.
- **The renderer raises instead of clipping.** A pin whose text cannot fit at
  the minimum sizes fails generation; shorten the copy instead of loosening
  gates.
- **Measured contrast uses the worst pixel** under each text block; a
  deliberately bright panel/text combination can still look low-contrast to a
  human even when WCAG passes — spot-check the images.
- **QR codes are optional and usually unnecessary for Pinterest** (the pin link
  already carries the destination).  They are kept for photo pins because the
  existing workflow/print use case expects them; use `--no-qr` if they hurt
  thumbnail readability.
- **PNG size:** photo pins are ~0.8–2 MB (photo detail), gradient pins ~90 KB.
  GitHub Pages handles both; re-encode with optimization only if the published
  page gets slow.
- **Attribution truncation** keeps author + license before the source label so
  legal credit is preserved, but very long author names are shortened; check
  CC BY-SA requirements when the author string is unusual.
- **Pinterest API/CSV limits are enforced client-side.** Pinterest may still
  reject a board/title for policy reasons; `board_id` `<BOARD_ID>` is a
  placeholder until `PINTEREST_BOARD_ID` is configured.
- **Pillow is optional for tests, required for rendering.** In a plain venv the
  five image-render tests are skipped (design/layout tests still run); CI/image
  rendering must use the DSH python or install `Pillow` + `segno`.
- **Ink AI backgrounds** (`HUGGINGFACE_API_KEY`) go through the same gates; a
  bright AI image gets the same scrim/panel treatment, and a photo variant is
  only produced when generation succeeds (otherwise gradient fallback).

---

## 8. References

- WCAG 2.1 contrast requirements: <https://www.w3.org/WAI/WCAG21/Understanding/contrast-minimum.html>
- `docs/pins.md` — existing pin factory overview (older renderer).
- `docs/assets/photos/credits.json` — photo authors and licenses.
- `tests/test_brand_design.py` — executable version of this document's rules.
- `content_factory/brand/design.py` — tokens, layout engine, renderer, payload
  and CSV helpers.
