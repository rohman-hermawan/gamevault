from app import allowed_file, human_size
from storage import _decode_text, _encode_text


def test_allowed_file():
    assert allowed_file("match.mp4")
    assert allowed_file("clip.WEBM")
    assert not allowed_file("script.exe")
    assert not allowed_file("tanpa_ekstensi")


def test_human_size():
    assert human_size(0) == "0 B"
    assert human_size(1024) == "1.00 KB"
    assert human_size(1024 * 1024) == "1.00 MB"


def test_metadata_roundtrip():
    value = "Highlight pertandingan terbaik"
    assert _decode_text(_encode_text(value)) == value
