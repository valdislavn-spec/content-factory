"""Tests for the brand design system + overflow-safe pin layout engine.

The layout/design tests are pure math (no Pillow required).  Image-render
tests are marked optional: they run only when Pillow is importable.
"""

from __future__ import annotations

import json

import pytest

from content_factory.brand import design as d


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


class FakeMeasurer:
    """Deterministic measurer so layout math is reproducible without fonts."""

    FACTORS = {"sans": 0.50, "display": 0.58}

    def measure(self, text: str, size: int, family: str = "sans") -> float:
        return len(str(text)) * int(size) * self.FACTORS.get(family, self.FACTORS["sans"])


def make_content(**overrides) -> d.PinContent:
    base = dict(
        niche="travel",
        headline="Europe for under $300",
        subtitle="Real cheap city breaks: flights + 3 nights, no tourist traps",
        bullets=(
            "Cheapest months: March-May",
            "Carry-on only, book 6-8 weeks ahead",
            "Mon-Wed departures are cheaper",
        ),
        cta="See the deals",
        tag="TRAVEL",
        disclosure="Save this guide",
        title="Cheap Europe city breaks under $300",
        description="Budget city breaks in Europe: cheapest months, carry-on tips and booking windows.",
        alt_text="Europe city breaks under $300",
    )
    base.update(overrides)
    return d.PinContent(**base)


def layout_for(content: d.PinContent | None = None, **kwargs):
    content = content or make_content()
    kwargs.setdefault("measure", FakeMeasurer())
    return d.layout_pin(content, **kwargs)


def require_pil():
    return pytest.importorskip("PIL")


def require_fonts() -> None:
    for file_name in d.FONT_FILES.values():
        if not (d.FONT_DIR / file_name).exists():
            pytest.skip("brand fonts are not installed in assets/fonts")


# ---------------------------------------------------------------------------
# Tokens / constraints
# ---------------------------------------------------------------------------


def test_pin_size_and_aspect():
    assert d.PIN_SIZE == (1000, 1500)
    assert d.PIN_ASPECT == pytest.approx(2 / 3)


def test_design_tokens_meet_quality_floors():
    assert d.SAFE_MARGIN >= 64
    assert d.MIN_SAFE_MARGIN >= 64
    assert d.DESIGN.margin >= d.MIN_SAFE_MARGIN
    assert d.DESIGN.min_font_size >= 24
    assert d.MIN_FONT_SIZE >= 24
    assert d.DESIGN.radius_card > 0
    assert d.DESIGN.radius_pill > 0
    assert d.DESIGN.gaps and all(gap > 0 for gap in d.DESIGN.gaps)


def test_type_scale_never_below_min_font():
    for role, size in d.TYPE_SCALE.items():
        assert size >= d.MIN_FONT_SIZE, role
    assert min(d.HEADLINE_SIZES) >= d.MIN_FONT_SIZE
    assert min(d.SUBTITLE_SIZES) >= d.MIN_FONT_SIZE
    assert min(d.BULLET_SIZES) >= d.MIN_FONT_SIZE
    assert min(d.CTA_SIZES) >= d.MIN_FONT_SIZE
    assert d.SUBTITLE_MIN_SIZE >= d.MIN_FONT_SIZE


def test_pinterest_limits_are_documented_constants():
    assert d.TITLE_MAX == 100
    assert d.DESCRIPTION_MAX == 500
    assert d.ALT_TEXT_MAX == 500
    assert d.HEADLINE_MAX_LINES == 3
    assert d.BODY_CONTRAST >= 4.5
    assert d.HEADING_CONTRAST >= 3.0


# ---------------------------------------------------------------------------
# Colour / WCAG contrast
# ---------------------------------------------------------------------------


def test_contrast_ratio_extremes():
    assert d.contrast_ratio((0, 0, 0), (255, 255, 255)) == pytest.approx(21.0, abs=1e-6)
    assert d.contrast_ratio((255, 255, 255), (0, 0, 0)) == pytest.approx(21.0, abs=1e-6)
    assert d.contrast_ratio((18, 52, 86), (18, 52, 86)) == pytest.approx(1.0)


def test_relative_luminance_known_values():
    assert d.relative_luminance((0, 0, 0)) == pytest.approx(0.0)
    assert d.relative_luminance((255, 255, 255)) == pytest.approx(1.0)


def test_cream_and_muted_are_readable_on_ink():
    assert d.contrast_ratio(d.CREAM, d.INK) >= d.BODY_CONTRAST
    assert d.contrast_ratio(d.MUTED, d.INK) >= d.BODY_CONTRAST


def test_ensure_contrast_keeps_passing_colour_and_fixes_low_contrast():
    passing = d.ensure_contrast(d.CREAM, d.INK, d.BODY_CONTRAST)
    assert passing == d.CREAM
    adjusted = d.ensure_contrast((40, 42, 48), d.INK, d.BODY_CONTRAST)
    assert d.contrast_ratio(adjusted, d.INK) >= d.BODY_CONTRAST
    with pytest.raises(ValueError):
        d.ensure_contrast(d.CREAM, d.INK, 22.0)


def test_best_text_color_picks_highest_contrast():
    assert d.best_text_color((255, 255, 255)) == d.INK
    assert d.best_text_color((0, 0, 0)) == d.WHITE


def test_hex_rgb_roundtrip_and_fallback():
    assert d.hex_to_rgb("#FF7A45") == (255, 122, 69)
    assert d.hex_to_rgb("2ECC71") == (46, 204, 113)
    assert d.hex_to_rgb("zzz") == (79, 140, 255)
    assert d.rgb_to_hex((255, 122, 69)) == "#FF7A45"


def test_mix_and_composite_over():
    assert d.mix((0, 0, 0), (255, 255, 255), 0.5) == (128, 128, 128)
    assert d.composite_over((0, 0, 0), (255, 255, 255), 1.0) == (0, 0, 0)
    assert d.composite_over((0, 0, 0), (255, 255, 255), 0.0) == (255, 255, 255)


# ---------------------------------------------------------------------------
# Themes / gradients / photo cover / scrim
# ---------------------------------------------------------------------------


def test_theme_for_known_niches():
    travel = d.theme_for("travel")
    ai = d.theme_for("AI")
    assert travel.accent_hex == "#FF7A45"
    assert ai.accent_hex == "#4C9AFF"
    assert d.theme_for("unknown").niche == "default"
    custom = d.theme_for("travel", accent="#123456")
    assert custom.accent == (18, 52, 86)


def test_theme_cta_and_accent_text_contrast():
    for niche in ("travel", "crypto", "ai", "sports", "default"):
        theme = d.theme_for(niche)
        assert theme.cta_contrast >= d.BODY_CONTRAST, niche
        assert theme.accent_on_ink_contrast >= d.BODY_CONTRAST, niche
        assert d.contrast_ratio(theme.headline, theme.ink) >= d.BODY_CONTRAST
        for stop in theme.gradient:
            assert d.contrast_ratio(theme.headline, stop) >= d.BODY_CONTRAST, niche


def test_gradient_stops_multi_stop_math():
    theme = d.theme_for("crypto")
    stops = d.gradient_stops(theme)
    assert len(stops) == 3
    positions = [position for position, _ in stops]
    assert positions == sorted(positions)
    assert positions[0] == 0.0 and positions[-1] == 1.0
    assert d.gradient_color_at(stops, 0.0) == stops[0][1]
    assert d.gradient_color_at(stops, 1.0) == stops[-1][1]
    middle = d.gradient_color_at(stops, positions[1])
    assert middle == stops[1][1]
    tile = d.interpolate_gradient(stops, tile=16)
    assert len(tile) == 16 and tile[0] == stops[0][1] and tile[-1] == stops[-1][1]


def test_scrim_alpha_is_bounded_and_dark_at_top():
    assert 0.0 <= d.scrim_alpha_at(0.0) <= 1.0
    assert 0.0 <= d.scrim_alpha_at(1.0) <= 1.0
    assert d.scrim_alpha_at(0.0) > d.scrim_alpha_at(0.5)
    worst = d.scrim_color_at(0.0)
    assert d.contrast_ratio(d.CREAM, worst) >= d.BODY_CONTRAST


def test_cover_box_math():
    box = d.cover_box(1600, 900, 1000, 1500)
    assert box[2] - box[0] == 1000
    assert box[3] - box[1] == 1500
    inner = d.cover_box(900, 1600, 1000, 1500)
    assert inner[2] - inner[0] == 1000 and inner[3] - inner[1] == 1500
    square = d.cover_box(1000, 1000, 1000, 1500)
    assert square[3] - square[1] == 1500
    with pytest.raises(ValueError):
        d.cover_box(0, 10, 1000, 1500)


# ---------------------------------------------------------------------------
# Text fitting / wrapping
# ---------------------------------------------------------------------------


def test_wrap_text_respects_width_and_explicit_breaks():
    measurer = FakeMeasurer()
    lines = d.wrap_text("BALI ON\nA BUDGET", measurer, 100, 10_000)
    assert lines == ["BALI ON", "A BUDGET"]
    wrapped = d.wrap_text("one two three four five six", measurer, 40, 100)
    for line in wrapped:
        assert measurer.measure(line, 40) <= 100


def test_wrap_text_raises_for_unbreakable_word():
    with pytest.raises(d.TextOverflowError):
        d.wrap_text("A" * 300, FakeMeasurer(), 40, 100)


def test_truncate_to_width_fits_and_ellipsizes():
    measurer = FakeMeasurer()
    long_text = "A very long subtitle that will certainly not fit"
    trimmed = d.truncate_to_width(long_text, measurer, 24, 180)
    assert trimmed.endswith("\u2026")
    assert measurer.measure(trimmed, 24) <= 180
    assert d.truncate_to_width("short", measurer, 24, 180) == "short"


def test_fit_text_picks_largest_size_within_limits():
    measurer = FakeMeasurer()
    fit = d.fit_text(
        "Europe for under $300",
        measurer,
        max_width=856,
        sizes=d.HEADLINE_SIZES,
        max_lines=3,
        family="display",
        line_height_ratio=1.16,
    )
    assert fit.size >= d.MIN_FONT_SIZE
    assert len(fit.lines) <= 3
    assert all(measurer.measure(line, fit.size, "display") <= 856 for line in fit.lines)
    assert fit.height == fit.line_height * len(fit.lines)


def test_fit_text_can_shrink_for_narrow_box():
    measurer = FakeMeasurer()
    wide = d.fit_text(
        "Bali on a budget",
        measurer,
        max_width=900,
        sizes=d.HEADLINE_SIZES,
        max_lines=3,
        family="display",
    )
    narrow = d.fit_text(
        "Bali on a budget",
        measurer,
        max_width=400,
        sizes=d.HEADLINE_SIZES,
        max_lines=3,
        family="display",
    )
    assert narrow.size <= wide.size
    assert narrow.size >= d.MIN_FONT_SIZE


def test_fit_text_raises_when_impossible():
    with pytest.raises(d.TextOverflowError):
        d.fit_text(
            "Supercalifragilisticexpialidocious" * 4,
            FakeMeasurer(),
            max_width=200,
            sizes=d.HEADLINE_SIZES,
            max_lines=3,
            family="display",
        )


def test_fit_single_line_truncates_instead_of_raising():
    fit = d.fit_single_line(
        "Photo: Someone with a very long name / CC BY 4.0 / Wikimedia",
        FakeMeasurer(),
        max_width=220,
        sizes=(26, 24),
    )
    assert fit.size >= d.MIN_FONT_SIZE
    assert fit.lines[0].endswith("\u2026")
    assert FakeMeasurer().measure(fit.lines[0], fit.size) <= 220


def test_letterspaced_width():
    measurer = FakeMeasurer()
    plain = measurer.measure("CONTENT", 24)
    assert d.letterspaced_width("CONTENT", measurer, 24, 2) == pytest.approx(plain + 12)
    assert d.letterspaced_width("", measurer, 24, 2) == 0


# ---------------------------------------------------------------------------
# PinContent adapter
# ---------------------------------------------------------------------------


def test_pin_content_from_mapping_and_object():
    mapping = {
        "niche": "ai",
        "headline": "AI tools",
        "bullets": ["one", "two", ""],
        "cta": "See the list",
        "accent": "#123456",
    }
    content = d.PinContent.from_mapping(mapping)
    assert content.niche == "ai"
    assert content.bullets == ("one", "two")
    assert d.PinContent.from_object(content) is content
    from content_factory.integrations.pins import PinSpec

    spec = PinSpec(niche="sports", headline="NFL picks", bullets=["a", "b"], cta="See numbers")
    adapted = d.PinContent.from_object(spec)
    assert adapted.niche == "sports"
    assert adapted.bullets == ("a", "b")
    # PinSpec always carries an explicit disclosure; keep it verbatim.
    from content_factory.integrations.pins import DISCLOSURE

    assert adapted.clean_disclosure == DISCLOSURE


def test_clean_disclosure_switches_on_link():
    assert d.PinContent(link="https://example.com").clean_disclosure == d.DISCLOSURE_AFFILIATE
    assert d.PinContent().clean_disclosure == d.DISCLOSURE_GUIDE
    assert d.PinContent(disclosure="Custom").clean_disclosure == "Custom"


# ---------------------------------------------------------------------------
# Layout engine
# ---------------------------------------------------------------------------


def test_layout_is_valid_and_overflow_safe():
    layout = layout_for()
    assert layout.validate() == []
    assert layout.width == 1000 and layout.height == 1500
    assert layout.aspect_ratio == pytest.approx(2 / 3)
    assert layout.margin >= d.MIN_SAFE_MARGIN
    assert layout.min_font_size >= d.MIN_FONT_SIZE
    assert len(layout.headline.lines) <= d.HEADLINE_MAX_LINES
    assert layout.cta.label.strip()
    assert any(block.role == "disclosure" for block in layout.footer.texts)
    assert layout.header.tag is not None
    assert layout.header.brand.monogram_text == "CF"


def test_layout_blocks_inside_safe_area_and_not_overlapping():
    layout = layout_for()
    for name, rect in layout.top_level_rects():
        assert rect.x >= layout.margin, name
        assert rect.y >= layout.margin, name
        assert rect.right <= layout.width - layout.margin, name
        assert rect.bottom <= layout.height - layout.margin, name
    rects = layout.top_level_rects()
    for index, (name_a, rect_a) in enumerate(rects):
        for name_b, rect_b in rects[index + 1:]:
            assert not rect_a.intersects(rect_b), "%s overlaps %s" % (name_a, name_b)


def test_layout_text_lines_fit_their_boxes():
    layout = layout_for()
    for block in layout.text_blocks():
        assert block.line_width <= block.rect.w + 1, block.role
        assert block.font_size >= d.MIN_FONT_SIZE, block.role


def test_layout_is_deterministic_and_json_serialisable():
    first = layout_for().to_dict()
    second = layout_for().to_dict()
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)
    assert json.loads(json.dumps(first))["min_font_size"] >= d.MIN_FONT_SIZE


def test_layout_photo_variant_valid():
    layout = layout_for(variant="photo")
    assert layout.validate() == []
    assert layout.variant == "photo"


def test_layout_with_qr_reserves_footer_space():
    layout = layout_for(qr=True)
    assert layout.validate() == []
    assert layout.qr is not None
    assert layout.footer.rect.contains(layout.qr)
    for block in layout.footer.texts:
        assert block.rect.right <= layout.qr.x
    no_qr = layout_for(qr=False)
    assert no_qr.qr is None
    assert layout.footer.rect.h > no_qr.footer.rect.h


def test_layout_centres_content_when_room_allows():
    sparse = d.PinContent(niche="travel", headline="Paris", cta="Read more", disclosure="Save this guide")
    compact = layout_for(sparse)
    assert compact.validate() == []
    assert any("centred" in warning for warning in compact.warnings)


def test_layout_shrinks_spacing_or_content_instead_of_overflowing():
    content = make_content(
        headline="Travel insurance mistakes that void your cover abroad",
        subtitle=(
            "Five common mistakes: alcohol-related claims, rental excess cover, adventure "
            "sports riders, pre-existing conditions and missed connections"
        ),
        bullets=(
            "Alcohol-related claims are usually excluded from travel policies",
            "Check whether your rental car excess cover is included or separate",
            "Adventure sports almost always need a dedicated rider and extra premium",
        ),
    )
    layout = layout_for(content)
    assert layout.validate() == []
    assert layout.headline.rect.bottom <= layout.cta.rect.y
    if layout.bullets:
        assert max(card.rect.bottom for card in layout.bullets) <= layout.cta.rect.y


def test_layout_drops_bullets_when_needed_and_records_warnings():
    many = tuple(
        "This is a deliberately long bullet number %d that takes two lines to render on the pin" % index
        for index in range(1, 4)
    )
    content = make_content(
        headline="A long headline that will need to shrink quite a lot to fit this pin",
        subtitle="And a long subtitle too: " + "extra words " * 20,
        bullets=many,
    )
    layout = layout_for(content)
    assert layout.validate() == []
    assert layout.dropped or len(layout.bullets) == 3


def test_layout_raises_when_canvas_is_too_small():
    with pytest.raises(d.LayoutOverflowError):
        d.layout_pin(make_content(), size=(200, 200), measure=FakeMeasurer())


def test_layout_raises_for_unbreakable_headline():
    content = make_content(headline="A" * 400)
    with pytest.raises(d.TextOverflowError):
        layout_for(content)


def test_layout_drops_impossible_subtitle_instead_of_raising():
    content = make_content(subtitle="word " * 300)
    layout = layout_for(content)
    assert layout.validate() == []
    assert layout.subtitle is None
    assert any("subtitle dropped" in warning for warning in layout.warnings)


def test_assert_valid_raises_quality_error_for_bad_layout():
    layout = layout_for()
    assert layout.assert_valid() is layout


# ---------------------------------------------------------------------------
# Pinterest payload / CSV helpers
# ---------------------------------------------------------------------------


def test_pinterest_payload_limits_and_content():
    payload = d.build_pinterest_payload(make_content(), image_url="https://cdn.example.com/pin.png")
    assert len(payload["title"]) <= d.TITLE_MAX
    assert len(payload["description"]) <= d.DESCRIPTION_MAX
    assert len(payload["alt_text"]) <= d.ALT_TEXT_MAX
    assert "See the deals" in payload["description"]
    assert "Save this guide" in payload["description"]
    assert payload["media_source"] == {"source_type": "image_url", "url": "https://cdn.example.com/pin.png"}
    assert "link" not in payload
    assert d.validate_pinterest_payload(payload) == []


def test_pinterest_payload_clamps_long_fields_preserving_cta_and_disclosure():
    content = make_content(
        title="Europe " * 40,
        description="Budget tips " * 100,
        cta="Read the full guide",
        disclosure="Ad \u00b7 affiliate link",
    )
    payload = d.build_pinterest_payload(
        content, image_url="https://cdn.example.com/pin.png", include_link=False
    )
    assert len(payload["title"]) <= d.TITLE_MAX
    assert len(payload["description"]) <= d.DESCRIPTION_MAX
    assert "Read the full guide" in payload["description"]
    assert "Ad \u00b7 affiliate link" in payload["description"]
    assert d.validate_pinterest_payload(payload) == []


def test_pinterest_payload_includes_link_for_affiliate_pins():
    content = make_content(link="https://example.com/r/travel", disclosure="")
    payload = d.build_pinterest_payload(content, image_url="https://cdn.example.com/pin.png")
    assert payload["link"] == "https://example.com/r/travel"
    assert "Ad \u00b7 affiliate link" in payload["description"]


def test_pinterest_payload_rejects_invalid_media_url():
    with pytest.raises(d.PinterestPayloadError):
        d.build_pinterest_payload(make_content(), image_url="/local/pin.png")


def test_validate_pinterest_payload_catches_problems():
    bad = {
        "title": "",
        "description": "x" * (d.DESCRIPTION_MAX + 1),
        "alt_text": "a" * (d.ALT_TEXT_MAX + 1),
        "media_source": {"source_type": "image_url", "url": "ftp://bad"},
        "link": "not-a-url",
    }
    errors = d.validate_pinterest_payload(bad)
    assert len(errors) >= 4
    assert d.validate_pinterest_payload("not a mapping") == ["payload must be a mapping"]


def test_board_and_keywords_helpers():
    assert d.board_for_niche("travel") == "Travel ideas"
    assert d.board_for_niche("crypto") == "Crypto"
    assert d.board_for_niche("unknown") == "Pins"
    keywords = d.keywords_for("travel", "Cheap Europe city breaks", "Budget flights and hotels")
    assert keywords and len(keywords) <= 8
    assert len(set(keywords)) == len(keywords)
    assert all(keyword and len(keyword) <= 64 for keyword in keywords)
    assert "travel tips" in keywords


def test_csv_row_build_and_validation():
    meta = {
        "image_url": "https://cdn.example.com/pin.png",
        "niche": "travel",
        "affiliate": False,
        "disclosure": "Save this guide",
        "board": "Travel ideas",
        "keywords": ["travel tips", "city breaks"],
        "pin": d.build_pinterest_payload(make_content(), image_url="https://cdn.example.com/pin.png"),
    }
    row = d.build_csv_row(meta)
    errors, warnings = d.validate_csv_row(row, meta=meta)
    assert errors == []
    assert warnings == []
    assert row["Pinterest board"] == "Travel ideas"
    assert row["Keywords"] == "travel tips, city breaks"


def test_csv_row_validation_catches_bad_values():
    bad = {
        "Title": "",
        "Media URL": "not-a-url.png",
        "Pinterest board": "",
        "Description": "x" * (d.DESCRIPTION_MAX + 1),
        "Link": "javascript:alert(1)",
        "Keywords": "",
    }
    errors, _ = d.validate_csv_row(bad)
    assert any("Title" in error for error in errors)
    assert any("Media URL" in error for error in errors)
    assert any("board" in error.lower() for error in errors)
    assert any("Description" in error for error in errors)
    assert any("Keywords" in error for error in errors)
    assert any("Link" in error for error in errors)
    long_keyword = {"Keywords": "word " * 20}
    errors_long, _ = d.validate_csv_row(
        {"Title": "ok", "Media URL": "https://cdn.example.com/p.png", "Pinterest board": "Travel ideas",
         "Description": "ok", "Link": "", "Keywords": "fine"}, meta=None,
    )
    assert errors_long == []
    row = {
        "Title": "ok",
        "Media URL": "https://cdn.example.com/p.png",
        "Pinterest board": "Travel ideas",
        "Description": "ok",
        "Link": "",
        "Keywords": long_keyword["Keywords"],
    }
    errors_bad, _ = d.validate_csv_row(row)
    assert any("keyword" in error for error in errors_bad)


def test_csv_validation_warns_on_affiliate_disclosure_and_strict_mode():
    row = {
        "Title": "Travel eSIM guide",
        "Media URL": "https://cdn.example.com/p.png",
        "Pinterest board": "Travel ideas",
        "Description": "How travel eSIMs work and when they beat airport SIM cards.",
        "Link": "https://example.com/ad",
        "Keywords": "travel, esim",
    }
    meta = {"affiliate": True, "disclosure": "Ad \u00b7 affiliate link"}
    errors, warnings = d.validate_csv_row(row, meta=meta)
    assert errors == []
    assert any("disclosure" in warning for warning in warnings)
    strict_errors, strict_warnings = d.validate_csv_row(row, meta=meta, strict=True)
    assert strict_errors
    assert strict_warnings == []


def test_csv_validation_batch_detects_duplicates():
    row = {
        "Title": "Same title",
        "Media URL": "https://cdn.example.com/p.png",
        "Pinterest board": "Travel ideas",
        "Description": "Same description.",
        "Link": "",
        "Keywords": "travel",
    }
    errors, warnings = d.validate_csv_rows([dict(row), dict(row)])
    assert errors == []
    assert any("duplicate Title" in warning for warning in warnings)
    assert any("duplicate Media URL" in warning for warning in warnings)


# ---------------------------------------------------------------------------
# Render tests (optional: Pillow + fonts required)
# ---------------------------------------------------------------------------


def test_render_gradient_pin_quality_gates():
    require_pil()
    require_fonts()
    rendered = d.render_pin(make_content(), variants=("gradient",))["gradient"]
    assert rendered.image.size == (1000, 1500)
    assert rendered.image.mode == "RGB"
    metrics = rendered.metrics
    assert metrics.violations() == []
    assert metrics.min_font_size >= d.MIN_FONT_SIZE
    assert metrics.min_body_contrast >= d.BODY_CONTRAST
    assert metrics.min_heading_contrast >= d.HEADING_CONTRAST
    assert min(metrics.margins.values()) >= d.MIN_SAFE_MARGIN
    assert abs(metrics.aspect_ratio - 2 / 3) < 0.002
    for block in metrics.blocks:
        assert block["line_width"] <= block["box_width"] + 1, block["role"]
    assert rendered.layout.validate() == []


def test_render_photo_pin_with_qr(tmp_path):
    require_pil()
    require_fonts()
    pytest.importorskip("segno")
    photo = d.ROOT / "docs" / "assets" / "photos" / "bali.jpg"
    if not photo.exists():
        pytest.skip("sample photo is missing")
    content = make_content(
        niche="travel",
        headline="BALI ON\nA BUDGET",
        subtitle="7 days of rice terraces, surf and $3 meals",
        cta="Find flights",
        link="https://example.com/bali",
        attribution="Photo: Philip Nalangan \u00b7 CC BY 4.0 \u00b7 Wikimedia",
        tag="BUDGET",
    )
    rendered = d.render_pin(
        content,
        variants=("photo",),
        photo_path=photo,
        qr_data="https://example.com/bali",
    )["photo"]
    assert rendered.image.size == (1000, 1500)
    assert rendered.layout.qr is not None
    metrics = rendered.metrics
    assert metrics.violations() == []
    assert metrics.min_body_contrast >= d.BODY_CONTRAST
    assert any(block["role"] == "attribution" for block in metrics.blocks)
    target = rendered.save(tmp_path / "photo-pin.png")
    assert target.exists() and target.stat().st_size > 20_000


def test_render_variants_fall_back_to_gradient_without_photo():
    require_pil()
    require_fonts()
    rendered = d.render_pin(make_content(), variants=("photo",))
    assert "gradient" in rendered
    assert rendered["gradient"].image.size == (1000, 1500)
    both = d.render_pin(make_content(), variants=("photo", "gradient"))
    assert set(both) == {"gradient"}


def test_render_photo_variant_when_photo_available():
    require_pil()
    require_fonts()
    photo = d.ROOT / "docs" / "assets" / "photos" / "dubai.jpg"
    if not photo.exists():
        pytest.skip("sample photo is missing")
    rendered = d.render_pin(make_content(), variants=("photo", "gradient"), photo_path=photo)
    assert set(rendered) == {"photo", "gradient"}
    assert rendered["photo"].metrics.violations() == []
    assert rendered["gradient"].metrics.violations() == []


def test_render_pin_single_helper():
    require_pil()
    require_fonts()
    rendered = d.render_pin_single(make_content(), variant="gradient")
    assert rendered.variant == "gradient"
    assert rendered.size == (1000, 1500)


# ---------------------------------------------------------------------------
# Committed v5 sample batch: executable acceptance checks (pure JSON, no PIL)
# ---------------------------------------------------------------------------


def committed_v5_sidecars():
    samples_dir = d.ROOT / "docs" / "assets" / "pins-v5"
    if not samples_dir.exists():
        pytest.skip("docs/assets/pins-v5 is not present")
    sidecars = [path for path in sorted(samples_dir.rglob("*.json")) if path.name not in ("index.json", "meta.json", "qa-report.json")]
    if not sidecars:
        pytest.skip("no pin sidecars in docs/assets/pins-v5")
    return sidecars


def test_committed_v5_samples_have_valid_pinterest_payloads():
    for path in committed_v5_sidecars():
        meta = json.loads(path.read_text(encoding="utf-8"))
        payload = meta.get("pin") or {}
        assert payload, path.name
        assert d.validate_pinterest_payload(payload) == [], path.name
        assert 0 < len(payload["title"]) <= d.TITLE_MAX, path.name
        assert 0 < len(payload["description"]) <= d.DESCRIPTION_MAX, path.name
        assert 0 < len(payload["alt_text"]) <= d.ALT_TEXT_MAX, path.name
        assert meta.get("board"), path.name
        assert meta.get("keywords"), path.name
        assert meta.get("image_url", "").startswith("https://"), path.name


def test_committed_v5_samples_meet_layout_quality_gates():
    for path in committed_v5_sidecars():
        meta = json.loads(path.read_text(encoding="utf-8"))
        metrics = meta.get("metrics") or {}
        assert metrics, "metrics missing in %s" % path.name
        assert metrics["width"] == 1000 and metrics["height"] == 1500, path.name
        assert metrics["min_font_size"] >= d.MIN_FONT_SIZE, path.name
        assert metrics["min_body_contrast"] >= d.BODY_CONTRAST, path.name
        assert metrics["min_heading_contrast"] >= d.HEADING_CONTRAST, path.name
        assert min(metrics["margins"].values()) >= d.MIN_SAFE_MARGIN, path.name
        roles = {block["role"] for block in metrics["blocks"]}
        assert "cta" in roles and "disclosure" in roles, path.name
        for block in metrics["blocks"]:
            assert block["line_width"] <= block["box_width"] + 1, (path.name, block["role"])


def test_committed_v5_images_are_1000x1500_png():
    require_pil()
    from PIL import Image

    samples = committed_v5_sidecars()
    for sidecar in samples:
        png = sidecar.with_suffix(".png")
        assert png.exists(), png
        with Image.open(png) as image:
            assert image.size == (1000, 1500), png.name
            assert image.mode == "RGB", png.name
