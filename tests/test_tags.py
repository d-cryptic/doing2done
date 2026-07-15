"""Tag canonicalisation must merge spellings without inventing synonyms."""
from __future__ import annotations

import pytest

from doing2done.vault import canonical_tag, canonical_tags


@pytest.mark.parametrize(
    ("raw", "want"),
    [
        ("open source", "open-source"),
        ("open_source", "open-source"),
        ("Open-Source", "open-source"),
        ("  Web Development  ", "web-development"),
        ("CI/CD", "ci/cd"),          # only whitespace/underscore collapse
        ("k8s", "k8s"),
        ("multi   space", "multi-space"),
        ("--edges--", "edges"),
    ],
)
def test_canonical_tag(raw, want):
    assert canonical_tag(raw) == want


def test_synonyms_are_left_alone():
    """Merging these is a judgement call — guessing rewrites the user's vocabulary."""
    assert canonical_tag("webdev") != canonical_tag("web development")
    assert canonical_tag("software dev") != canonical_tag("software development")


def test_dedupes_and_preserves_order():
    assert canonical_tags(["Open Source", "open_source", "k8s"]) == ["open-source", "k8s"]


def test_drops_empties():
    assert canonical_tags(["", "  ", "-", "real"]) == ["real"]


def test_empty_input():
    assert canonical_tags([]) == []
