# Local PC / VS Code / Codex Setup

## Prerequisites

- Python 3.11+
- Google Cloud SDK
- Access to project `pathology-annotation-project`
- API key for Pathology Hub service
- Optional OpenAI API key for embedding rebuilds

## Environment variables

Use `.env` locally. Do not commit it.

```text
PATHOLOGY_HUB_API_KEY=...
OPENAI_API_KEY=...
GOOGLE_CLOUD_PROJECT=pathology-annotation-project
PATHOLOGY_HUB_API_BASE=https://pathology-hub-v04-vorn5q2kga-uc.a.run.app
```

## VS Code recommendations

- Open the unzipped handoff folder as workspace or copy scripts/docs into a repo.
- Let Codex read `codex/CODEX_AGENT_PROMPT.md` first.
- Ask Codex to create a branch/checklist before changing scripts.
- Keep large GCS artifacts out of git.

## Local execution notes

Most scripts use `gcloud storage cp` and the live API. They do not require raw vector artifacts unless you explicitly ask them to download them.
