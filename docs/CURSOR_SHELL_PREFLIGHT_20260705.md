# Cursor Shell Preflight — 2026-07-05

**Scope:** Shell execution guidance for Cursor agents on this machine. No production deploy performed as part of this doc update.

## Authoritative guidance (post-fix, 2026-07-05)

1. **Windows PowerShell on `\\wsl$\...` is NOT the production shell for agent work.** Do not treat the UNC workspace path or a Windows-side cwd as the environment for git, gcloud, python, or deploy commands.

2. **WSL Ubuntu is the production shell.** All agent command execution for this repo must run inside WSL Ubuntu.

3. **Future agents MUST use this command style:**

   ```bash
   wsl -d Ubuntu -- bash -lc "cd /home/herndonch/pathology-hub-dev && <COMMAND>"
   ```

   Use the absolute WSL repo path (`/home/herndonch/pathology-hub-dev`), not `~/pathology-hub-dev`, in agent Shell invocations for consistency.

4. **It IS safe to resume backend recovery using gcloud / Cloud Build** from WSL via the command style above.

5. **Do NOT use local Docker image extraction** unless Docker is installed in WSL. Docker is not present today (see limitations below). Prefer gcloud and Cloud Build over local Docker for image/build workflows.

---

## Post-fix verification 20260705

Human confirmed the following commands work **manually** in WSL Ubuntu from `/home/herndonch/pathology-hub-dev`:

```bash
wsl -d Ubuntu -- bash -lc "cd /home/herndonch/pathology-hub-dev && pwd"
# → /home/herndonch/pathology-hub-dev

wsl -d Ubuntu -- bash -lc "cd /home/herndonch/pathology-hub-dev && git status --short"
# → succeeds (repo status readable)

wsl -d Ubuntu -- bash -lc "cd /home/herndonch/pathology-hub-dev && python3 --version"
# → succeeds

wsl -d Ubuntu -- bash -lc "cd /home/herndonch/pathology-hub-dev && gcloud --version"
# → succeeds
```

### Known limitation (not a blocker)

```bash
wsl -d Ubuntu -- bash -lc "cd /home/herndonch/pathology-hub-dev && docker --version"
# → FAIL — Docker is NOT installed in WSL Ubuntu
```

- Document as a **limitation**, not a blocker for backend recovery or Cloud Build–based workflows.
- **Do not install Docker** unless a future production release truly requires local image extraction.
- Prefer **gcloud / Cloud Build** over local Docker for build and deploy tasks.

### Safe to resume?

| Workstream | Safe? | Notes |
|------------|-------|-------|
| Backend recovery via gcloud / Cloud Build | **Yes** | Use WSL command style above |
| git, python3, gcloud from agent | **Yes** | Confirmed working manually; agents should use WSL wrapper |
| Local Docker extraction / `docker pull` / image inspect | **No** | Docker not installed in WSL; do not attempt unless Docker is added later |

---

## Environment

| Item | Value |
|------|-------|
| OS | Windows 10.0.26200 |
| Cursor workspace (Windows UNC) | `\\wsl$\Ubuntu\home\herndonch\pathology-hub-dev` |
| **Production shell** | **WSL Ubuntu** |
| Repo path (WSL) | `/home/herndonch/pathology-hub-dev` |
| Agent Shell cwd (Windows, non-production) | `C:\Users\hernd\AppData\Local\Programs\cursor\Microsoft.PowerShell.Core\FileSystem::\\wsl$\Ubuntu\home\herndonch\pathology-hub-dev` |
| Git branch (read via `.git/HEAD`) | `evidence-search-reliability-v0_2-prod` |

---

## Historical context: spawn ENOENT (pre-fix)

Before human verification on 2026-07-05, the Cursor agent Shell tool failed immediately at process spawn:

```text
error: "spawn C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe ENOENT"
```

This happened **before** the requested command ran — not a WSL hang, git hang, or sandbox timeout.

### Test matrix (2026-07-05, agent Shell tool — pre-fix)

Each test failed at spawn unless noted.

| # | Command style | Command | Result | Notes |
|---|---------------|---------|--------|-------|
| 1 | Plain PowerShell | `Write-Output "PS_TEST_OK"` | **FAIL** | Spawn ENOENT (~12–18 ms) |
| 2 | pwsh explicit | `& "C:\Program Files\PowerShell\7\pwsh.exe" ...` | **FAIL** | Spawn ENOENT — never reaches pwsh |
| 3 | cmd.exe | `cmd.exe /c echo CMD_TEST_OK` | **FAIL** | Spawn ENOENT |
| 4 | WSL | `wsl -d Ubuntu bash -lc "pwd && whoami && echo WSL_OK"` | **FAIL** (session) | Spawn ENOENT |
| 5 | git | `git status --short` | **FAIL** | Spawn ENOENT |
| 6 | gcloud | `gcloud --version` | **FAIL** | Spawn ENOENT |
| 7 | docker | `docker --version` | **FAIL** | Spawn ENOENT |
| 8 | python | `python --version` | **FAIL** | Spawn ENOENT |

One allowlisted WSL command succeeded transiently earlier in the same session:

```text
wsl -d Ubuntu bash -lc "pwd && whoami && echo OK"
→ /home/herndonch/pathology-hub-dev
→ herndonch
→ OK
→ exit 0 (~3.2 s, outside sandbox allowlist)
```

Secondary sandbox error (also observed when sandbox was attempted without `["all"]`):

```text
Sandbox policy 'workspace_readwrite' is not supported on this system.
Ensure the sandbox helper binary is available, or use 'insecure_none'.
Reason: Windows sandbox helper only provides network proxy, not filesystem isolation
```

### Root cause (most likely, pre-fix)

Cursor's agent Shell on Windows targeted:

```text
C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe
```

That path was missing, blocked, or unavailable (`ENOENT`). Wrapping commands in `wsl`, `pwsh`, or `cmd` from inside a broken agent Shell did not help — the wrapper never started.

**Post-fix mitigation:** agents run all repo commands via explicit WSL invocation (see authoritative guidance). Human manual verification confirms WSL tooling works; agents should use the mandated `wsl -d Ubuntu -- bash -lc "cd /home/herndonch/pathology-hub-dev && ..."` pattern.

---

## What works via non-shell tools

| Capability | Status | Notes |
|------------|--------|-------|
| Read repo files via UNC | **OK** | `Read`, `Glob`, `Grep` on `\\wsl$\Ubuntu\home\herndonch\pathology-hub-dev\...` |
| Git metadata (read-only) | **OK** | `.git/HEAD` readable via file tools |
| WSL command execution | **OK** | Confirmed manually post-fix; use WSL wrapper from agent |

---

## Command style for future agents

**Required:**

```bash
wsl -d Ubuntu -- bash -lc "cd /home/herndonch/pathology-hub-dev && <COMMAND>"
```

**Avoid:**

- Running git, gcloud, python, or deploy scripts directly from Windows PowerShell against `\\wsl$\` as the production environment.
- Assuming `\\wsl$\` cwd is a normal Windows path for native git/gcloud/docker.
- Local Docker extraction when Docker is not installed in WSL.
- Long-running parallel WSL calls before confirming single-command reliability.

**Prefer gcloud / Cloud Build** over local Docker for builds and deploys until Docker is explicitly installed and verified in WSL.

---

## Tool availability (post-fix)

| Tool | WSL verified? | Notes |
|------|---------------|-------|
| git | **Yes** | `git status --short` confirmed |
| gcloud | **Yes** | `gcloud --version` confirmed |
| python3 | **Yes** | `python3 --version` confirmed |
| wsl | **Yes** | `pwd` → `/home/herndonch/pathology-hub-dev` |
| docker | **No (not installed)** | `docker --version` fails in WSL; limitation only — use Cloud Build |

---

## Related doc

If WSL-specific hangs recur after spawn is fixed, capture hang vs success patterns in a follow-up:

- `docs/CURSOR_WSL_SHELL_FAILURE_20260705.md` (not created — spawn failure was the initial blocking issue)

---

*Preflight updated 2026-07-05 with post-fix verification. No production deploy, benchmark, or backend changes were made as part of this doc update.*
