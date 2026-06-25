from __future__ import annotations

from navercafe_app.gui_fe_board_archive import PresetStore


def test_preset_store_upsert_replaces_by_name(tmp_path) -> None:
    store = PresetStore(tmp_path / "presets.json")
    first = {"name": "줌슐랭", "url": "https://example.com/1", "board_name": "old"}
    second = {"name": "줌슐랭", "url": "https://example.com/2", "board_name": "new"}

    store.upsert(first)
    store.upsert(second)

    presets = store.load()
    assert len(presets) == 1
    assert presets[0]["url"] == "https://example.com/2"
    assert presets[0]["board_name"] == "new"


def test_preset_store_ignores_invalid_json(tmp_path) -> None:
    path = tmp_path / "bad.json"
    path.write_text("not-json", encoding="utf-8")
    assert PresetStore(path).load() == []
