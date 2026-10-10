# Pathology Knowledge Hub

Tools for finding pathology teaching material, inspecting its sources, and connecting that material to educational topics.

This repository contains the application and engineering work for the Hub: a reference/chat interface, an evidence-search backend, curriculum browsing tools, and content-processing scripts. The related [pathology_hub](https://github.com/herndoch/pathology_hub) repository describes the earlier data-processing pipeline.

**Share the Hub:** [Open Pathology Knowledge Hub](https://map.pathologynotebook.com/) · [Run or package the maps locally](frontend/pathology_hub_map_hub_v0_1/README.md)

**Start here:** [Project guide](docs/PROJECT_GUIDE.md) · [Consolidation and release plan](docs/REPOSITORY_CLEANUP.md)

## Explore the project

| I want to… | Start with |
|---|---|
| Browse the hosted reference interface | [Pathology Hub](https://chat.pathologynotebook.com/) |
| Explore the hosted teaching maps | [Maps hub](https://map.pathologynotebook.com/) |
| Understand the code and its dependencies | [Project guide](docs/PROJECT_GUIDE.md) |
| Work on the reference/chat application | [Application README](frontend/pathology_hub_chat_mvp/README.md) |
| Inspect the evidence backend | [Recovered backend source and provenance](backend/pathology_hub_v04_live_recovered/README_RECOVERED_SOURCE.md) |
| Understand pending work and the next release | [Consolidation and release plan](docs/REPOSITORY_CLEANUP.md) |

The maps provide one front door to the existing hosted reference library and assistant preview. See the [October 10 release record](docs/HUB_RELEASE_20261010.md) for tested workflows and deployment boundaries.

## What is in this repository?

- **Reference and chat interface:** topic browsing, evidence retrieval, source links, and optional generated answers.
- **Evidence API:** retrieval infrastructure used by the interface and the Custom GPT integration.
- **Curriculum tools:** inspection of educational topics, source mappings, and provenance.
- **Processing scripts:** preparation of lecture, textbook, figure, and other source records.
- **Engineering records:** tests, audits, API contracts, and dated implementation handoffs.

The unified teaching maps incorporate [PR #51](https://github.com/herndoch/pathology-hub-dev/pull/51) with source-provenance, navigation and sharing fixes. Their canonical implementation is `frontend/pathology_hub_map_hub_v0_1/`. [The release record](docs/HUB_RELEASE_20261010.md) distinguishes the map package from separately deployed application work.

## Run the reference/chat application

The application expects access to a configured evidence backend. Cloning this repository does not include the underlying source library or grant access to it.

In a Bash environment with Python 3.11 or later:

```bash
git clone https://github.com/herndoch/pathology-hub-dev.git
cd pathology-hub-dev/frontend/pathology_hub_chat_mvp
bash scripts/run_local.sh
```

Open [localhost:8000](http://127.0.0.1:8000/). The launcher creates a virtual environment and installs its requirements.

Provide `PATHOLOGY_HUB_API_KEY` (or `HUB_API`) through your local environment for evidence retrieval. Synthesis also needs `OPENAI_API_KEY`. Backend selection and further configuration are described in the [application README](frontend/pathology_hub_chat_mvp/README.md). These instructions were checked against the launcher; a fresh authenticated installation was not run for this documentation update.

## Development status

This is a research and development repository with work distributed across open pull requests. The October 10, 2026 inventory found **22 open PRs and 49 remote branches**. The default branch does not yet represent all of the locally developed or separately deployed work.

The shared entry point and teaching-map package are consolidated. Broader reconciliation of the separately deployed application source remains a separate workstream. See the [specific PR decisions and acceptance criteria](docs/REPOSITORY_CLEANUP.md).

## Source material and reuse

Code, source documents, derived records, and generated pages have different provenance and access requirements. This repository is not a redistribution license for third-party textbooks, figures, recordings, or institutional material. Review the applicable rights before including those assets in a release.

No root software license was found in the audited default branch. A software license and contributor-rights review remain release decisions.

Contributors should read [AGENTS.md](AGENTS.md), preserve original source records, and keep credentials and private data outside Git.
