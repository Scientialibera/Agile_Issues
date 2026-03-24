from __future__ import annotations

import hashlib
import logging
from typing import Any

import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

from app.config.config import AgileConfig

logger = logging.getLogger("agile_issues.jira")


class JiraClient:
    """Jira Cloud REST API client for reading, creating, and managing issues."""

    def __init__(self, config: AgileConfig) -> None:
        self.username = config.jira_id
        self.api_token = config.jira_key
        self.subdomain = self.username.split("@")[0] if self.username else ""
        self.base_url = f"https://{self.subdomain}.atlassian.net"
        self._auth = HTTPBasicAuth(self.username, self.api_token)

    def _get(self, path: str, **kwargs) -> requests.Response:
        return requests.get(f"{self.base_url}{path}", auth=self._auth, **kwargs)

    def _post(self, path: str, **kwargs) -> requests.Response:
        return requests.post(f"{self.base_url}{path}", auth=self._auth, **kwargs)

    def _delete(self, path: str) -> requests.Response:
        return requests.delete(f"{self.base_url}{path}", auth=self._auth)

    def get_issues(self, project_key: str, issue_type: str) -> list[dict]:
        jql = f"project={project_key} AND issuetype='{issue_type}'"
        resp = self._get(f"/rest/api/3/search?jql={jql}")
        if resp.status_code != 200:
            logger.warning("Failed to fetch %s issues: %s", issue_type, resp.text)
            return []

        results = []
        for issue in resp.json().get("issues", []):
            fields = issue["fields"]
            description_texts = _extract_text(fields.get("description"))
            parent_summary = None
            if issue_type != "Epic":
                parent_summary = (
                    fields.get("parent", {}).get("fields", {}).get("summary")
                )
            results.append({
                "name": fields["summary"],
                "type": issue_type,
                "parent": parent_summary,
                "description": " ".join(description_texts),
            })
        return results

    def get_all_issue_ids(self, project_key: str) -> list[str]:
        resp = self._get(f"/rest/api/3/search?jql=project={project_key}")
        if resp.status_code != 200:
            return []
        return [issue["id"] for issue in resp.json().get("issues", [])]

    def delete_issue(self, issue_id: str) -> bool:
        return self._delete(f"/rest/api/3/issue/{issue_id}").status_code == 204

    def delete_all_issues(self, project_key: str) -> int:
        ids = self.get_all_issue_ids(project_key)
        deleted = sum(1 for iid in ids if self.delete_issue(iid))
        logger.info("Deleted %d/%d issues in %s", deleted, len(ids), project_key)
        return deleted

    def create_issue(
        self,
        project_key: str,
        title: str,
        issue_type: str,
        description: str,
        parent_key: str | None = None,
    ) -> dict[str, Any]:
        payload: dict = {
            "fields": {
                "project": {"key": project_key},
                "summary": title,
                "issuetype": {"name": issue_type},
                "description": {
                    "type": "doc",
                    "version": 1,
                    "content": [{
                        "type": "paragraph",
                        "content": [{"text": description, "type": "text"}],
                    }],
                },
            }
        }
        if parent_key and issue_type.lower() != "epic":
            payload["fields"]["parent"] = {"key": parent_key}

        resp = self._post("/rest/api/3/issue", json=payload)
        return resp.json()

    def upload_dataframe(self, df: pd.DataFrame, project_key: str) -> list[str]:
        """Create Jira issues from a DataFrame with columns:
        title, description, type, parent, skills, roles.
        """
        created_keys: list[str] = []
        parent_mapping: dict[str, str] = {}

        for _, row in df.iterrows():
            title = row["title"]
            issue_type = row["type"]
            skills = row.get("skills", "")
            roles = row.get("roles", "")
            description = (
                f"Description:\n{row['description']}\n"
                f"Skills Required:\n{skills}\n"
                f"Roles:\n{roles}"
            )

            parent_key = None
            parent_name = row.get("parent")
            if parent_name and issue_type.lower() != "epic":
                parent_key = parent_mapping.get(str(parent_name))
                if not parent_key:
                    logger.warning("Parent key not found for '%s'", title)
                    continue

            result = self.create_issue(project_key, title, issue_type, description, parent_key)
            key = result.get("key")
            if key:
                created_keys.append(key)
                if issue_type.lower() in ("epic", "story"):
                    parent_mapping[title] = key
            else:
                logger.warning("Failed to create issue '%s': %s", title, result)

        return created_keys


def _extract_text(content: Any) -> list[str]:
    """Recursively extract text values from Jira ADF content."""
    texts: list[str] = []
    if isinstance(content, dict):
        for key, value in content.items():
            if key == "text":
                texts.append(value)
            elif isinstance(value, (list, dict)):
                texts.extend(_extract_text(value))
    elif isinstance(content, list):
        for item in content:
            texts.extend(_extract_text(item))
    return texts
