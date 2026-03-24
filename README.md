# Agile Issue Generator

Azure OpenAI-powered pipeline that generates structured Agile backlogs (Epics, Stories, Subtasks) from natural-language project descriptions, with optional upload to **Jira** or **Azure DevOps**.

## Architecture

Built with modern OpenAI function calling (`tools` / `tool_choice`), frozen dataclass configuration, exponential-backoff retry, and a FastAPI REST API.

```
  CLI (main.py)  ──or──  FastAPI API (api/main.py)
        │                        │
   ┌────▼────────────────────────▼────┐
   │     Backlog Generator Pipeline    │
   │  generate → enrich → skills → roles│
   └──────────────┬───────────────────┘
                  │
      ┌───────────▼───────────┐
      │     Azure OpenAI       │
      │   (function calling)   │
      │   tools / tool_choice  │
      └───────────────────────┘
                  │
      ┌───────────▼───────────┐
      │   Output (CSV / JSON)  │
      └───────────┬───────────┘
                  │
      ┌───────────▼───────────┐
      │  Jira  │  Azure DevOps │  (optional upload)
      └────────┴──────────────┘
```

## What it does

1. Accepts a free-text **project description**
2. Calls Azure OpenAI with **function calling** (`tools` + `tool_choice`) to generate a structured backlog
3. **Enriches** each item with detailed Agile-compliant descriptions
4. Adds **skills** required per work item via function calling
5. Adds recommended **roles** per work item via function calling
6. Exports to **CSV / JSON** and optionally uploads to **Jira** or **Azure DevOps**

## Key patterns

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
├── main.py                        # CLI entry point
├── app/
│   ├── __main__.py                # python -m app support
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

## Usage

### CLI

```bash
# Full pipeline: generate + enrich + skills + roles
python main.py generate --name "my-project" --description "Build a customer portal with SSO, dashboards, and notifications."

# Read description from a file
python main.py generate --name "my-project" --file project_brief.txt

# Skip enrichment for faster output (structure only)
python main.py generate --name "my-project" --description "..." --no-enrich --no-skills --no-roles

# Generate and also save as JSON
python main.py generate --name "my-project" --description "..." --json

# Generate and upload to Jira
python main.py generate --name "my-project" --description "..." --upload jira --project-key PROJ

# Generate and upload to Azure DevOps
python main.py generate --name "my-project" --description "..." --upload devops

# Use a TOML config file instead of .env
python main.py --config config.toml generate --name "my-project" --description "..."

# Verbose logging
python main.py -v generate --name "my-project" --description "..."
```

### FastAPI Server

```bash
# Start the API server
python main.py serve

# With auto-reload for development
python main.py serve --reload --port 8000
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

### Module invocation

```bash
python -m app generate --name "my-project" --description "..."
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
