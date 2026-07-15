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
            out.append(f'<li><a href="./notes/{_esc(stem)}">{_esc(title)}</a></li>')
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
            f'<div class="v-pair"><a href="./notes/{_esc(a["stem"])}">{_esc(a["title"])}</a>'
            f'<span class="v-vs">vs</span>'
            f'<a href="./notes/{_esc(b["stem"])}">{_esc(b["title"])}</a></div>'
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
    body = linkify_titles(_llm_markdown(prompt, settings), str(nd))
    dest = nd.parent / "insights.md"
    dest.write_text(
        '<div class="v-page">\n<p class="v-eyebrow">vault \u00b7 insights</p>\n'
        "<h1>Insights</h1>\n</div>\n\n" + body + "\n"
    )
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
            out.append(f'<li><a href="./notes/{_esc(stem)}">{_esc(title)}</a></li>')
        out.append("</ul></div>")
    out.append("</div></div>")
    dest = nd.parent / "timeline.md"
    dest.write_text("\n".join(out) + "\n")
    return str(dest)


def generate_graph(notes_dir: str) -> str:
    """A note graph you can walk -> docs/graph.md.

    Every node links to its note. Rendering a map you can't click is decoration:
    you can see that two notes are related but not go and read them.
    """
    from .relate import top_edges

    edges = top_edges(notes_dir)
    if not edges:
        dest = Path(notes_dir).parent / "graph.md"
        dest.write_text(
            '<div class="v-page"><p class="v-eyebrow">vault \u00b7 graph</p>'
            "<h1>Note graph</h1>"
            '<p class="v-empty">Not enough notes are related yet.</p></div>\n'
        )
        return str(dest)

    ids: dict[str, str] = {}
    stems: dict[str, str] = {}

    def nid(node: dict) -> str:
        key = node["title"]
        if key not in ids:
            ids[key] = f"n{len(ids)}"
            stems[ids[key]] = node["stem"]
        return ids[key]

    def label(s: str) -> str:
        """One line, always. Mermaid doesn't grow a node to fit a wrapped label, so
        anything long enough to wrap gets its second line sliced off."""
        s = s.replace('"', "'")
        return s if len(s) <= 30 else s[:29].rstrip() + "\u2026"

    lines = ["graph LR"]
    for a, b, _ in edges:
        lines.append(f'  {nid(a)}["{label(a["title"])}"] --- {nid(b)}["{label(b["title"])}"]')
    # click makes each node navigable; needs securityLevel loose (set in config.mts)
    for node_id, stem in stems.items():
        lines.append(f'  click {node_id} "./notes/{stem}"')

    body = "```mermaid\n" + "\n".join(lines) + "\n```"
    dest = Path(notes_dir).parent / "graph.md"
    dest.write_text(
        '<div class="v-page">\n'
        '<p class="v-eyebrow">vault \u00b7 graph</p>\n'
        "<h1>Note graph</h1>\n"
        f'<p class="v-note">{len(ids)} notes, {len(edges)} strongest links. '
        "Tap a node to open the note.</p>\n"
        "</div>\n\n"
        f"{body}\n"
    )
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
            f'<h2><a href="./notes/{_esc(lede["stem"])}">{_esc(lede["title"])}</a></h2>',
            f'<p class="v-drop">{_esc(lede["summary"])}</p>' if lede["summary"] else "",
            f'<p class="v-when">{lede["date"]}</p>',
            "</section>",
        ]

    # ── columns ──
    out.append('<div class="v-cols">')

    out.append('<section class="v-col"><p class="v-kicker">recently</p><ul class="v-idx">')
    for n in rest:
        out.append(
            f'<li><a href="./notes/{_esc(n["stem"])}"><b>{_esc(n["title"])}</b>'
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
        ("Weekly", "./notes/weekly/", "the week, reviewed"),
        ("Drafts", "./drafts/", "written from your notes"),
        ("Timeline", "./timeline", "by date, 2021 onward"),
        ("Tags", "./tags", "browse by topic"),
        ("Mentions", "./mentions", "names, projects, tools"),
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


def linkify_titles(markdown: str, notes_dir: str) -> str:
    """Turn note titles the LLM quoted into links to those notes.

    The report names real notes as evidence but writes prose, so every reference was
    a dead end — you could read that "Hackathon Tracker" matters and have no way to
    open it. Only exact title matches are linked; a near-miss stays plain text rather
    than sending you to the wrong note.
    """
    titles: dict[str, str] = {}
    for md in Path(notes_dir).glob("*.md"):
        if md.name == "index.md":
            continue
        fm = _frontmatter(md.read_text())
        title = (fm.get("title") or "").strip()
        if title:
            titles.setdefault(title.lower(), md.stem)
    if not titles:
        return markdown

    # Longest first is belt-and-braces: the closing quote in the pattern below already
    # forces the whole title to match, so "Hackathon" can't shadow "Hackathon
    # Brainstorm and Learning Plan" even unsorted. Kept because it costs nothing and
    # stops being true the moment the quote anchor is relaxed.
    pattern = "|".join(re.escape(t) for t in sorted(titles, key=len, reverse=True))

    def repl(m: re.Match) -> str:
        quote, title = m.group(1), m.group(2)
        stem = titles.get(title.lower())
        return f'{quote}[{title}](./notes/{stem}){quote}' if stem else m.group(0)

    # only inside the quotes the model already uses to cite a note
    return re.sub(rf'(["\u201c\u201d])({pattern})\1', repl, markdown, flags=re.I)


def generate_period_index(notes_dir: str, sub: str, label: str) -> str:
    """Latest brief inline, earlier ones listed -> docs/notes/<sub>/index.md.

    Both landing pages were stubs that described the feature and showed none of it,
    while the briefs hid in the sidebar. Tapping Daily should answer "what am I doing
    today"; tapping Weekly should show the review, not explain what a review is.
    """
    d = Path(notes_dir) / sub
    if not d.exists():
        return ""
    days = sorted((f for f in d.glob("*.md") if f.name != "index.md"), reverse=True)
    out = [
        '<div class="v-page">',
        f'<p class="v-eyebrow">vault \u00b7 {label.lower()}</p>',
        "</div>",
        "",
    ]
    if not days:
        out.append(f"# {label}\n")
        out.append(
            f'<p class="v-empty">No {label.lower()} brief yet \u2014 the scheduler '
            "writes one automatically.</p>"
        )
    else:
        latest = days[0]
        body = re.sub(r"^---\n.*?\n---\n", "", latest.read_text(), flags=re.S).strip()
        out.append(body)
        if len(days) > 1:
            out.append('\n<div class="v-page">\n<p class="v-kicker">earlier</p>')
            out.append('<ul class="v-list">')
            for f in days[1:15]:
                out.append(f'<li><a href="./{_esc(f.stem)}">{_esc(f.stem)}</a></li>')
            out.append("</ul>\n</div>")
    dest = d / "index.md"
    dest.write_text("\n".join(out) + "\n")
    return str(dest)


def generate_daily_index(notes_dir: str) -> str:
    """Today's brief, inline."""
    return generate_period_index(notes_dir, "daily", "Daily")


def generate_weekly_index(notes_dir: str) -> str:
    """The latest weekly review, inline.

    d2d weekly has been writing these all along and nothing linked to them — not the
    nav, sidebar, notes index or front page. It built into the site and was
    unreachable, and I then scheduled it to cost a model call every Sunday.
    """
    return generate_period_index(notes_dir, "weekly", "Weekly")


def generate_notes_index(notes_dir: str) -> str:
    """Every note, listed -> docs/notes/index.md.

    Was a hand-written stub describing itself ("every parsed note lands here") while
    listing nothing, so the only way to browse was the sidebar. It also advertised a
    "press /" shortcut that isn't bound.
    """
    nd = Path(notes_dir)
    rows = []
    for md in nd.glob("*.md"):
        if md.name == "index.md":
            continue
        raw = md.read_text()
        fm = _frontmatter(raw)
        rows.append({
            "title": fm.get("title", md.stem),
            "stem": md.stem,
            "date": (fm.get("date", "") or "").split("T")[0],
            "summary": _summary_of(raw),
            "drawn": "## Diagrams" in raw,
        })
    rows.sort(key=lambda r: (r["date"] or "0000", r["title"]), reverse=True)

    out = [
        '<div class="v-page">',
        '<p class="v-eyebrow">vault \u00b7 notes</p>',
        "<h1>Notes</h1>",
        f'<p class="v-note">{len(rows)} notes, newest first. '
        f'{sum(1 for r in rows if r["drawn"])} are handwritten \u2014 their pages carry '
        "the original scan and its transcription.</p>",
        '<ul class="v-idx v-idx-full">',
    ]
    for r in rows:
        pen = ' <em class="v-pen" title="handwritten">\u270e</em>' if r["drawn"] else ""
        summary = f'<span>{_esc(r["summary"])}</span>' if r["summary"] else ""
        out.append(
            f'<li><a href="./{_esc(r["stem"])}"><b>{_esc(r["title"])}{pen}</b>'
            f'{summary}<time>{r["date"]}</time></a></li>'
        )
    out.append("</ul></div>")
    dest = nd / "index.md"
    dest.write_text("\n".join(out) + "\n")
    return str(dest)


def generate_drafts_index(notes_dir: str) -> str:
    """Every draft, listed -> docs/drafts/index.md.

    d2d draft writes RAG-grounded drafts and publishes them, and nothing linked to
    them — the same way the weekly review was orphaned. A page you can only reach by
    already knowing its URL may as well not exist.
    """
    d = Path(notes_dir).parent / "drafts"
    if not d.exists():
        return ""
    files = sorted(f for f in d.glob("*.md") if f.name != "index.md")
    out = [
        '<div class="v-page">',
        '<p class="v-eyebrow">vault \u00b7 drafts</p>',
        "<h1>Drafts</h1>",
    ]
    if not files:
        out.append('<p class="v-empty">Nothing drafted yet \u2014 try '
                   "<code>d2d draft &quot;a topic&quot;</code>.</p></div>")
    else:
        out.append(
            f'<p class="v-note">{len(files)} draft(s), written from your own notes. '
            "Private, like the rest of the vault.</p>"
            '<ul class="v-idx v-idx-full">'
        )
        for f in files:
            kind, _, rest = f.stem.partition("-")
            title = rest.replace("-", " ") or f.stem
            out.append(
                f'<li><a href="./{_esc(f.stem)}"><b>{_esc(title)}</b>'
                f'<time>{_esc(kind)}</time></a></li>'
            )
        out.append("</ul></div>")
    dest = d / "index.md"
    dest.write_text("\n".join(out) + "\n")
    return str(dest)


def generate_mentions_page(notes_dir: str) -> str:
    """A cross-reference of recurring named entities -> docs/mentions.md.

    Tags are topical labels the classifier assigns; this is the complementary view —
    the specific orgs, projects, tech and certs you name, and every note each shows
    up in. Built locally from the note text, so it costs nothing to keep current.
    """
    from .entities import extract

    ents = extract(notes_dir)
    out = [
        '<div class="v-page">',
        '<p class="v-eyebrow">vault \u00b7 mentions</p>',
        "<h1>Mentions</h1>",
    ]
    if not ents:
        out.append('<p class="v-empty">No entity recurs across notes yet.</p></div>')
        dest = Path(notes_dir).parent / "mentions.md"
        dest.write_text("\n".join(out) + "\n")
        return str(dest)

    ordered = sorted(ents.items(), key=lambda kv: (-len(kv[1]), kv[0]))
    out.append(
        f'<p class="v-note">{len(ordered)} names, projects and tools that recur across '
        "your notes. Bigger chip = mentioned in more notes.</p>"
    )
    out.append('<div class="v-chips">')
    mx = max(len(v) for _, v in ordered)
    for ent, notes in ordered:
        n = len(notes)
        w = "lg" if n >= max(3, mx * 0.6) else ("md" if n > 2 else "sm")
        out.append(f'<a class="v-chip v-{w}" href="#{_slug(ent)}">{_esc(ent)}<i>{n}</i></a>')
    out.append("</div>")

    for ent, notes in ordered:
        out.append(f'<h2 id="{_slug(ent)}">{_esc(ent)} <i class="v-count">{len(notes)}</i></h2>')
        out.append('<ul class="v-list">')
        for title, stem in notes:
            out.append(f'<li><a href="./notes/{_esc(stem)}">{_esc(title)}</a></li>')
        out.append("</ul>")
    out.append("</div>")
    dest = Path(notes_dir).parent / "mentions.md"
    dest.write_text("\n".join(out) + "\n")
    return str(dest)
