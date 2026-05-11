from app.services.text import chunk_text, clean_text, html_to_text, normalize_for_hash


def test_html_to_text_removes_scripts_and_collapses_space():
    html = "<p>Hello <strong>world</strong></p><script>alert(1)</script><p>again</p>"
    assert html_to_text(html) == "Hello world again"


def test_chunk_text_overlaps_long_content():
    text = " ".join(f"word{i}" for i in range(200))
    chunks = chunk_text(text, max_chars=120, overlap_chars=20)
    assert len(chunks) > 1
    assert all(len(chunk) <= 130 for chunk in chunks)
    assert "word0" in chunks[0]


def test_chunk_text_splits_minified_unbroken_content_at_hard_limit():
    text = ".pfptBanner" + ("{display:block!important;background:#D0D8DC!important;}" * 120)

    chunks = chunk_text(text, max_chars=1200, overlap_chars=150)

    assert len(chunks) > 1
    assert all(len(chunk) <= 1200 for chunk in chunks)
    assert chunks[0] != chunks[1]


def test_normalize_for_hash_is_case_and_space_stable():
    assert normalize_for_hash("  Hello\nWORLD ") == "hello world"


def test_clean_text_removes_unpaired_surrogates():
    assert clean_text("ok\ud83d bad") == "ok bad"
