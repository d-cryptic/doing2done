"""doing2done command line — run `d2d --help`."""
from __future__ import annotations

from pathlib import Path

import httpx
import typer
from rich import print as rprint

from . import daily as daily_mod
from .cloudflare.deploy import Cloudflare
from .config import get_settings
from .pipeline import run_ingest
from .providers import build_provider
from .state import State
from .ticktick import oauth
from .todo import TodoService

app = typer.Typer(add_completion=False, help="Apple Notes -> smart TickTick + note vault.")


def _svc(s, state) -> TodoService | None:
    """Build the configured todo provider (TickTick/Reminders/Markdown) as a service."""
    prov = build_provider(s, state)
    return TodoService(prov, state, s.ticktick_default_project_id) if prov else None


@app.command()
def init() -> None:
    """Bootstrap a fresh clone: scaffold the vault, .env, and worker config."""
    from .init import init_project

    for step in init_project(get_settings()):
        rprint(f"[green]•[/green] {step}")
    rprint("\n[bold]Next (manual):[/bold]")
    rprint("  1. Fill .env — TickTick, OpenRouter, Cloudflare token + account id, your email")
    rprint("  2. Provision Cloudflare (once):")
    rprint("       cd worker && wrangler d1 create doing2done \\")
    rprint("         && wrangler r2 bucket create doing2done-assets \\")
    rprint("         && wrangler vectorize create doing2done-notes \\")
    rprint("              --dimensions=768 --metric=cosine")
    rprint("     then set database_id in worker/wrangler.toml, and: wrangler deploy")
    rprint("  3. Grant Full Disk Access to /bin/bash (System Settings → Privacy)")
    rprint("  4. uv run d2d auth → d2d cf-check → d2d ingest --apply → d2d deploy-site")


@app.command()
def auth() -> None:
    """One-time TickTick OAuth. Saves the token locally."""
    s = get_settings()
    if not s.ticktick_client_id or not s.ticktick_client_secret:
        rprint("[red]Set TICKTICK_CLIENT_ID / TICKTICK_CLIENT_SECRET in .env first.[/red]")
        raise typer.Exit(1)
    oauth.authorize(
        s.ticktick_client_id, s.ticktick_client_secret,
        s.ticktick_redirect_uri, s.ticktick_token_path,
    )


@app.command("ticktick-check")
def ticktick_check() -> None:
    """Verify the TickTick token by listing your projects."""
    s = get_settings()
    tok = oauth.load_token(s.ticktick_token_path)
    if not tok:
        rprint("[red]No token — run `d2d auth` first.[/red]")
        raise typer.Exit(1)
    svc = _svc(s, State(s.state_db))
    if svc is None:
        rprint("[red]No provider configured / no token.[/red]")
        raise typer.Exit(1)
    for pr in svc.p.list_projects():
        rprint(f"  [green]{pr.id}[/green]  {pr.name}")
    svc.close()


@app.command("cf-check")
def cf_check() -> None:
    """Verify CF_ADMIN_API_TOKEN can reach the account (Pages/Access scopes)."""
    s = get_settings()
    if not s.cf_admin_api_token:
        rprint("[red]CF_ADMIN_API_TOKEN not set in .env.[/red]")
        raise typer.Exit(1)
    cf = Cloudflare(s.cf_admin_api_token, s.cf_account_id)
    try:
        proj = cf.ensure_pages_project(s.cf_pages_project)
        rprint(f"[green]Pages OK[/green] — project '{proj.get('name', s.cf_pages_project)}'")
    finally:
        cf.close()


@app.command("telegram-setup")
def telegram_setup(
    token: str = typer.Argument(..., help="Bot token from @BotFather."),
) -> None:
    """Wire a Telegram bot: set the Worker secret + register the webhook."""
    import os
    import subprocess

    import httpx

    s = get_settings()
    if not s.worker_url or not s.ingest_token:
        rprint("[red]Set WORKER_URL + INGEST_TOKEN in .env first.[/red]")
        raise typer.Exit(1)
    # store the bot token as a Worker secret (via wrangler OAuth)
    env = {k: v for k, v in os.environ.items() if k != "CLOUDFLARE_API_TOKEN"}
    p = subprocess.run(
        ["wrangler", "secret", "put", "TELEGRAM_BOT_TOKEN"], cwd="worker", env=env,
        input=token + "\n", capture_output=True, text=True,
    )
    if "Success" not in p.stdout:
        rprint(f"[red]secret failed:[/red] {(p.stderr or p.stdout)[-120:]}")
        raise typer.Exit(1)
    # register the webhook
    hook = f"{s.worker_url}/telegram/{s.ingest_token}"
    api = f"https://api.telegram.org/bot{token}/setWebhook"
    r = httpx.get(api, params={"url": hook}, timeout=20)
    ok = r.json().get("ok")
    rprint("[green]telegram ready[/green]" if ok else f"[red]webhook failed:[/red] {r.text[:120]}")
    if ok:
        rprint("  Message your bot: a thought -> todos, or 'ask <question>' -> search.")


@app.command()
def shortcuts() -> None:
    """Print ready-to-paste capture/ask config (URLs + token) for Apple Shortcuts."""
    s = get_settings()
    if not s.worker_url or not s.ingest_token:
        rprint("[red]Set WORKER_URL + INGEST_TOKEN in .env first.[/red]")
        raise typer.Exit(1)
    rprint("[bold]Capture[/bold] (share-sheet / Siri)")
    rprint(f"  POST {s.worker_url}/capture")
    rprint(f"  Header  Authorization: Bearer {s.ingest_token}")
    rprint('  Body    {"source":"shortcut","text":[Shortcut Input]}')
    rprint("\n[bold]Ask my notes[/bold]")
    rprint(f"  GET  {s.worker_url}/ask?q=[Provided Input]")
    rprint(f"  Header  Authorization: Bearer {s.ingest_token}")
    rprint("\n[bold]WhatsApp webhook[/bold] (Twilio sandbox)")
    rprint(f"  {s.worker_url}/whatsapp/{s.ingest_token}")
    rprint(f"\n[bold]Web ask page[/bold]\n  {s.worker_url}/app")


@app.command("wire-email")
def wire_email(
    address: str = typer.Argument(..., help="e.g. capture@your-domain.com"),
) -> None:
    """Route an email address to the Worker via Cloudflare Email Routing (API)."""
    s = get_settings()
    domain = address.split("@", 1)[1]
    cf = Cloudflare(s.cf_admin_api_token, s.cf_account_id)
    try:
        zone = cf.zone_id(domain)
        if not zone:
            rprint(f"[red]No Cloudflare zone for {domain}.[/red]")
            raise typer.Exit(1)
        try:
            cf.enable_email_routing(zone)
            cf.route_to_worker(
                zone, address, s.cf_pages_project.replace("-vault", "") or "doing2done"
            )
            rprint(f"[green]email routed[/green] {address} -> Worker")
        except httpx.HTTPStatusError as e:
            if e.response.status_code == 403:
                rprint("[yellow]403[/yellow] — token needs 'Zone > Email Routing Rules > Edit'.")
                rprint("  Add that scope to CF_ADMIN_API_TOKEN and re-run,")
                rprint("  or configure it in the Cloudflare dashboard.")
            else:
                raise
    finally:
        cf.close()


@app.command("gate-site")
def gate_site(domain: str = typer.Option(..., help="e.g. doing2done-vault.pages.dev")) -> None:
    """Create/ensure an Access app for DOMAIN allowing only your email."""
    s = get_settings()
    cf = Cloudflare(s.cf_admin_api_token, s.cf_account_id)
    try:
        app_id = cf.ensure_access_app(f"doing2done vault ({domain})", domain)
        cf.set_email_only_policy(app_id, s.cf_access_allowed_email)
        rprint(f"[green]Access gated[/green] {domain} -> only {s.cf_access_allowed_email}")
    finally:
        cf.close()


@app.command("deploy-site")
def deploy_site() -> None:
    """Build the VitePress vault and deploy it to Cloudflare Pages."""
    import os
    import subprocess

    s = get_settings()
    from .relate import relate_vault
    from .reports import generate_tag_index

    relate_vault(s.vault_notes_dir)
    generate_tag_index(s.vault_notes_dir)
    from .reports import generate_duplicates_page

    generate_duplicates_page(s.vault_notes_dir)
    from .reports import generate_graph, generate_timeline

    generate_timeline(s.vault_notes_dir)
    generate_graph(s.vault_notes_dir)
    subprocess.run(["npm", "run", "docs:build"], cwd=s.vault_dir, check=True)
    env = {**os.environ, "CLOUDFLARE_API_TOKEN": s.cf_admin_api_token}
    if s.cf_account_id:
        env["CLOUDFLARE_ACCOUNT_ID"] = s.cf_account_id
    subprocess.run(
        [
            "wrangler", "pages", "deploy", "docs/.vitepress/dist",
            "--project-name", s.cf_pages_project,
            "--branch", "main", "--commit-dirty=true",
        ],
        cwd=s.vault_dir, env=env, check=True,
    )
    rprint(f"[green]Deployed[/green] -> https://{s.cf_pages_project}.pages.dev")


@app.command()
def ingest(
    apply: bool = typer.Option(False, help="Write todos + notes (default: dry-run)."),
    limit: int = typer.Option(0, help="Only process the first N changed notes (0 = all)."),
    force: bool = typer.Option(False, help="Reprocess even if unchanged (ignore watermark)."),
    media_only: bool = typer.Option(False, "--media-only", help="Only notes with diagrams."),
) -> None:
    """Run the ingest pipeline. Dry-run by default; pass --apply to commit changes."""
    s = get_settings()
    state = State(s.state_db)
    svc = None
    if apply:
        svc = _svc(s, state)
        if svc is None:
            rprint("[red]No TickTick token — run `d2d auth` first.[/red]")
            raise typer.Exit(1)
    try:
        rep = run_ingest(
            s, state, svc, apply=apply, limit=limit or None, force=force, media_only=media_only
        )
    finally:
        if svc:
            svc.close()
    if apply:
        from .health import mark_sync

        mark_sync(state)
    mode = "APPLIED" if apply else "DRY-RUN"
    rprint(
        f"[bold]{mode}[/bold] — processed={rep.processed} "
        f"todos={rep.todos_upserted} notes={rep.notes_written} skipped={rep.skipped}"
    )


@app.command()
def ask(question: str = typer.Argument(..., help="Your question about your notes.")) -> None:
    """Ask a question answered from your vault (RAG)."""
    from .ask import ask as ask_notes

    s = get_settings()
    r = ask_notes(question, s.vault_notes_dir, s)
    rprint(f"\n{r['answer']}\n")
    if r.get("sources"):
        rprint("[dim]sources: " + ", ".join(r["sources"]) + "[/dim]")


@app.command("enrich-links")
def enrich_links_cmd(limit: int = typer.Option(0, help="Max notes to enrich (0=all).")) -> None:
    """Fetch + summarize URLs found in notes."""
    from .enrich import enrich_links

    s = get_settings()
    n = enrich_links(s.vault_notes_dir, s, limit=limit or None)
    rprint(f"[green]enriched[/green] -> {n} notes")


@app.command("calendar")
def calendar_cmd(
    apply: bool = typer.Option(False, help="Write events (default: dry-run)."),
) -> None:
    """Mirror due-dated todos onto your Apple Calendar (no Google OAuth)."""
    from .calendar import sync as cal_sync

    s = get_settings()
    state = State(s.state_db)
    svc = _svc(s, state)
    if svc is None:
        rprint("[red]No todo provider configured.[/red]")
        raise typer.Exit(1)
    try:
        rep = cal_sync(s, state, svc, apply=apply)
    finally:
        svc.close()
    mode = "APPLIED" if apply else "DRY-RUN"
    rprint(
        f"[bold]{mode}[/bold] calendar '{s.calendar_name}' — "
        f"created={rep['created']} updated={rep['updated']} unchanged={rep['unchanged']}"
    )


@app.command()
def cost(days: int = typer.Option(30, help="Window in days.")) -> None:
    """What this actually costs: tokens + estimated spend by model."""
    from .usage import summarize

    s = summarize(days)
    if not s["calls"]:
        rprint("[yellow]no usage recorded yet[/yellow] (accounting starts from now)")
        return
    rprint(f"[bold]last {s['days']}d — {s['calls']} LLM calls[/bold]\n")
    for model, a in sorted(s["models"].items(), key=lambda x: -x[1]["cost"]):
        rprint(
            f"  {model:38} {a['calls']:4} calls  "
            f"{a['in']:>8,} in / {a['out']:>7,} out   ${a['cost']:.4f}"
        )
    monthly = s["total_cost"] * 30 / max(s["days"], 1)
    rprint(f"\n[bold]estimated total: ${s['total_cost']:.4f}[/bold]  (~${monthly:.2f}/mo)")


@app.command()
def backup() -> None:
    """Snapshot the state DB to R2 (dedup map — losing it duplicates every todo)."""
    from .backup import backup as do_backup

    keys = do_backup(get_settings())
    rprint(f"[green]backed up[/green] -> {', '.join(keys)}")


@app.command()
def restore(
    key: str = typer.Option("", help="R2 key (default: latest, encrypted if configured)."),
) -> None:
    """Restore the state DB from an R2 snapshot (overwrites local state)."""
    from .backup import restore as do_restore

    path = do_restore(get_settings(), key)
    rprint(f"[green]restored[/green] {key} -> {path}")


@app.command()
def health() -> None:
    """Canary: verify Notes access, provider, worker, and sync recency. Alerts on failure."""
    from .health import check
    from .notify import notify

    s = get_settings()
    problems = check(s, State(s.state_db))
    if problems:
        msg = "health check FAILED: " + "; ".join(problems)
        notify(msg)
        rprint(f"[red]{msg}[/red]")
        raise typer.Exit(1)
    rprint("[green]healthy[/green] — notes readable, provider ok, worker ok, sync recent")


@app.command("eval")
def eval_cmd(
    model: str = typer.Option("", help="Override the model for this run."),
    compare: str = typer.Option("", help="Comma-separated models to A/B on your cases."),
) -> None:
    """Run the extraction eval harness over golden cases (guards quality regressions)."""
    from .eval import run_evals

    s = get_settings()
    if compare:
        rprint("[bold]model comparison on your golden cases[/bold]\n")
        table: list[tuple[str, int, int, list[str]]] = []
        for m in [x.strip() for x in compare.split(",") if x.strip()]:
            try:
                res = run_evals(s, model=m)
            except Exception as e:
                rprint(f"[red]{m}: error[/red] {str(e)[:70]}")
                continue
            ok = sum(1 for r in res if r.ok)
            fails = [r.name for r in res if not r.ok]
            table.append((m, ok, len(res), fails))
            mark = "[green]" if ok == len(res) else "[yellow]"
            detail = f"  failed: {', '.join(fails)}" if fails else ""
            rprint(f"{mark}{ok}/{len(res)}[/] {m}{detail}")
        if table:
            best = max(table, key=lambda r: r[1])
            rprint(f"\n[bold]best on your data:[/bold] {best[0]} ({best[1]}/{best[2]})")
        return

    results = run_evals(s, model=model or None)
    passed = sum(1 for r in results if r.ok)
    for r in results:
        mark = "[green]PASS[/green]" if r.ok else "[red]FAIL[/red]"
        rprint(f"{mark}  {r.name}")
        if not r.ok:
            if r.missing:
                rprint(f"       missing: {', '.join(r.missing)}")
            if r.leaked:
                rprint(f"       [red]hallucinated[/red]: {', '.join(r.leaked)}")
            for n in r.notes:
                rprint(f"       {n}")
            rprint(f"       got: {r.got}")
    rprint(f"\n[bold]{passed}/{len(results)} passed[/bold]")
    if passed != len(results):
        raise typer.Exit(1)


@app.command()
def draft(
    topic: str = typer.Argument(..., help="What to write about (grounded in your notes)."),
    kind: str = typer.Option("blog", help="tweet | blog | note"),
) -> None:
    """Draft a tweet/blog from your own notes (RAG-grounded)."""
    from .draft import make_draft

    s = get_settings()
    body, path = make_draft(topic, kind, s.vault_notes_dir, s)
    if not path:
        rprint("[yellow]no relevant notes found[/yellow]")
        raise typer.Exit(1)
    rprint(f"[green]draft[/green] -> {path}\n")
    rprint(body[:600])


@app.command()
def insights() -> None:
    """Generate an LLM insight report over all notes."""
    from .reports import generate_insights

    p = generate_insights(get_settings())
    rprint(f"[green]insights[/green] -> {p or 'no notes'}")


@app.command()
def push(
    force: bool = typer.Option(False, help="Re-push every note (rebuild embeddings)."),
) -> None:
    """Push changed Apple Notes to the Cloudflare edge (D1 + Vectorize)."""
    from hashlib import sha1

    from .notes import store

    s = get_settings()
    if not s.worker_url or not s.ingest_token:
        rprint("[red]Set WORKER_URL + INGEST_TOKEN in .env.[/red]")
        raise typer.Exit(1)
    state = State(s.state_db)

    pending: list[tuple[dict, str]] = []
    for n in store.list_notes():
        body = n.body_html[:8000]
        digest = sha1(f"{n.name}|{n.modified}|{body}".encode()).hexdigest()
        if not force and state.get_pushed_hash(n.id) == digest:
            continue  # unchanged since last push — skip re-embedding
        pending.append(
            ({"note_id": n.id, "title": n.name, "body": body, "modified": n.modified}, digest)
        )

    if not pending:
        rprint("[green]push[/green] -> up to date (0 changed)")
        return

    embedded = 0
    for i in range(0, len(pending), 20):  # batch for Workers AI subrequest limits
        chunk = pending[i : i + 20]
        r = httpx.post(
            f"{s.worker_url}/ingest", json=[p for p, _ in chunk],
            headers={"Authorization": f"Bearer {s.ingest_token}"}, timeout=120,
        )
        r.raise_for_status()
        embedded += r.json().get("embedded", 0)
        for payload, digest in chunk:  # only record after a successful push
            state.set_pushed_hash(payload["note_id"], digest)
    rprint(f"[green]pushed[/green] -> {len(pending)} changed, {embedded} embedded")


@app.command()
def analytics() -> None:
    """Generate the completion + open-task analytics page."""
    from .reports import generate_analytics

    s = get_settings()
    state = State(s.state_db)
    svc = _svc(s, state)
    try:
        p = generate_analytics(s, state, svc)
    finally:
        if svc:
            svc.close()
    rprint(f"[green]analytics[/green] -> {p}")


@app.command()
def timeline() -> None:
    """Generate the timeline (notes by date) page."""
    from .reports import generate_timeline

    rprint(f"[green]timeline[/green] -> {generate_timeline(get_settings().vault_notes_dir)}")


@app.command()
def graph() -> None:
    """Generate the Mermaid note graph page."""
    from .reports import generate_graph

    rprint(f"[green]graph[/green] -> {generate_graph(get_settings().vault_notes_dir)}")


@app.command()
def librarian(
    apply: bool = typer.Option(False, help="Repair metadata (default: dry-run report)."),
    limit: int = typer.Option(0, help="Max notes to touch (0 = all)."),
) -> None:
    """Garden the vault: re-derive weak titles/tags/TL;DR from each note's own body."""
    from .librarian import garden

    rows = garden(get_settings(), apply=apply, limit=limit or None)
    if not rows:
        rprint("[green]vault is tidy[/green] — no weak metadata found")
        return
    for r in rows:
        mark = "[green]fixed[/green]" if r.get("fixed") else "[yellow]weak[/yellow]"
        err = f" ({r['error']})" if r.get("error") else ""
        rprint(f"  {mark}  {r['file']}  missing: {', '.join(r['weak'])}{err}")
    action = "repaired" if apply else "found (dry-run — pass --apply to fix)"
    rprint(f"\n[bold]{len(rows)} note(s) {action}[/bold]")


@app.command()
def dedup() -> None:
    """Regenerate the near-duplicate notes report."""
    from .reports import generate_duplicates_page

    p = generate_duplicates_page(get_settings().vault_notes_dir)
    rprint(f"[green]duplicates[/green] -> {p}")


@app.command()
def capture() -> None:
    """Pull queued Telegram messages into todos + notes."""
    from . import capture as cap

    s = get_settings()
    state = State(s.state_db)
    svc = _svc(s, state)
    try:
        n = cap.process_captures(s, state, svc)
    finally:
        if svc:
            svc.close()
    rprint(f"[green]capture[/green] -> {n} message(s) handled")


@app.command()
def relate() -> None:
    """Compute related-notes/backlinks (TF-IDF + shared tags) and inject into the vault."""
    from .relate import relate_vault

    n = relate_vault(get_settings().vault_notes_dir)
    rprint(f"[green]related[/green] -> {n} notes linked")


@app.command()
def tags() -> None:
    """Regenerate the vault tag index page."""
    from .reports import generate_tag_index

    p = generate_tag_index(get_settings().vault_notes_dir)
    rprint(f"[green]tag index[/green] -> {p}")


@app.command()
def weekly() -> None:
    """Generate a weekly review digest into the vault."""
    from .reports import weekly_digest

    s = get_settings()
    p = weekly_digest(s, state=State(s.state_db))
    rprint(f"[green]weekly[/green] -> {p or 'no recent notes'}")


@app.command()
def share(
    query: str = typer.Argument(..., help="Note stem, or part of its title."),
    days: int = typer.Option(30, help="Link lifetime in days (0 = no expiry)."),
) -> None:
    """Publish ONE note behind an unguessable, revocable link."""
    from .share import find_note, prepare

    s = get_settings()
    path = find_note(s.vault_notes_dir, query)
    if not path:
        rprint(f"[red]no note matching[/red] {query!r}")
        raise typer.Exit(1)
    payload = prepare(s, path, days=days)
    r = httpx.post(
        f"{s.worker_url}/share",
        json=payload,
        headers={"Authorization": f"Bearer {s.ingest_token}"},
        timeout=30,
    )
    if r.status_code != 200:
        rprint(f"[red]share failed[/red] {r.status_code} {r.text[:120]}")
        raise typer.Exit(1)
    out = r.json()
    rprint(f"[green]shared[/green] {payload['title']}")
    rprint(f"  {out['url']}")
    rprint(f"  expires: {out['expires_at'] or 'never'}")
    rprint(f"  revoke:  d2d unshare {payload['token'][:12]}")


@app.command()
def shares() -> None:
    """List every share link and its state."""
    s = get_settings()
    r = httpx.get(
        f"{s.worker_url}/shares",
        headers={"Authorization": f"Bearer {s.ingest_token}"},
        timeout=30,
    )
    rows = r.json().get("shares", [])
    if not rows:
        rprint("[yellow]nothing shared[/yellow]")
        return
    for row in rows:
        if row["revoked"]:
            state, colour = "revoked", "red"
        elif row["expires_at"]:
            state, colour = f"expires {row['expires_at'][:10]}", "green"
        else:
            state, colour = "no expiry", "green"
        rprint(
            f"[{colour}]{row['token'][:12]}[/{colour}]  {row['title'][:40]:42s} "
            f"{state:22s} {row['views']} views"
        )


@app.command()
def unshare(
    token: str = typer.Argument("", help="Token (or its prefix). Omit with --all."),
    all: bool = typer.Option(False, "--all", help="Revoke every live link."),
) -> None:
    """Revoke a share link immediately."""
    s = get_settings()
    H = {"Authorization": f"Bearer {s.ingest_token}"}
    if not all and not token:
        rprint("[red]give a token or --all[/red]")
        raise typer.Exit(1)
    full = token
    if token and len(token) < 43:  # accept the prefix d2d shares prints
        listing = httpx.get(f"{s.worker_url}/shares", headers=H, timeout=30).json()
        rows = listing.get("shares", [])
        hits = [r["token"] for r in rows if r["token"].startswith(token.rstrip("…."))]
        if len(hits) != 1:
            rprint(f"[red]{'no' if not hits else 'ambiguous'} token[/red] {token!r}")
            raise typer.Exit(1)
        full = hits[0]
    r = httpx.post(
        f"{s.worker_url}/unshare", json={"token": full, "all": all}, headers=H, timeout=30
    )
    rprint(f"[green]revoked {r.json().get('revoked', 0)} link(s)[/green]")


@app.command()
def prune(
    apply: bool = typer.Option(False, help="Actually archive (default: dry run)."),
) -> None:
    """Archive vault files orphaned by a re-titled note.

    Archives rather than deletes: an orphan is inferred from state, and state can be
    wrong (a note id whose file no longer matches its content). <vault>/archive/ keeps
    them out of the published site while staying recoverable.
    """
    from .vault import archive_note, find_orphans

    s = get_settings()
    state = State(s.state_db)
    rows = state.all_seen_notes()
    live = {r["md_path"] for r in rows if r["md_path"]}
    orphans = find_orphans(s.vault_notes_dir, live, [r["note_id"] for r in rows])
    if not orphans:
        rprint("[green]no orphans[/green]")
        return
    for o in orphans:
        rprint(f"  {'archived' if apply else 'would archive'} {Path(o).name}")
        if apply:
            archive_note(o, s.vault_dir, s.vault_notes_dir)
    rprint(
        f"[green]{len(orphans)} orphan(s)[/green]"
        + ("" if apply else " — re-run with --apply to move them to <vault>/archive/")
    )


@app.command()
def digest(
    days: int = typer.Option(7, help="Look-back window."),
    send: bool = typer.Option(False, help="Push it to Telegram instead of printing."),
) -> None:
    """Weekly review: what you captured, closed, and keep deferring."""
    from .digest import compose_digest
    from .notify import send_telegram

    s = get_settings()
    text = compose_digest(s, State(s.state_db), days=days)
    if not text:
        rprint("[yellow]nothing to report[/yellow]")
        return
    if not send:
        rprint(text)
        return
    rprint("[green]digest sent[/green]" if send_telegram(text)
           else "[red]send failed — set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID[/red]")


@app.command()
def surface(
    send: bool = typer.Option(False, help="Push it to Telegram instead of printing."),
) -> None:
    """Nudge: open todos going stale and notes gone dormant."""
    from .digest import compose_surface
    from .notify import send_telegram

    s = get_settings()
    text = compose_surface(s, State(s.state_db))
    if not text:
        rprint("[green]nothing going stale[/green]")
        return
    if not send:
        rprint(text)
        return
    rprint("[green]surfaced[/green]" if send_telegram(text)
           else "[red]send failed — set TELEGRAM_BOT_TOKEN + TELEGRAM_CHAT_ID[/red]")


@app.command()
def daily(
    target: str = typer.Option("both", help="Where to write: notes | vault | both."),
    folder: str = typer.Option("Daily", help="Apple Notes folder for the daily note."),
) -> None:
    """Build a daily brief (rolled-over overdue + today's tasks) and write it out."""
    s = get_settings()
    tok = oauth.load_token(s.ticktick_token_path)
    if not tok:
        rprint("[red]No TickTick token — run `d2d auth`.[/red]")
        raise typer.Exit(1)
    state = State(s.state_db)
    svc = _svc(s, state)
    if svc is None:
        rprint("[red]No todo provider configured — run `d2d auth` (TickTick).[/red]")
        raise typer.Exit(1)
    try:
        title, md = daily_mod.build_brief(svc, state=state, settings=s)
    finally:
        svc.close()
    if target in ("vault", "both"):
        from pathlib import Path
        d = Path(s.vault_notes_dir) / "daily"
        d.mkdir(parents=True, exist_ok=True)
        (d / f"{title.split(' — ')[-1]}.md").write_text(
            f"---\ntitle: {title!r}\n---\n\n" + md + "\n"
        )
        rprint("[green]vault[/green] daily written")
    if target in ("notes", "both"):
        try:
            res = daily_mod.write_to_apple_notes(title, md, folder)
            rprint(f"[green]apple notes[/green] {res}")
        except Exception as e:
            rprint(
                f"[yellow]apple notes skipped[/yellow] ({str(e)[:60]}) "
                "— needs Automation permission"
            )
    rprint(f"[bold]{title}[/bold]")


if __name__ == "__main__":
    app()
