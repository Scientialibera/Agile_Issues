from __future__ import annotations

import logging
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from app.config.config import AgileConfig
from app.core.backlog_generator import generate_backlog, run_pipeline
from app.integrations.jira_client import JiraClient
from app.integrations.devops_client import DevOpsClient

logger = logging.getLogger("agile_issues.api")

app = FastAPI(
    title="Agile Issue Generator API",
    description="Generate structured Agile backlogs using Azure OpenAI function calling.",
    version="2.0.0",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _load_config() -> AgileConfig:
    toml_path = Path(__file__).resolve().parent.parent / "config.toml"
    if toml_path.exists():
        return AgileConfig.from_toml(toml_path)
    env_path = Path(__file__).resolve().parent.parent / "environment.env"
    return AgileConfig.from_env(env_path if env_path.exists() else None)


# ── Request / Response models ────────────────────────────────────────────

class GenerateRequest(BaseModel):
    project_name: str
    project_description: str
    enrich: bool = True
    include_skills: bool = True
    include_roles: bool = True


class JiraUploadRequest(BaseModel):
    project_key: str
    issues: list[dict]


class DevOpsUploadRequest(BaseModel):
    issues: list[dict]


# ── Endpoints ────────────────────────────────────────────────────────────

@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.post("/api/generate")
def generate(req: GenerateRequest):
    """Run the full backlog generation pipeline and return the issues."""
    config = _load_config()
    try:
        df = run_pipeline(
            config,
            req.project_description,
            req.project_name,
            enrich=req.enrich,
            include_skills=req.include_skills,
            include_roles=req.include_roles,
        )
    except Exception as exc:
        logger.exception("Pipeline failed")
        raise HTTPException(status_code=500, detail=str(exc))

    issues = df.to_dict(orient="records")
    return {
        "project_name": req.project_name,
        "issue_count": len(issues),
        "issues": issues,
    }


@app.post("/api/generate/backlog")
def generate_backlog_only(req: GenerateRequest):
    """Generate just the initial backlog structure (no enrichment)."""
    config = _load_config()
    issues = generate_backlog(config, req.project_description)
    return {"project_name": req.project_name, "issue_count": len(issues), "issues": issues}


@app.post("/api/upload/jira")
def upload_to_jira(req: JiraUploadRequest):
    """Upload issues to Jira."""
    config = _load_config()
    if not config.jira_domain or not config.jira_api_token:
        raise HTTPException(status_code=400, detail="Jira credentials not configured")

    import pandas as pd
    client = JiraClient(config)
    df = pd.DataFrame(req.issues)
    keys = client.upload_dataframe(df, req.project_key)
    return {"created_count": len(keys), "keys": keys}


@app.post("/api/upload/devops")
def upload_to_devops(req: DevOpsUploadRequest):
    """Upload issues to Azure DevOps."""
    config = _load_config()
    if not config.devops_organization or not config.devops_pat:
        raise HTTPException(status_code=400, detail="Azure DevOps credentials not configured")

    import pandas as pd
    client = DevOpsClient(config)
    df = pd.DataFrame(req.issues)
    work_items = client.upload_dataframe(df)
    return {"created_count": len(work_items), "work_items": work_items}
