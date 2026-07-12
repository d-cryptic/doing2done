"""doing2done command line — run `d2d --help`."""
from __future__ import annotations

import typer
from rich import print as rprint

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
    rep = run_ingest(s, state, tt, apply=apply)
    mode = "APPLIED" if apply else "DRY-RUN"
    rprint(
        f"[bold]{mode}[/bold] — processed={rep.processed} "
        f"todos={rep.todos_upserted} notes={rep.notes_written} skipped={rep.skipped}"
    )
    if tt:
        tt.close()


if __name__ == "__main__":
    app()
