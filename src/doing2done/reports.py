"""Vault reports: tag index page + weekly digest."""
from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

from .config import Settings


def _llm_markdown(prompt: str, settings: Settings) -> str:
    """Call the LLM for a {markdown} JSON payload; retry once, fall back to raw."""
    import json

    from .classify.classifier import _gemini, _openai

    for _ in range(2):
        if settings.llm_provider == "gemini":
            raw = _gemini(prompt, settings.llm_api_key, settings.llm_model)
        else:
            raw = _openai(prompt, settings.llm_api_key, settings.llm_model, settings.llm_base_url)
        try:
            return json.loads(raw).get("markdown", "")
        except json.JSONDecodeError:
            last = raw
    return last  # best-effort raw text


def _frontmatter(md: str) -> dict:
    m = re.match(r"^---\n(.*?)\n---", md, re.S)
    if not m:
        return {}
    fm: dict = {}
    for line in m.group(1).splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        v = v.strip()
        if v.startswith("[") and v.endswith("]"):
            items = [x.strip().strip('"').strip("'") for x in v[1:-1].split(",")]
            fm[k.strip()] = [x for x in items if x]
        else:
            fm[k.strip()] = v.strip('"').strip("'")
    return fm


def generate_tag_index(notes_dir: str) -> str:
    """Write docs/tags.md: a jump grid over every tag, then the notes per tag."""
    nd = Path(notes_dir)
    by_tag: dict[str, list[tuple[str, str]]] = {}
    for md in nd.glob("*.md"):
        if md.name == "index.md":
            continue
        fm = _frontmatter(md.read_text())
        for tag in fm.get("tags", []) or []:
            by_tag.setdefault(tag, []).append((fm.get("title", md.stem), md.stem))

    ordered = sorted(by_tag, key=lambda k: (-len(by_tag[k]), k))
    out = [
        '<div class="v-page">',
        '<p class="v-eyebrow">vault \u00b7 tags</p>',
        "<h1>Tags</h1>",
        f'<p class="v-note">{len(by_tag)} tags across '
        f'{len({s for v in by_tag.values() for _, s in v})} notes. '
        "Bigger chip = more notes.</p>",
        '<div class="v-chips">',
    ]
    # Chips are sized by count, so the shape of your thinking is visible at a glance.
    mx = max((len(v) for v in by_tag.values()), default=1)
    for tag in ordered:
        n = len(by_tag[tag])
        weight = "lg" if n >= max(3, mx * 0.6) else ("md" if n > 1 else "sm")
        out.append(
            f'<a class="v-chip v-{weight}" href="#{_slug(tag)}">'
            f"{_esc(tag)}<i>{n}</i></a>"
        )
    out.append("</div>")

    for tag in ordered:
        out.append(
            f'<h2 id="{_slug(tag)}">{_esc(tag)} '
            f'<i class="v-count">{len(by_tag[tag])}</i></h2>'
        )
        out.append('<ul class="v-list">')
        for title, stem in sorted(by_tag[tag]):
            out.append(f'<li><a href="./notes/{stem}">{_esc(title)}</a></li>')
        out.append("</ul>")
    out.append("</div>")
    dest = nd.parent / "tags.md"
    dest.write_text("\n".join(out) + "\n")
    return str(dest)


def _slug(s: str) -> str:
    import re as _re

    return _re.sub(r"[^a-z0-9]+", "-", str(s).lower()).strip("-") or "tag"


def _kill_list(state) -> str:
    """A weekly mirror: what you keep deferring."""
    if state is None:
        return ""
    chronic = state.chronic_tasks(4)
    if not chronic:
        return ""
    lines = ["\n## 🪓 Kill list — rolled over repeatedly\n",
             "\nBe honest: break these down or delete them.\n"]
    lines += [f"- **{n}×** — {title}" for title, n in chronic]
    return "\n".join(lines) + "\n"


def weekly_digest(settings: Settings, days: int = 7, state=None) -> str:
    """Summarize the last N days of notes into a vault digest via the LLM."""

    nd = Path(settings.vault_notes_dir)
    cutoff = dt.date.today() - dt.timedelta(days=days)
    recent = []
    for md in nd.glob("*.md"):
        if md.name == "index.md":
            continue
        fm = _frontmatter(md.read_text())
        d = fm.get("date", "")
        try:
            if d and dt.date.fromisoformat(d.split("T")[0]) >= cutoff:
                recent.append((fm.get("title", md.stem), fm.get("summary", "")))
        except ValueError:
            continue
    if not recent:
        return ""
    listing = "\n".join(f"- {t}: {s}" for t, s in recent)
    prompt = (
        "Write a concise weekly review (markdown) from these note summaries. "
        "Group into themes, surface what's in progress and what needs attention. "
        f"Return JSON {{\"markdown\": string}}.\n\n{listing}"
    )

    body = _llm_markdown(prompt, settings)
    wk = nd / "weekly"
    wk.mkdir(parents=True, exist_ok=True)
    today = dt.date.today().isoformat()
    dest = wk / f"{today}.md"
    header = f'---\ntitle: "Weekly — {today}"\n---\n\n# Weekly review — {today}\n\n'
    dest.write_text(header + body + "\n" + _kill_list(state))
    return str(dest)


def generate_duplicates_page(notes_dir: str) -> str:
    """Near-duplicate pairs, side by side and clickable -> docs/duplicates.md."""
    from .relate import find_duplicates

    pairs = find_duplicates(notes_dir)
    out = [
        '<div class="v-page">',
        '<p class="v-eyebrow">vault \u00b7 duplicates</p>',
        "<h1>Possible duplicates</h1>",
    ]
    if not pairs:
        out.append('<p class="v-empty">Nothing looks duplicated. \U0001f389</p></div>')
        dest = Path(notes_dir).parent / "duplicates.md"
        dest.write_text("\n".join(out) + "\n")
        return str(dest)

    out.append(
        f'<p class="v-note">{len(pairs)} pairs above 0.72 similarity. '
        "Open both, keep the better one.</p>"
    )
    for a, b, sim in pairs:
        pct = round(sim * 100)
        out.append('<div class="v-dup">')
        out.append(
            f'<div class="v-score"><b>{pct}%</b>'
            f'<span class="v-meter"><span style="width:{pct}%"></span></span></div>'
        )
        out.append(
            f'<div class="v-pair"><a href="./notes/{a["stem"]}">{_esc(a["title"])}</a>'
            f'<span class="v-vs">vs</span>'
            f'<a href="./notes/{b["stem"]}">{_esc(b["title"])}</a></div>'
        )
        out.append("</div>")
    out.append("</div>")
    dest = Path(notes_dir).parent / "duplicates.md"
    dest.write_text("\n".join(out) + "\n")
    return str(dest)


def generate_insights(settings: Settings) -> str:
    """LLM insight report over all notes: recurring themes, stale ideas, patterns."""

    nd = Path(settings.vault_notes_dir)
    items = []
    for md in nd.glob("*.md"):
        if md.name == "index.md":
            continue
        fm = _frontmatter(md.read_text())
        tags = ', '.join(fm.get('tags', []) or [])
        items.append(f"- {fm.get('title', md.stem)} [{tags}]: {fm.get('summary', '')}")
    if not items:
        return ""
    prompt = (
        "From these note titles/tags/summaries, produce a markdown insight report: "
        "recurring themes, what's in progress, stale ideas worth revisiting, and any patterns. "
        'Return JSON {"markdown": string}.\n\n' + "\n".join(items[:200])
    )
    body = _llm_markdown(prompt, settings)
    dest = nd.parent / "insights.md"
    dest.write_text(f"# Insights\n\n{body}\n")
    return str(dest)


def _esc(s: str) -> str:
    return (
        str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def _chart(rows: list[tuple[str, int]], *, unit: str = "", accent: str = "amber") -> str:
    """A CSS bar chart: bars are spans with a width %, so it prints and needs no JS."""
    if not rows:
        return '<p class="v-empty">nothing yet</p>'
    mx = max(n for _, n in rows) or 1
    out = ['<div class="v-chart v-' + accent + '">']
    for label, n in rows:
        pct = max(2, round(n / mx * 100))
        out.append(
            f'<div class="v-row"><span class="v-label">{_esc(label)}</span>'
            f'<span class="v-track"><span class="v-bar" style="width:{pct}%"></span></span>'
            f'<span class="v-val">{n}{unit}</span></div>'
        )
    out.append("</div>")
    return "".join(out)


def generate_analytics(settings: Settings, state, svc) -> str:
    """What is actually true about your workload -> docs/analytics.md.

    Deliberately omits a completion trend: task_map only marks a todo complete when
    reconciliation drops it from a note, so that series measures the pipeline's bulk
    writes (hundreds per minute), not work you finished. Every number here is one the
    schema can stand behind.
    """
    nd = Path(settings.vault_notes_dir)
    out = [
        '<div class="v-page">',
        '<p class="v-eyebrow">vault \u00b7 analytics</p>',
        "<h1>Analytics</h1>",
    ]

    open_rows: list[tuple[str, int]] = []
    if svc is not None:
        counts: dict[str, int] = {}
        for _task, pname in svc.open_with_project():
            counts[pname] = counts.get(pname, 0) + 1
        open_rows = sorted(counts.items(), key=lambda x: -x[1])
    total_open = sum(n for _, n in open_rows)

    by_day: dict[str, int] = {}
    for md in nd.glob("*.md"):
        if md.name == "index.md":
            continue
        d = (_frontmatter(md.read_text()).get("date", "") or "").split("T")[0]
        if d:
            by_day[d] = by_day.get(d, 0) + 1
    recent_notes = sorted(by_day.items())[-14:]

    created = state.created_by_day(14) if state is not None else []
    chronic = state.chronic_tasks(4) if state is not None else []

    out.append('<div class="v-stats">')
    for label, val in (
        ("open todos", total_open),
        ("notes", sum(by_day.values())),
        ("lists in play", len(open_rows)),
        ("chronic rollovers", len(chronic)),
    ):
        out.append(f'<div class="v-stat"><b>{val}</b><span>{label}</span></div>')
    out.append("</div>")

    out.append("<h2>Open todos by list</h2>")
    out.append(_chart(open_rows))

    out.append("<h2>Notes by date</h2>")
    out.append(
        '<p class="v-note">The note\'s own date \u2014 the date it names, or when '
        "Apple Notes last modified it. Not when it was captured, so old notes show "
        "old dates. Most recent 14 active days.</p>"
    )
    out.append(_chart(recent_notes, accent="sage"))

    out.append("<h2>Todos created</h2>")
    out.append('<p class="v-note">When a todo first appeared.</p>')
    out.append(_chart(created, accent="sage"))

    if chronic:
        out.append("<h2>Kill list</h2>")
        out.append(
            '<p class="v-note">Rolled over four times or more. '
            "Break them down or drop them.</p>"
        )
        out.append(_chart(list(chronic[:10]), unit="\u00d7", accent="rose"))

    out.append("</div>")
    dest = nd.parent / "analytics.md"
    dest.write_text("\n".join(out) + "\n")
    return str(dest)


def generate_timeline(notes_dir: str) -> str:
    """Notes down a dated rail -> docs/timeline.md."""
    nd = Path(notes_dir)
    by_date: dict[str, list[tuple[str, str]]] = {}
    for md in nd.glob("*.md"):
        if md.name == "index.md":
            continue
        fm = _frontmatter(md.read_text())
        d = (fm.get("date", "") or "undated").split("T")[0]
        by_date.setdefault(d, []).append((fm.get("title", md.stem), md.stem))

    dated = sorted((d for d in by_date if d != "undated"), reverse=True)
    out = [
        '<div class="v-page">',
        '<p class="v-eyebrow">vault \u00b7 timeline</p>',
        "<h1>Timeline</h1>",
        f'<p class="v-note">{sum(len(v) for v in by_date.values())} notes'
        + (f", {dated[-1]} \u2192 {dated[0]}" if dated else "")
        + ".</p>",
        '<div class="v-rail">',
    ]
    for d in dated + (["undated"] if "undated" in by_date else []):
        out.append('<div class="v-tick">')
        out.append(f'<div class="v-when">{_esc(d)}<i>{len(by_date[d])}</i></div>')
        out.append('<ul class="v-list">')
        for title, stem in sorted(by_date[d]):
            out.append(f'<li><a href="./notes/{stem}">{_esc(title)}</a></li>')
        out.append("</ul></div>")
    out.append("</div></div>")
    dest = nd.parent / "timeline.md"
    dest.write_text("\n".join(out) + "\n")
    return str(dest)


def generate_graph(notes_dir: str) -> str:
    """Mermaid backlink graph -> docs/graph.md."""
    from .relate import top_edges

    edges = top_edges(notes_dir)
    ids: dict[str, str] = {}

    def nid(title: str) -> str:
        if title not in ids:
            ids[title] = f"n{len(ids)}"
        return ids[title]

    lines = ["graph LR"]
    for a, b, _ in edges:
        safe_a = a.replace('"', "'")[:40]
        safe_b = b.replace('"', "'")[:40]
        lines.append(f'  {nid(a)}["{safe_a}"] --- {nid(b)}["{safe_b}"]')
    body = "```mermaid\n" + "\n".join(lines) + "\n```" if edges else "*not enough notes yet*"
    dest = Path(notes_dir).parent / "graph.md"
    dest.write_text(f"# Note graph\n\nHow your notes connect (strongest links).\n\n{body}\n")
    return str(dest)


def generate_home(settings: Settings, state=None, svc=None) -> str:
    """The vault's front page: real content, not a menu of links.

    Built from the vault itself so it can never advertise something that isn't
    there — every number and headline below is read off the notes at build time.
    """
    import datetime as _dt

    nd = Path(settings.vault_notes_dir)
    notes: list[dict] = []
    tag_counts: dict[str, int] = {}
    diagrams = 0
    for md in nd.glob("*.md"):
        if md.name == "index.md":
            continue
        raw = md.read_text()
        fm = _frontmatter(raw)
        d = (fm.get("date", "") or "").split("T")[0]
        notes.append({
            "title": fm.get("title", md.stem),
            "stem": md.stem,
            "date": d,
            "summary": _summary_of(raw),
            "tags": fm.get("tags", []) or [],
        })
        for tg in fm.get("tags", []) or []:
            tag_counts[tg] = tag_counts.get(tg, 0) + 1
        if "## Diagrams" in raw:
            diagrams += 1

    dated = sorted((n for n in notes if n["date"]), key=lambda n: n["date"], reverse=True)
    lede, rest = (dated[0], dated[1:9]) if dated else (None, [])
    span = f"{dated[-1]['date']} \u2192 {dated[0]['date']}" if dated else ""

    open_n = 0
    if state is not None:
        with state._conn() as c:
            open_n = c.execute(
                "SELECT COUNT(*) n FROM task_map WHERE completed = 0"
            ).fetchone()["n"]
    chronic = state.chronic_tasks(4) if state is not None else []

    out = [
        "---",
        "layout: page",
        "aside: false",
        "sidebar: false",
        "---",
        '<div class="v-front">',
        # ── masthead ──
        '<header class="v-mast">',
        '<div class="v-mast-rule"></div>',
        "<h1>the vault</h1>",
        '<p class="v-mast-sub">everything you ever scribbled \u2014 '
        "parsed, transcribed, searchable</p>",
        '<div class="v-mast-meta">',
        f"<span>{len(notes)} notes</span><span>{span}</span>"
        f"<span>{diagrams} handwritten</span><span>{len(tag_counts)} tags</span>"
        f"<span>{open_n} open todos</span>",
        "</div>",
        '<div class="v-mast-rule"></div>',
        "</header>",
    ]

    # ── the lede: your most recent thinking, not a nav card ──
    if lede:
        out += [
            '<section class="v-lede">',
            '<p class="v-kicker">latest</p>',
            f'<h2><a href="./notes/{lede["stem"]}">{_esc(lede["title"])}</a></h2>',
            f'<p class="v-drop">{_esc(lede["summary"])}</p>' if lede["summary"] else "",
            f'<p class="v-when">{lede["date"]}</p>',
            "</section>",
        ]

    # ── columns ──
    out.append('<div class="v-cols">')

    out.append('<section class="v-col"><p class="v-kicker">recently</p><ul class="v-idx">')
    for n in rest:
        out.append(
            f'<li><a href="./notes/{n["stem"]}"><b>{_esc(n["title"])}</b>'
            f'<time>{n["date"]}</time></a></li>'
        )
    out.append("</ul></section>")

    out.append('<section class="v-col"><p class="v-kicker">threads</p><div class="v-chips">')
    for tg, n in sorted(tag_counts.items(), key=lambda x: (-x[1], x[0]))[:22]:
        out.append(f'<a class="v-chip v-md" href="./tags#{_slug(tg)}">{_esc(tg)}<i>{n}</i></a>')
    out.append("</div>")
    if chronic:
        out.append('<p class="v-kicker v-kicker-2">be honest</p><ul class="v-kill">')
        for title, n in chronic[:5]:
            out.append(f"<li><span>{n}\u00d7</span>{_esc(title)}</li>")
        out.append("</ul>")
    out.append("</section>")
    out.append("</div>")

    # ── the rest of the vault, as a ruled index rather than cards ──
    out.append('<section class="v-more"><p class="v-kicker">also</p><div class="v-more-grid">')
    for label, href, blurb in (
        ("All notes", "./notes/", "every parsed note, full-text"),
        ("Daily", "./notes/daily/", "rolled-over tasks + today"),
        ("Timeline", "./timeline", "by date, 2021 onward"),
        ("Tags", "./tags", "browse by topic"),
        ("Graph", "./graph", "how notes connect"),
        ("Insights", "./insights", "recurring themes"),
        ("Analytics", "./analytics", "where the work sits"),
        ("Duplicates", "./duplicates", "near-copies to merge"),
    ):
        out.append(f'<a href="{href}"><b>{label}</b><span>{blurb}</span></a>')
    out.append("</div></section>")

    now = _dt.date.today().isoformat()
    out.append(f'<footer class="v-foot">built {now} \u00b7 private \u00b7 doing2done</footer>')
    out.append("</div>")
    dest = nd.parent / "index.md"
    dest.write_text("\n".join(x for x in out if x) + "\n")
    return str(dest)


def _summary_of(raw: str) -> str:
    m = re.search(r"^> \*\*TL;DR\*\*\s*(.+)$", raw, re.M)
    return m.group(1).strip() if m else ""
