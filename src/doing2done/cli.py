"""doing2done command line — run `d2d --help`."""
from __future__ import annotations

import typer
from rich import print as rprint

from . import daily as daily_mod
from .cloudflare.deploy import Cloudflare
from .config import get_settings
from .pipeline import run_ingest
from .state import State
from .ticktick import oauth
from .ticktick.client import TickTickClient

app = typer.Typer(add_completion=False, help="Apple Notes -> smart TickTick + note vault.")


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
    tt = TickTickClient(tok["access_token"], State(s.state_db))
    for p in tt.projects():
        rprint(f"  [green]{p['id']}[/green]  {p['name']}")
    tt.close()


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
    from .reports import generate_tag_index

    generate_tag_index(s.vault_notes_dir)
    subprocess.run(["npm", "run", "docs:build"], cwd=s.vault_dir, check=True)
    env = {
        **os.environ,
        "CLOUDFLARE_API_TOKEN": s.cf_admin_api_token,
        "CLOUDFLARE_ACCOUNT_ID": s.cf_account_id,
    }
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
    tt = None
    if apply:
        tok = oauth.load_token(s.ticktick_token_path)
        if not tok:
            rprint("[red]No TickTick token — run `d2d auth` first.[/red]")
            raise typer.Exit(1)
        tt = TickTickClient(tok["access_token"], state)
    try:
        rep = run_ingest(
            s, state, tt, apply=apply, limit=limit or None, force=force, media_only=media_only
        )
    finally:
        if tt:
            tt.close()
    mode = "APPLIED" if apply else "DRY-RUN"
    rprint(
        f"[bold]{mode}[/bold] — processed={rep.processed} "
        f"todos={rep.todos_upserted} notes={rep.notes_written} skipped={rep.skipped}"
    )


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

    p = weekly_digest(get_settings())
    rprint(f"[green]weekly[/green] -> {p or 'no recent notes'}")


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
    tt = TickTickClient(tok["access_token"], State(s.state_db))
    try:
        title, md = daily_mod.build_brief(tt)
    finally:
        tt.close()
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
