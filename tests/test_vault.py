from doing2done.classify.models import NoteResult
from doing2done.vault import slugify, write_note


def test_slugify():
    assert slugify("Meeting Notes: Q3!") == "meeting-notes-q3"


def test_write_note(tmp_path):
    r = NoteResult(title="Hello World", date="2026-07-12", tags=["a", "b"], markdown="# Hi")
    p = write_note(r, str(tmp_path))
    assert p.endswith("2026-07-12-hello-world.md")
    txt = open(p).read()
    assert 'title: "Hello World"' in txt
    assert 'tags: ["a", "b"]' in txt
    assert "# Hi" in txt


def test_write_note_colon_title_is_valid_yaml(tmp_path):
    import yaml  # pyyaml not a dep; parse frontmatter manually if unavailable

    from doing2done.vault import render_frontmatter

    fm = render_frontmatter("Module 2: Translate language", "2026-07-13", ["x:y"])
    # frontmatter body between the --- fences must parse as YAML
    inner = fm.split("---")[1]
    data = yaml.safe_load(inner)
    assert data["title"] == "Module 2: Translate language"
    assert data["tags"] == ["x:y"]
