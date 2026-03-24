from __future__ import annotations

import logging

import pandas as pd
from azure.devops.connection import Connection
from azure.devops.v7_0.work_item_tracking.models import JsonPatchOperation
from msrest.authentication import BasicAuthentication

from app.config.config import AgileConfig

logger = logging.getLogger("agile_issues.devops")


class DevOpsClient:
    """Azure DevOps Work Item Tracking client."""

    def __init__(self, config: AgileConfig) -> None:
        self.organization = config.devops_organization
        self.project = config.devops_project
        credentials = BasicAuthentication("", config.devops_pat)
        self.connection = Connection(
            base_url=f"https://dev.azure.com/{self.organization}",
            creds=credentials,
        )

    def _wit_client(self):
        return self.connection.clients.get_work_item_tracking_client()

    def create_work_item(self, work_item_type: str, title: str, description: str) -> int:
        """Create a single work item and return its ID."""
        patch = [
            JsonPatchOperation(op="add", path="/fields/System.Title", value=title),
            JsonPatchOperation(op="add", path="/fields/System.Description", value=description),
        ]
        item = self._wit_client().create_work_item(
            document=patch, project=self.project, type=work_item_type,
        )
        return item.id

    def link_parent(self, child_id: int, parent_id: int) -> None:
        patch = [
            JsonPatchOperation(
                op="add",
                path="/relations/-",
                value={
                    "rel": "System.LinkTypes.Hierarchy-Reverse",
                    "url": (
                        f"https://dev.azure.com/{self.organization}"
                        f"/_apis/wit/workItems/{parent_id}"
                    ),
                },
            )
        ]
        self._wit_client().update_work_item(document=patch, id=child_id)

    def upload_dataframe(self, df: pd.DataFrame) -> dict[str, int]:
        """Create work items from a DataFrame and link parent-child relationships.

        Returns a mapping of title → work item ID.
        """
        work_items: dict[str, int] = {}

        for _, row in df.iterrows():
            title = row["title"]
            description = row["description"]
            work_item_type = row["type"]
            wid = self.create_work_item(work_item_type, title, description)
            work_items[title] = wid
            logger.info("Created %s '%s' (id=%d)", work_item_type, title, wid)

        for _, row in df.iterrows():
            child_title = row["title"]
            parent_title = row.get("parent")
            if (
                pd.notna(parent_title)
                and parent_title in work_items
                and child_title != parent_title
            ):
                self.link_parent(work_items[child_title], work_items[parent_title])
                logger.info("Linked '%s' → '%s'", child_title, parent_title)

        return work_items
