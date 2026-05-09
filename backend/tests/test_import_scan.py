from pathlib import Path

from app.config import Settings
from app.services.import_runner import safe_relative_import_path, scan_import_dir


def test_scan_import_dir_finds_uppercase_pst(tmp_path: Path):
    (tmp_path / "Archive.PST").write_bytes(b"pst")
    (tmp_path / "notes.txt").write_text("ignore me", encoding="utf-8")

    files = scan_import_dir(Settings(import_dir=tmp_path))

    assert [item["filename"] for item in files] == ["Archive.PST"]
    assert files[0]["relative_path"] == "Archive.PST"


def test_safe_relative_import_path_accepts_uppercase_pst(tmp_path: Path):
    pst = tmp_path / "Archive.PST"
    pst.write_bytes(b"pst")

    resolved = safe_relative_import_path(Settings(import_dir=tmp_path), "Archive.PST")

    assert resolved == pst.resolve()

