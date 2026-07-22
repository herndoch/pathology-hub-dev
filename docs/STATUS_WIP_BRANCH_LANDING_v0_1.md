# Status: landing `cursor/pathology-hub-chat-mvp` WIP (2026-07-22)

## Finding

The long WIP branch tip has **the same lecture / Chat MVP tree content** as `master` for the files that once looked “ahead.” Those commits already landed via squash merges:

- **PR #13** — Chat MVP UX (compare tables, figure scoping, labels, videos)
- **PR #14** — Lectures (Cipriani live + YT_Skin remaster + deck scripts/audits)

`master` is also ahead of that WIP tip on Cloud Run HTTPS (#21/#22) and Heme Anki builder (#18/#19).

So there was **nothing left to re-extract** from the WIP for lecture/YT/deck packaging.

## Clean land PRs cut from current `master`

| PR | Branch | What |
|----|--------|------|
| #23 | `cursor/anki-prompts-land-9231` | ChatGPT prompt `.txt` files (`docs/anki_chatgpt_prompts/`) — was draft #20 |
| #24 | `cursor/anki-combo-dedupe-land-9231` | ABPath+WHO combo dedupe script + artifacts — was draft #17 |
| (this) | `cursor/topic-page-ux-port-9231` | Topic-page UX from conflicting #16, ported onto current `master` without dropping Cloud Run / Videos strip |

## Safe to close after merge (superseded / conflicting)

- Draft **#20**, **#17** — replaced by #23 / #24
- Open **#16** — conflicting; content ported in topic-page UX PR
- Stacked Chat MVP **#1–#7** — historical; product already on `master`

## Do not merge

- `cursor/pathology-hub-chat-mvp` as a whole — history is a parallel timeline; tip content for lectures/chat is already on `master`
