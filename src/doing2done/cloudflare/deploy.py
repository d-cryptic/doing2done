"""Create the Pages project and gate it with an Access policy — via the CF API.

Needs CF_ADMIN_API_TOKEN with: Account:Cloudflare Pages:Edit and
Account:Access: Apps and Policies:Edit.
"""
from __future__ import annotations

import httpx

API = "https://api.cloudflare.com/client/v4"


class Cloudflare:
    def __init__(self, api_token: str, account_id: str) -> None:
        self.account_id = account_id
        self._http = httpx.Client(
            base_url=API,
            headers={"Authorization": f"Bearer {api_token}"},
            timeout=45,
            transport=httpx.HTTPTransport(retries=3),
        )

    def _post(self, path: str, body: dict) -> dict:
        r = self._http.post(path, json=body)
        r.raise_for_status()
        return r.json()["result"]

    def _get(self, path: str) -> dict | list:
        r = self._http.get(path)
        r.raise_for_status()
        return r.json()["result"]

    # ── Pages ──
    def ensure_pages_project(self, name: str, production_branch: str = "main") -> dict:
        try:
            return self._get(f"/accounts/{self.account_id}/pages/projects/{name}")  # type: ignore[return-value]
        except httpx.HTTPStatusError:
            return self._post(
                f"/accounts/{self.account_id}/pages/projects",
                {"name": name, "production_branch": production_branch},
            )

    # ── Access ──
    def ensure_access_app(self, name: str, domain: str) -> str:
        apps = self._get(f"/accounts/{self.account_id}/access/apps")
        for app in apps:  # type: ignore[union-attr]
            if app.get("domain") == domain:
                return app["id"]
        app = self._post(
            f"/accounts/{self.account_id}/access/apps",
            {
                "name": name,
                "domain": domain,
                "type": "self_hosted",
                "session_duration": "24h",
            },
        )
        return app["id"]

    def set_email_only_policy(self, app_id: str, email: str) -> dict:
        return self._post(
            f"/accounts/{self.account_id}/access/apps/{app_id}/policies",
            {
                "name": f"only {email}",
                "decision": "allow",
                "include": [{"email": {"email": email}}],
            },
        )

    def close(self) -> None:
        self._http.close()
