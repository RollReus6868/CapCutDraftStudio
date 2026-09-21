"""Test cho kho hiệu ứng ảnh và bộ chọn hiệu ứng."""
from __future__ import annotations

import pytest

from capcut_draft_studio import animations as an


# --------------------------------------------------------------------------- #
# Kho hiệu ứng
# --------------------------------------------------------------------------- #
def test_catalog_has_eight_effects_with_unique_keys():
    assert len(an.ANIMS) == 8
    assert len(set(an.EFFECT_KEYS)) == 8
    assert set(an.EFFECT_KEYS) == set(an.BY_KEY)


def test_every_effect_has_vietnamese_label():
    for anim in an.ANIMS:
        assert anim.label and anim.label != anim.key


@pytest.mark.parametrize("anim", an.ANIMS, ids=[a.key for a in an.ANIMS])
def test_moving_effects_are_zoomed_enough_to_hide_black_borders(anim):
    """Ảnh phải luôn to hơn khung hình ít nhất bằng độ dịch của nó."""
    if not anim.moves:
        return
    assert anim.min_scale() >= anim.required_scale(), (
        f"{anim.key}: phóng {anim.min_scale():.3f} nhưng cần "
        f"{anim.required_scale():.3f} để che hết mép")


def test_pure_zoom_effects_do_not_move():
    for key in ("zoom_in", "zoom_out"):
        assert not an.BY_KEY[key].moves


def test_keyframes_for_zoom_only_emits_scale():
    specs = an.keyframes_for("zoom_in")
    assert specs == [("uniform_scale", 1.0, 1.08)]


def test_keyframes_for_pan_emits_constant_scale_plus_movement():
    specs = dict((p, (a, b)) for p, a, b in an.keyframes_for("pan_left"))
    assert specs["uniform_scale"] == (an.PAN_ZOOM, an.PAN_ZOOM)
    assert specs["position_x"] == (0.10, -0.10)
    assert "position_y" not in specs


def test_keyframes_for_diagonal_emits_all_three():
    props = [p for p, _, _ in an.keyframes_for("zoom_in_pan")]
    assert props == ["uniform_scale", "position_x", "position_y"]


def test_keyframes_for_unknown_key_is_empty():
    assert an.keyframes_for("khong_ton_tai") == []


# --------------------------------------------------------------------------- #
# normalize_mode
# --------------------------------------------------------------------------- #
@pytest.mark.parametrize("raw,expected", [
    ("random", "random"),
    ("RANDOM", "random"),
    ("  variety ", "variety"),
    ("zoom_in", "zoom_in"),
    ("off", "off"),
    ("", "variety"),
    (None, "variety"),
    ("hieu_ung_la", "variety"),
])
def test_normalize_mode(raw, expected):
    assert an.normalize_mode(raw) == expected


# --------------------------------------------------------------------------- #
# AnimPicker
# --------------------------------------------------------------------------- #
def test_off_mode_returns_off():
    picker = an.AnimPicker("off")
    assert [picker.pick(i) for i in range(5)] == ["off"] * 5


def test_variety_cycles_through_all_effects_in_order():
    picker = an.AnimPicker("variety")
    got = [picker.pick(i) for i in range(len(an.EFFECT_KEYS) * 2)]
    assert got[:8] == list(an.EFFECT_KEYS)
    assert got[8:] == list(an.EFFECT_KEYS)


def test_explicit_effect_is_always_used():
    picker = an.AnimPicker("pan_right")
    assert [picker.pick(i) for i in range(6)] == ["pan_right"] * 6


def test_random_never_repeats_adjacent_scenes():
    picker = an.AnimPicker("random", seed=1234)
    got = [picker.pick(i) for i in range(400)]
    repeats = [(a, b) for a, b in zip(got, got[1:]) if a == b]
    assert repeats == []


def test_random_stays_inside_catalog_and_uses_every_effect():
    picker = an.AnimPicker("random", seed=7)
    got = [picker.pick(i) for i in range(300)]
    assert set(got) <= set(an.EFFECT_KEYS)
    assert set(got) == set(an.EFFECT_KEYS), "300 cảnh mà vẫn sót hiệu ứng chưa dùng"


def test_random_is_reproducible_with_same_seed():
    a = [an.AnimPicker("random", seed=42).pick(i) for i in range(20)]
    b = [an.AnimPicker("random", seed=42).pick(i) for i in range(20)]
    assert a == b


def test_random_differs_without_seed_across_pickers():
    runs = {tuple(an.AnimPicker("random").pick(i) for i in range(40))
            for _ in range(8)}
    assert len(runs) > 1, "không seed mà 8 lần chạy ra kết quả y hệt nhau"


def test_random_is_reasonably_balanced():
    picker = an.AnimPicker("random", seed=2026)
    got = [picker.pick(i) for i in range(800)]
    counts = {k: got.count(k) for k in an.EFFECT_KEYS}
    expected = 800 / len(an.EFFECT_KEYS)
    for key, n in counts.items():
        assert 0.6 * expected < n < 1.6 * expected, f"{key} lệch quá nhiều: {n}"


def test_picker_normalizes_unknown_mode():
    picker = an.AnimPicker("mode_la_hoac")
    assert picker.mode == "variety"
    assert picker.pick(0) == an.EFFECT_KEYS[0]


def test_describe_is_human_readable():
    assert "ngẫu nhiên" in an.AnimPicker("random").describe()
    assert "luân phiên" in an.AnimPicker("variety").describe()
    assert an.AnimPicker("off").describe() == "tắt"
    assert an.AnimPicker("pan_up").describe() == "trượt lên trên"


# --------------------------------------------------------------------------- #
# Danh sách cho giao diện
# --------------------------------------------------------------------------- #
def test_mode_choices_cover_all_modes_without_duplicates():
    keys = [k for k, _ in an.MODE_CHOICES]
    labels = [v for _, v in an.MODE_CHOICES]
    assert len(keys) == len(set(keys))
    assert len(labels) == len(set(labels))
    assert set(keys) == set(an.EFFECT_KEYS) | {"random", "variety", "off"}


def test_random_is_offered_first_in_the_dropdown():
    assert an.MODE_CHOICES[0][0] == "random"


def test_every_choice_survives_normalize():
    for key, _ in an.MODE_CHOICES:
        assert an.normalize_mode(key) == key
