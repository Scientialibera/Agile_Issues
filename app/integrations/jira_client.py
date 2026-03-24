from __future__ import annotations

import logging
from typing import Any

import pandas as pd
import requests
from requests.auth import HTTPBasicAuth

from app.config.config import AgileConfig

logger = logging.getLogger("agile_issues.jira")

_MAX_SEARCH_PAGE = 100
_BULK_CREATE_LIMIT = 50


class JiraApiError(Exception):
    """Raised when the Jira REST API returns a non-success status."""

    def __init__(self, status_code: int, body: Any) -> None:
        self.status_code = status_code
        self.body = body
        super().__init__(f"Jira API {status_code}: {body}")


class JiraClient:
    """Jira Cloud REST API v3 client.

    Reference: https://developer.atlassian.com/cloud/jira/platform/rest/v3/
    """

    def __init__(self, config: AgileConfig) -> None:
        self.base_url = f"https://{config.jira_domain}.atlassian.net"
        self._auth = HTTPBasicAuth(config.jira_email, config.jira_api_token)
        self._headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> requests.Response:
        return requests.get(
            f"{self.base_url}{path}",
            auth=self._auth,
            headers=self._headers,
            params=params,
        )

    def _post(self, path: str, json: Any = None) -> requests.Response:
        return requests.post(
            f"{self.base_url}{path}",
            auth=self._auth,
            headers=self._headers,
            json=json,
        )

    def _put(self, path: str, json: Any = None) -> requests.Response:
        return requests.put(
            f"{self.base_url}{path}",
            auth=self._auth,
            headers=self._headers,
            json=json,
        )

    def _delete(self, path: str, params: dict | None = None) -> requests.Response:
        return requests.delete(
            f"{self.base_url}{path}",
            auth=self._auth,
            headers=self._headers,
            params=params,
        )

    @staticmethod
    def _check(resp: requests.Response) -> None:
        if resp.status_code >= 400:
            try:
                body = resp.json()
            except Exception:
                body = resp.text
            raise JiraApiError(resp.status_code, body)

    # ── Search (paginated) ───────────────────────────────────────────────

    def search(
        self,
        jql: str,
        fields: list[str] | None = None,
        max_results: int | None = None,
    ) -> list[dict]:
        """Execute a JQL search with automatic pagination.

        GET /rest/api/3/search  (startAt / maxResults)
        """
        collected: list[dict] = []
        start_at = 0
        page_size = min(max_results or _MAX_SEARCH_PAGE, _MAX_SEARCH_PAGE)

        while True:
            params: dict[str, Any] = {
                "jql": jql,
                "startAt": start_at,
                "maxResults": page_size,
            }
            if fields:
                params["fields"] = ",".join(fields)

            resp = self._get("/rest/api/3/search", params=params)
            self._check(resp)
            data = resp.json()

            issues = data.get("issues", [])
            collected.extend(issues)

            total = data.get("total", 0)
            start_at += len(issues)

            if start_at >= total or not issues:
                break
            if max_results and len(collected) >= max_results:
                break

        return collected[:max_results] if max_results else collected

    def get_project_issues(
        self, project_key: str, issue_type: str | None = None,
    ) -> list[dict]:
        """Fetch all issues for a project, optionally filtered by type."""
        jql = f"project={project_key}"
        if issue_type:
            jql += f" AND issuetype='{issue_type}'"
        jql += " ORDER BY created ASC"

        raw_issues = self.search(jql, fields=["summary", "description", "parent", "issuetype", "status", "labels"])
        results = []
        for issue in raw_issues:
            fields = issue["fields"]
            parent_summary = (
                fields.get("parent", {}).get("fields", {}).get("summary")
                if fields.get("parent")
                else None
            )
            results.append({
                "key": issue["key"],
                "title": fields["summary"],
                "type": fields["issuetype"]["name"],
                "status": fields.get("status", {}).get("name"),
                "parent": parent_summary,
                "labels": fields.get("labels", []),
                "description": " ".join(_extract_adf_text(fields.get("description"))),
            })
        return results

    # ── Get single issue ─────────────────────────────────────────────────

    def get_issue(self, issue_id_or_key: str) -> dict:
        """GET /rest/api/3/issue/{issueIdOrKey}"""
        resp = self._get(f"/rest/api/3/issue/{issue_id_or_key}")
        self._check(resp)
        return resp.json()

    # ── Create issue ─────────────────────────────────────────────────────

    def create_issue(
        self,
        project_key: str,
        summary: str,
        issue_type: str,
        description_adf: dict | None = None,
        parent_key: str | None = None,
        labels: list[str] | None = None,
    ) -> dict:
        """POST /rest/api/3/issue

        Returns {"id", "key", "self"} on success.
        """
        fields: dict[str, Any] = {
            "project": {"key": project_key},
            "summary": summary,
            "issuetype": {"name": issue_type},
        }
        if description_adf:
            fields["description"] = description_adf
        if parent_key and issue_type.lower() != "epic":
            fields["parent"] = {"key": parent_key}
        if labels:
            fields["labels"] = labels

        resp = self._post("/rest/api/3/issue", json={"fields": fields})
        self._check(resp)
        return resp.json()

    # ── Bulk create (up to 50 per call) ──────────────────────────────────

    def bulk_create_issues(self, issue_payloads: list[dict]) -> dict:
        """POST /rest/api/3/issue/bulk

        Accepts up to 50 issue payloads per call.
        Returns {"issues": [...], "errors": [...]}.
        """
        results: dict = {"issues": [], "errors": []}

        for i in range(0, len(issue_payloads), _BULK_CREATE_LIMIT):
            batch = issue_payloads[i : i + _BULK_CREATE_LIMIT]
            resp = self._post("/rest/api/3/issue/bulk", json={"issueUpdates": batch})
            self._check(resp)
            data = resp.json()
            results["issues"].extend(data.get("issues", []))
            results["errors"].extend(data.get("errors", []))

        return results

    # ── Edit issue ───────────────────────────────────────────────────────

    def edit_issue(
        self,
        issue_id_or_key: str,
        fields: dict | None = None,
        update: dict | None = None,
    ) -> None:
        """PUT /rest/api/3/issue/{issueIdOrKey}"""
        body: dict[str, Any] = {}
        if fields:
            body["fields"] = fields
        if update:
            body["update"] = update
        resp = self._put(f"/rest/api/3/issue/{issue_id_or_key}", json=body)
        self._check(resp)

    # ── Delete issue ─────────────────────────────────────────────────────

    def delete_issue(self, issue_id_or_key: str, delete_subtasks: bool = False) -> None:
        """DELETE /rest/api/3/issue/{issueIdOrKey}"""
        params = {"deleteSubtasks": "true"} if delete_subtasks else {}
        resp = self._delete(f"/rest/api/3/issue/{issue_id_or_key}", params=params)
        self._check(resp)

    def delete_all_issues(self, project_key: str) -> int:
        issues = self.search(f"project={project_key}", fields=["summary"])
        deleted = 0
        for issue in issues:
            try:
                self.delete_issue(issue["key"], delete_subtasks=True)
                deleted += 1
            except JiraApiError as exc:
                logger.warning("Failed to delete %s: %s", issue["key"], exc)
        logger.info("Deleted %d/%d issues in %s", deleted, len(issues), project_key)
        return deleted

    # ── Transitions ──────────────────────────────────────────────────────

    def get_transitions(self, issue_id_or_key: str) -> list[dict]:
        """GET /rest/api/3/issue/{issueIdOrKey}/transitions"""
        resp = self._get(f"/rest/api/3/issue/{issue_id_or_key}/transitions")
        self._check(resp)
        return resp.json().get("transitions", [])

    def transition_issue(self, issue_id_or_key: str, transition_id: str) -> None:
        """POST /rest/api/3/issue/{issueIdOrKey}/transitions"""
        resp = self._post(
            f"/rest/api/3/issue/{issue_id_or_key}/transitions",
            json={"transition": {"id": transition_id}},
        )
        self._check(resp)

    # ── Upload pipeline output ───────────────────────────────────────────

    def upload_dataframe(self, df: pd.DataFrame, project_key: str) -> list[str]:
        """Create Jira issues from a pipeline DataFrame.

        Columns: title, description, type, parent, skills, roles.
        Creates Epics first, then Stories, then Subtasks so parent keys
        are available when children are created.
        """
        created_keys: list[str] = []
        parent_mapping: dict[str, str] = {}

        type_order = {"Epic": 0, "Story": 1, "Subtask": 2}
        sorted_df = df.copy()
        sorted_df["_order"] = sorted_df["type"].map(type_order).fillna(3)
        sorted_df = sorted_df.sort_values("_order").drop(columns=["_order"])

        for _, row in sorted_df.iterrows():
            title = row["title"]
            issue_type = row["type"]
            skills = row.get("skills", [])
            roles = row.get("roles", [])

            description_adf = _build_adf_description(
                row["description"], skills, roles,
            )

            labels = _build_labels(skills, roles)

            parent_key = None
            parent_name = row.get("parent")
            if pd.notna(parent_name) and parent_name and issue_type.lower() != "epic":
                parent_key = parent_mapping.get(str(parent_name))
                if not parent_key:
                    logger.warning("Parent key not found for '%s' (parent='%s')", title, parent_name)

            try:
                result = self.create_issue(
                    project_key, title, issue_type, description_adf, parent_key, labels,
                )
                key = result["key"]
                created_keys.append(key)
                parent_mapping[title] = key
                logger.info("Created %s '%s' → %s", issue_type, title, key)
            except JiraApiError as exc:
                logger.error("Failed to create '%s': %s", title, exc)

        return created_keys


# ── ADF (Atlassian Document Format) helpers ──────────────────────────────

def _build_adf_description(
    description: str,
    skills: Any = None,
    roles: Any = None,
) -> dict:
    """Build a rich ADF document with structured sections."""
    content: list[dict] = []

    if description:
        content.append(_adf_heading("Description"))
        for para in description.split("\n\n"):
            stripped = para.strip()
            if stripped:
                content.append(_adf_paragraph(stripped))

    if skills:
        skill_list = skills if isinstance(skills, list) else [str(skills)]
        if skill_list:
            content.append(_adf_heading("Skills Required"))
            content.append(_adf_bullet_list(skill_list))

    if roles:
        role_list = roles if isinstance(roles, list) else [str(roles)]
        if role_list:
            content.append(_adf_heading("Roles"))
            content.append(_adf_bullet_list(role_list))

    if not content:
        content.append(_adf_paragraph("No description provided."))

    return {"type": "doc", "version": 1, "content": content}


def _adf_paragraph(text: str) -> dict:
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": text}],
    }


def _adf_heading(text: str, level: int = 3) -> dict:
    return {
        "type": "heading",
        "attrs": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def _adf_bullet_list(items: list[str]) -> dict:
    return {
        "type": "bulletList",
        "content": [
            {
                "type": "listItem",
                "content": [_adf_paragraph(item)],
            }
            for item in items
        ],
    }


def _build_labels(skills: Any, roles: Any) -> list[str]:
    """Derive Jira labels from skills/roles for easy filtering."""
    labels: list[str] = []
    if isinstance(skills, list):
        for s in skills[:5]:
            label = str(s).strip().replace(" ", "-").lower()[:255]
            if label:
                labels.append(label)
    if isinstance(roles, list):
        for r in roles[:5]:
            label = str(r).strip().replace(" ", "-").lower()[:255]
            if label:
                labels.append(f"role:{label}")
    return labels


def _extract_adf_text(content: Any) -> list[str]:
    """Recursively extract plain text from Jira ADF content."""
    texts: list[str] = []
    if isinstance(content, dict):
        for key, value in content.items():
            if key == "text":
                texts.append(value)
            elif isinstance(value, (list, dict)):
                texts.extend(_extract_adf_text(value))
    elif isinstance(content, list):
        for item in content:
            texts.extend(_extract_adf_text(item))
    return texts
