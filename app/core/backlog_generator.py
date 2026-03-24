from __future__ import annotations

import json
import logging
import os
from pathlib import Path

import pandas as pd

from app.config.config import AgileConfig
from app.core.azure_client import AgileExtractor

logger = logging.getLogger("agile_issues.generator")

SCHEMAS_DIR = Path(__file__).resolve().parent.parent / "schemas"

SYSTEM_ARCHITECT = (
    "You are an Expert Technology Architect. Your job is to generate a "
    "structured Agile backlog based on your expert knowledge of past projects "
    "of a similar type. Organize the project into Epics, Stories, and Subtasks. "
    "Titles should be concise. Descriptions must be Agile-compliant (50 words or "
    "less). Subtasks belong to Stories, Stories belong to Epics."
)

SYSTEM_SOLUTIONS_ARCHITECT = (
    "You are a Master Solutions Architect, both a technical expert and a "
    "business leader."
)


def generate_backlog(config: AgileConfig, project_description: str) -> list[dict]:
    """Generate the initial backlog of Epics/Stories/Subtasks from a project description."""
    extractor = AgileExtractor.from_schema_file(config, SCHEMAS_DIR / "generate_backlog.json")
    result = extractor.extract(SYSTEM_ARCHITECT, project_description)
    issues = result.get("issues", [])
    for issue in issues:
        if issue.get("type") == "Epic":
            issue["parent"] = None
    return issues


def enrich_descriptions(
    config: AgileConfig,
    issues: list[dict],
    project_description: str,
) -> list[dict]:
    """Re-generate longer, context-aware descriptions for each issue."""
    extractor = AgileExtractor.from_schema_file(config, SCHEMAS_DIR / "generate_backlog.json")
    other_items = "\n".join(f"{i['type']}: {i['title']}" for i in issues)

    for issue in issues:
        issue_type = issue["type"]
        length = 300 if issue_type == "Epic" else 200 if issue_type == "Story" else 100
        context_without_current = other_items.replace(f"{issue_type}: {issue['title']}\n", "")

        prompt = (
            f"Project Overview:\n{project_description}\n\n"
            f"Other Items in the Project:\n{context_without_current}\n\n"
            f"Write an Agile-compliant description of ~{length} words for a(n) "
            f"{issue_type} titled: '{issue['title']}' - {issue['description']}\n"
            f"If it's an Epic, write as a Product Owner; if a Story, as a Tech Lead; "
            f"if a Subtask, as a Developer."
        )
        enhanced = extractor.chat(SYSTEM_SOLUTIONS_ARCHITECT, prompt)
        issue["description"] = enhanced

    return issues


def add_skills(config: AgileConfig, issues: list[dict]) -> list[dict]:
    """Add a 'skills' field to each issue via function calling."""
    extractor = AgileExtractor.from_schema_file(config, SCHEMAS_DIR / "generate_skills.json")

    for issue in issues:
        parent = issue.get("parent") or "None"
        prompt = (
            f"Given a work item with title '{issue['title']}', "
            f"description '{issue['description']}', type '{issue['type']}', "
            f"and parent '{parent}', list the skills required to deliver it."
        )
        result = extractor.extract(SYSTEM_SOLUTIONS_ARCHITECT, prompt)
        issue["skills"] = result.get("skills", [])

    return issues


def add_roles(config: AgileConfig, issues: list[dict]) -> list[dict]:
    """Add a 'roles' field to each issue via function calling."""
    extractor = AgileExtractor.from_schema_file(config, SCHEMAS_DIR / "generate_roles.json")

    for issue in issues:
        parent = issue.get("parent") or "None"
        prompt = (
            f"Given a work item with title '{issue['title']}', "
            f"description '{issue['description']}', type '{issue['type']}', "
            f"and parent '{parent}', list 5 IT roles that could deliver this issue."
        )
        result = extractor.extract(SYSTEM_SOLUTIONS_ARCHITECT, prompt)
        issue["roles"] = result.get("roles", [])

    return issues


def run_pipeline(
    config: AgileConfig,
    project_description: str,
    project_name: str,
    *,
    enrich: bool = True,
    include_skills: bool = True,
    include_roles: bool = True,
) -> pd.DataFrame:
    """Full pipeline: generate → enrich → skills → roles → DataFrame.

    Returns a DataFrame with columns:
      title, description, parent, type, skills, roles
    """
    logger.info("Starting backlog generation for project: %s", project_name)

    issues = generate_backlog(config, project_description)
    logger.info("Generated %d issues", len(issues))

    if enrich:
        issues = enrich_descriptions(config, issues, project_description)
        logger.info("Descriptions enriched")

    if include_skills:
        issues = add_skills(config, issues)
        logger.info("Skills added")

    if include_roles:
        issues = add_roles(config, issues)
        logger.info("Roles added")

    df = pd.DataFrame(issues)

    output_dir = Path(config.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / f"{project_name}.csv"
    df.to_csv(output_path, index=False, encoding="utf-8")
    logger.info("Final CSV saved to %s", output_path)

    return df
