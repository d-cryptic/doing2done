"""Sharing publishes a note publicly — the content must not carry markup with it."""
from __future__ import annotations

from doing2done.share import DEFAULT_DAYS, TOKEN_BYTES, find_note, prepare, render


def test_raw_html_in_a_note_is_escaped_not_rendered():
    out = render("<script>alert('x')</script>\n\n<img src=x onerror=alert(1)>")
    assert "<script>" not in out
    assert "onerror=alert(1)>" not in out.replace("&gt;", ">") or "&lt;img" in out
    assert "&lt;script&gt;" in out


def test_markdown_still_renders():
    out = render("# Head\n\n**bold** and [a](https://example.com)")
    assert "<h1>" in out and "<strong>" in out and 'href="https://example.com"' in out


def test_tokens_are_unguessable_and_unique():
    import re
    from pathlib import Path

    class S:
        pass

    p = Path("/tmp/zz-tok.md")
    p.write_text('---\ntitle: "T"\n---\n\nbody\n')
    a = prepare(S(), p)["token"]
    b = prepare(S(), p)["token"]
    assert a != b
    assert len(a) >= 40 and re.fullmatch(r"[A-Za-z0-9_-]+", a)
    p.unlink()


def test_vault_only_links_and_assets_are_stripped(tmp_path):
    class S:
        pass

    p = tmp_path / "n.md"
    p.write_text(
        '---\ntitle: "T"\n---\n\n'
        "![d](./assets/n/diagram-1.png)\n\n"
        "See [Other](./other-abc123) too.\n\n"
        "## Related\n\n- [X](./x-1)\n"
    )
    html = prepare(S(), p)["html"]
    assert "assets/" not in html, "asset path would 404 or leak off-site"
    assert "other-abc123" not in html, "vault-relative link leaked"
    assert "Related" not in html
    assert "See Other too." in html, "link text should survive as plain text"
    # The image must vanish whole. Stripping only the link part leaves a stray "!d".
    assert "!d" not in html, "image markdown left a stray alt-text fragment"


def test_expiry_defaults_on_and_can_be_disabled(tmp_path):
    class S:
        pass

    p = tmp_path / "n.md"
    p.write_text('---\ntitle: "T"\n---\n\nbody\n')
    assert prepare(S(), p, days=DEFAULT_DAYS)["expires_at"] is not None
    assert prepare(S(), p, days=0)["expires_at"] is None


def test_find_note_by_stem_and_by_title(tmp_path):
    (tmp_path / "kubernetes-notes-abc123.md").write_text('---\ntitle: "K8s Concepts"\n---\n\nx\n')
    assert find_note(str(tmp_path), "kubernetes-notes-abc123").name.startswith("kubernetes")
    assert find_note(str(tmp_path), "k8s concepts") is not None
    assert find_note(str(tmp_path), "nothing here") is None


def test_token_bytes_is_not_weakened():
    assert TOKEN_BYTES >= 32
