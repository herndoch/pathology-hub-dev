# Desktop Cursor — catch up with Cloud Agent work

Date: 2026-09-01  
Repo: `herndoch/pathology-hub-dev`

Cloud Agents land work as **git branches + PRs**. Desktop Cursor does not
automatically inherit chat transcripts. To get “up to speed with everything,”
pull the repo state and skim the handoff surfaces below — not Cursor Online’s
full chat history.

## Fast path (10–15 min)

```bash
cd /path/to/pathology-hub-dev
git fetch origin
git checkout master
git pull origin master

# See what Cloud Agents still have open
gh pr list --state open --limit 40

# Optional: check out the branch you care about
gh pr checkout 49   # example: chat-no-ai content map
```

In Desktop Cursor:

1. Open this repo folder (same remote).
2. Start a chat with: *“Read AGENTS.md, README.md, docs/DESKTOP_CURSOR_SYNC_WITH_CLOUD_AGENTS_v0_1.md, and summarize open PRs from `gh pr list`.”*
3. Point Desktop at specific PRs (`gh pr view N --json title,body,files`) when continuing a workstream.

## Where the knowledge lives (fix the GH gap)

| Surface | What it is |
|---------|------------|
| **Open / merged PRs** | Primary record of Cloud Agent work (title, body, commits, review) |
| **`AGENTS.md`** | Canonical local-dev / workstream rules |
| **`README.md`** / project README PRs | Repo orientation |
| **`docs/`** | Deploy, billing, hosting, handoff notes |
| **Branches `cursor/*-9231`** | Agent feature branches (even before merge) |
| **Cursor Cloud Agents UI** | Transcripts: https://cursor.com/agents — *not* cloned into Desktop |

There is no automatic “sync all online chats into Desktop.” Treat **GitHub as the source of truth**; use Cloud Agent pages only when you need the conversation trail.

## Recent Cloud Agent workstreams (Sep 2026 snapshot)

| PR | Branch | Topic |
|----|--------|-------|
| #49 | `cursor/chat-no-ai-content-map-9231` | No-AI prebuild content map + `no-ai-chat.` hosting |
| #48 | `cursor/textbook-oncotree-index-9231` | Textbook OncoTree + sample modal (figure/page/PDF) |
| #47 | `cursor/lecture-video-oncotree-index-9231` | Lecture video OncoTree |
| #46 | `cursor/billing-cost-ops-notes-9231` | Cloud Run billing / min-instance cost notes |
| #45 | `cursor/project-readme-9231` | Project-wide README |
| older open | `cursor/*-9231` | Chat MVP UX, prebuilds, GI browse, journals, etc. |

Refresh anytime:

```bash
gh pr list --state open --search "head:cursor/"
gh pr list --state merged --limit 20
```

## Live hosts (verify before claiming)

| Host | Service / notes |
|------|-----------------|
| `https://chat.pathologynotebook.com` | `pathology-hub-chat-mvp` (DNS CNAME → `ghs.googlehosted.com`) |
| `https://no-ai-chat.pathologynotebook.com` | `pathology-hub-no-ai-chat` — **needs DNS CNAME** `no-ai-chat` → `ghs.googlehosted.com.` |
| run.app fallback | `https://pathology-hub-no-ai-chat-vorn5q2kga-uc.a.run.app` |

Hosting note: `docs/HOSTING_NO_AI_CHAT_CONTENT_MAP_v0_1.md`

## Optional: bring Cloud context into Desktop more deeply

1. **Merge or review PRs** so `master` accumulates agent work.
2. Keep **PR bodies + docs/** updated (agents should already do this).
3. For a past Cloud run: open https://cursor.com/agents → copy the run URL / summary into a Desktop chat or a short `docs/` note.
4. Do **not** expect Desktop to see Cloud Agent tool transcripts unless you paste or document them.

## If something feels “missing” on Desktop

- Wrong branch / stale `master` → `git fetch` + `gh pr checkout <n>`
- Docs not merged → read the PR branch files directly
- GCP / DNS steps done only in Cloud → check `docs/*DEPLOY*`, `docs/*HOSTING*`, and open PR evidence sections
