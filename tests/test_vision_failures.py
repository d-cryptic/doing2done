"""A handwritten note's content lives in its image. A failed read must not be
recorded as 'this note is empty' — that loses the page permanently.
"""
from __future__ import annotations

from unittest.mock import patch

from doing2done.notes.media import NoteMedia
from doing2done.pipeline import _describe_diagrams


def _media(tmp_path, n=1):
    paths = []
    for i in range(n):
        p = tmp_path / f"d{i}.png"
        p.write_bytes(b"\x89PNG\r\n\x1a\n" + bytes([i]) * 40)  # distinct bytes -> distinct hash
        paths.append(str(p))
    return [NoteMedia(identifier="m", uti="png", png_paths=tuple(paths), is_drawing=True)]


class _S:
    llm_api_key = "k"
    llm_model = "m"
    llm_base_url = "http://x"


def test_exception_counts_as_a_failure(tmp_path):
    with patch("doing2done.classify.vision.describe_page", side_effect=RuntimeError("429")):
        descs, failures = _describe_diagrams(_media(tmp_path), _S())
    assert failures == 1
    # The image is still kept (you don't lose the scan) — but it carries no text,
    # which is exactly why the caller must not treat this note as readable.
    assert all(not d["transcription"] for d in descs)


def test_empty_response_counts_as_a_failure(tmp_path):
    """The bug that lost a page: a call that 'succeeds' with nothing looks blank."""
    with patch("doing2done.classify.vision.describe_page", return_value={}):
        descs, failures = _describe_diagrams(_media(tmp_path), _S())
    assert failures == 1, "an empty read must not pass as a legitimately blank page"


def test_successful_read_has_no_failures(tmp_path):
    good = {"kind": "handwriting", "caption": "notes", "transcription": "Azure migration"}
    with patch("doing2done.classify.vision.describe_page", return_value=good):
        descs, failures = _describe_diagrams(_media(tmp_path), _S())
    assert failures == 0
    assert descs[0]["transcription"] == "Azure migration"


def test_partial_failure_is_counted(tmp_path):
    good = {"kind": "h", "caption": "c", "transcription": "real text"}
    with patch(
        "doing2done.classify.vision.describe_page",
        side_effect=[good, RuntimeError("boom")],
    ):
        descs, failures = _describe_diagrams(_media(tmp_path, n=2), _S())
    assert failures == 1
    assert [d["transcription"] for d in descs] == ["real text", ""]


def test_caption_only_is_not_a_failure(tmp_path):
    """A doodle with no words still yields a caption — that's a real read."""
    with patch("doing2done.classify.vision.describe_page",
               return_value={"kind": "sketch", "caption": "a flow diagram", "transcription": ""}):
        _descs, failures = _describe_diagrams(_media(tmp_path), _S())
    assert failures == 0
