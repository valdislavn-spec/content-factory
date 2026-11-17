import importlib.util
from pathlib import Path

P = Path(__file__).resolve().parent.parent / "scripts" / "buffer_es_channels_promo.py"
spec = importlib.util.spec_from_file_location("es_promo", P)
promo = importlib.util.module_from_spec(spec)
spec.loader.exec_module(promo)


def test_all_variants_fit_x_limit():
    for key, channel in promo.CHANNELS.items():
        for variant in range(len(channel["variants"])):
            assert promo.weighted_length(promo.build_text(key, variant)) <= 280


def test_every_post_has_disclosure_link_and_image():
    for key, channel in promo.CHANNELS.items():
        text = promo.build_text(key, 0)
        assert "Publicidad" in text
        assert channel["url"] in text
        assert channel["image"].startswith("https://")


def test_rotation_advances():
    state = {"index": 0, "variants": {}}
    first, _ = promo.pick(state)
    state["index"] = 1
    second, _ = promo.pick(state)
    assert first != second
