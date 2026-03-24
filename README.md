# Agile Issue Generator

Azure OpenAI–powered pipeline that generates structured Agile backlogs (Epics → Stories → Subtasks) from natural-language project descriptions, with optional upload to **Jira** or **Azure DevOps**.

## Architecture

Uses the same patterns as [RFP-SUMMARIZER](https://github.com/Scientialibera/RFP-SUMMARIZER): modern OpenAI function calling via `tools` / `tool_choice`, frozen dataclass configuration, exponential-backoff retry, and a FastAPI viewer API.

```
┌──────────────────┐
│  Jupyter Notebook │──or──▶ FastAPI API (/api/generate)
└────────┬─────────┘        └──────┬──────┘
         │                         │
    ┌────▼─────────────────────────▼────┐
    │      Backlog Generator Pipeline    │
    │  generate → enrich → skills → roles│
    └────────────────┬──────────────────┘
                     │
         ┌───────────▼───────────┐
         │   Azure OpenAI        │
         │   (function calling)  │
         │   tools / tool_choice │
         └───────────────────────┘
                     │
         ┌───────────▼───────────┐
         │   Output (CSV / JSON) │
         └───────────┬───────────┘
                     │
         ┌───────────▼───────────┐
         │  Jira  │  Azure DevOps│  (optional upload)
         └────────┴──────────────┘
```

## What it does

1. Accepts a free-text **project description**
2. Calls Azure OpenAI with **function calling** (`tools` + `tool_choice`) to generate a structured backlog
3. **Enriches** each item with detailed Agile-compliant descriptions
4. Adds **skills** required per work item via function calling
5. Adds recommended **roles** per work item via function calling
6. Exports to **CSV** and optionally uploads to **Jira** or **Azure DevOps**

## Key patterns (from RFP-SUMMARIZER)

| Pattern | Implementation |
|---------|---------------|
| **Modern function calling** | `tools` / `tool_choice` with `AzureOpenAI` client (not legacy `functions`) |
| **Forced structured output** | `tool_choice: {"type": "function", "function": {"name": ...}}` |
| **External JSON schemas** | `app/schemas/*.json` — update extraction shapes without code changes |
| **Frozen dataclass config** | `AgileConfig` with `from_env()` and `from_toml()` for env/TOML parity |
| **Retry with backoff** | `retry_external_call` wrapping API calls with exponential backoff |
| **Azure AD auth support** | `DefaultAzureCredential` + `get_bearer_token_provider` (optional) |
| **FastAPI REST API** | Stateless API for pipeline execution and Jira/DevOps upload |
| **TOML-based deployment** | `deploy/deploy.config.toml` drives all infrastructure settings |

## Project layout

```
├── app/
│   ├── config/
│   │   └── config.py              # AgileConfig frozen dataclass
│   ├── core/
│   │   ├── azure_client.py        # Modern OpenAI client (tools API)
│   │   ├── retry.py               # Exponential backoff retry
│   │   └── backlog_generator.py   # Pipeline orchestrator
│   ├── integrations/
│   │   ├── jira_client.py         # Jira REST API client
│   │   └── devops_client.py       # Azure DevOps SDK client
│   └── schemas/
│       ├── generate_backlog.json  # Backlog generation tool schema
│       ├── generate_skills.json   # Skills extraction tool schema
│       └── generate_roles.json    # Roles extraction tool schema
├── api/
│   └── main.py                    # FastAPI backend
├── deploy/
│   ├── deploy.config.toml         # Centralized deployment config
│   └── deploy-infra.ps1           # Azure infrastructure script
├── Agile_Devops_Jira_Clean.ipynb  # Interactive notebook
├── requirements.txt
├── environment.env.example
└── .gitignore
```

## Setup

1. Clone the repository
2. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
3. Copy `environment.env.example` to `environment.env` and fill in your credentials
4. Run the notebook **or** start the API:

### Notebook
```bash
jupyter notebook Agile_Devops_Jira_Clean.ipynb
```

### API
```bash
python -m uvicorn api.main:app --reload
```

Then call:
```bash
curl -X POST http://localhost:8000/api/generate \
  -H "Content-Type: application/json" \
  -d '{
    "project_name": "my-project",
    "project_description": "Build a customer portal with SSO, dashboards, and notifications."
  }'
```

## API endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Health check |
| POST | `/api/generate` | Full pipeline (generate + enrich + skills + roles) |
| POST | `/api/generate/backlog` | Generate structure only (no enrichment) |
| POST | `/api/upload/jira` | Upload issues to Jira |
| POST | `/api/upload/devops` | Upload issues to Azure DevOps |

## Deployment

Fill in `deploy/deploy.config.toml` and run:

```powershell
.\deploy\deploy-infra.ps1
```

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `OPENAI_ENDPOINT` | Yes | Azure OpenAI endpoint URL |
| `OPENAI_KEY` | Yes* | API key (*not needed if using Azure AD auth) |
| `CHAT_ENGINE` | Yes | Model deployment name |
| `OPENAI_API_VERSION` | No | API version (default: `2025-01-01-preview`) |
| `USE_AZURE_AD_AUTH` | No | Use DefaultAzureCredential instead of API key |
| `JIRA_ID` | No | Jira email for upload |
| `JIRA_KEY` | No | Jira API token |
| `DEVOPS_ORGANIZATION` | No | Azure DevOps org for upload |
| `DEVOPS_PROJECT` | No | Azure DevOps project |
| `DEVOPS_PAT` | No | Azure DevOps PAT |
