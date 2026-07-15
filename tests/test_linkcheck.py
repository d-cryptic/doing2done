"""VitePress ignores raw-HTML links; the dashboards are made of them."""
from __future__ import annotations

from doing2done.linkcheck import broken_links


def _vault(tmp_path):
    docs = tmp_path / "docs"
    (docs / "notes").mkdir(parents=True)
    (docs / "notes" / "real-note-abc123.md").write_text("---\ntitle: \"R\"\n---\n\nx\n")
    (docs / "notes" / "index.md").write_text("index\n")
    return docs


def test_catches_a_dead_raw_html_link(tmp_path):
    """The exact failure mode: a retitle renames the file, anchors still point at the old stem."""
    docs = _vault(tmp_path)
    (docs / "duplicates.md").write_text('<a href="./notes/gone-xyz789">Gone</a>')
    bad = broken_links(str(docs))
    assert bad == [("duplicates.md", "./notes/gone-xyz789")]


def test_passes_a_live_raw_html_link(tmp_path):
    docs = _vault(tmp_path)
    (docs / "duplicates.md").write_text('<a href="./notes/real-note-abc123">R</a>')
    assert broken_links(str(docs)) == []


def test_catches_dead_markdown_links_too(tmp_path):
    docs = _vault(tmp_path)
    (docs / "insights.md").write_text("see [X](./notes/nope-000000)")
    assert len(broken_links(str(docs))) == 1


def test_assets_are_not_pages(tmp_path):
    docs = _vault(tmp_path)
    (docs / "notes" / "n.md").write_text("![d](./assets/n/diagram-1.png)")
    assert broken_links(str(docs)) == []


def test_index_resolves_without_its_filename(tmp_path):
    """/notes/ must satisfy a link to ./notes/ — cleanUrls serves the index."""
    docs = _vault(tmp_path)
    (docs / "index.md").write_text('<a href="./notes/">All</a>')
    assert broken_links(str(docs)) == []


def test_missing_dir_is_a_noop(tmp_path):
    assert broken_links(str(tmp_path / "nope")) == []
