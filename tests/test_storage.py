from shorts.storage import Storage


def test_storage_marks_and_detects_seen(tmp_path):
    storage = Storage(tmp_path / "history.sqlite3")
    storage.mark_seen(
        "https://example.com|titulo",
        "titulo",
        "https://example.com",
        "Receita Federal",
        "2026-01-01T00:00:00+00:00",
    )
    assert storage.seen_identity("https://example.com|titulo")
    storage.close()
