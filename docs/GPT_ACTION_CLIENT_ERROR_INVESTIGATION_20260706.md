# GPT Action "ClientResponseError" Investigation — 2026-07-06

**Read-only investigation. No Cloud Run config, GCS object, or GPT Builder
configuration was changed while producing this report.**

## Conclusion (read this first)

**The requests from the cloned GPT never reached the `pathology-hub-v04` backend
at all — confirmed via Cloud Run's proxy-level request logs, which capture every
incoming HTTP request regardless of success or failure.** This rules out a backend
problem entirely. The most likely root cause is an **Authentication/Action
configuration issue specific to the newly duplicated GPT** — most plausibly the
Action's API key field being empty or not carried over from the original GPT during
duplication (a known GPT Builder limitation), causing ChatGPT's own client to fail
before ever dispatching the network request. This is **not** best explained by a
backend timeout, because Charlie reported uniform failure across every single call
on every source tested separately, which is inconsistent with this session's own
reproduction showing fast (sub-second) responses for the exact same queries on
every source individually.

---

## Step 1: Is production healthy right now, and do Charlie's exact queries succeed?

```
GET https://pathology-hub-v04-vorn5q2kga-uc.a.run.app/health
HTTP 200 in 0.20s
version: 1.5.10-html-bundle-v0.2-prod, loaded: true, all v0_2 flags true
```

**Reproduced both of Charlie's exact queries, using the same `X-API-Key` header
mechanism used throughout this session:**

| Query | Sources | Result |
|---|---|---|
| "sessile serrated lesion" | who + textbooks + pathout (combined) | HTTP 200, 26.48s, all 3 sources `ok` |
| "tubular adenoma colon" | who + textbooks + pathout (combined) | HTTP 200, 1.53s, all 3 sources `ok` |

**Then re-tested matching Charlie's actual reported pattern (each source tested
separately, not combined):**

| Query | Source | HTTP | Elapsed |
|---|---|---|---|
| sessile serrated lesion | who | 200 | 0.15s |
| sessile serrated lesion | textbooks | 200 | 0.43s |
| sessile serrated lesion | pathout | 200 | 0.72s |
| tubular adenoma colon | who | 200 | 0.13s |
| tubular adenoma colon | textbooks | 200 | 0.39s |
| tubular adenoma colon | pathout | 200 | 0.58s |

**All 8 reproduction calls succeeded with HTTP 200 and returned real results.**
**This directly confirms: the backend itself is healthy and correctly serving the
exact queries Charlie reported failing, on every source he tested.** This strongly
points away from a backend/production problem.

(One incidental observation: the first combined 3-source call took 26.48s — the same
"first live request per instance lifecycle" warm-up phenomenon documented in
`docs/PRODUCTION_COLD_START_FIX_APPLIED_20260706.md`. This is unrelated to Charlie's
issue, since it does not explain a *uniform* failure across every single
separately-tested source call, and every one of my single-source reproductions was
sub-second.)

## Step 2 & 3: Cloud Run request logs for the last 90 minutes

Checked two independent log sources for maximum certainty:

1. **Application-level access logs** (uvicorn's own request logging, visible via
   `resource.type="cloud_run_revision"`): only 18 entries in a 90-minute window
   (17:42-19:12 UTC), and **all 18 are timestamped 19:07:11 UTC or later — i.e. all
   of them are this investigation's own reproduction calls**, not Charlie's testing.
2. **Proxy-level request logs** (`run.googleapis.com/requests`, which capture
   *every* HTTP request that reaches the Cloud Run service's front door, including
   any that would be rejected before the application code runs — e.g. malformed
   requests, auth failures returned by the app, or anything else): only **9**
   entries in the same 90-minute window, **all with `userAgent: Python-urllib/3.14`
   or `curl/8.18.0`** (this investigation's own tooling) and **all HTTP 200**.

**There is not a single logged request — successful, 401, 400, or any other status
— from any client resembling ChatGPT's Action-calling infrastructure, at any point
in the last 90 minutes, before this investigation's own testing began.**

This directly answers the task's diagnostic questions:
- **(a) Any incoming requests at all matching Charlie's timeframe?** No.
- **(b) What status codes did they get?** N/A — none arrived.
- **(c) 401/403 responses in the window?** **None** — this rules out "GPT sent a
  wrong-but-present API key and got rejected by the server," since that scenario
  would necessarily produce a logged request (uvicorn logs the outcome of every
  request it actually processes, success or failure, exactly as seen for all 18 of
  this investigation's own calls above).

Also checked the three other Cloud Run services in this project that could
plausibly have been the target if the clone's Action URL were misconfigured to
point elsewhere (`pathology-hub-v04-v0-2-staging`,
`pathology-hub-v04-curriculum-staging`, `pathology-hub-v04-html-staging`): **zero
request-log entries on any of them in the same window.** This doesn't fully rule out
every conceivable wrong-URL scenario (e.g. a typo producing a URL that resolves to
nothing at all, which would obviously show no logs anywhere), but it does rule out
the request having landed on any other known sibling service in this project.

## Step 4: What this evidence means

**Since zero requests reached `pathology-hub-v04` (or any known sibling service) at
the network level, the failure occurred entirely before or during ChatGPT's attempt
to dispatch the HTTP request — not after.** A wrong-but-present API key would still
produce a request that arrives and gets a 401 (logged); a slow backend would still
produce a request that arrives and eventually returns 200 or times out server-side
(also logged, since Cloud Run logs a request as soon as it's dispatched to the
container, not only on completion). Neither pattern appears anywhere in the logs.

The evidence most consistent with **zero outbound network activity from ChatGPT's
side** is:

1. **Most likely: the Action's Authentication field is empty (not merely wrong) in
   the duplicated GPT.** GPT Builder does not always reliably carry over a saved
   Action credential when a GPT is duplicated — this is a widely-reported behavior,
   not specific to this project. If the Authentication field is empty while the
   Action's OpenAPI schema declares `security: - ApiKeyAuth: []` (i.e. auth is
   required), ChatGPT's own client-side Action-calling code can recognize that a
   required credential is missing and refuse to send the request at all, surfacing
   a generic client-side error (consistent with a generic class name like
   "ClientResponseError") without ever making a network call. This exactly matches
   the observed zero-request evidence.
2. **Also possible, not ruled out by available evidence: a wrong/mistyped server
   URL** in the clone's Action config (e.g. a typo, extra character, or wrong
   Cloud Run project/service entirely) that resolves to nothing or to an
   unrelated/unreachable host, so no request would ever appear on any service in
   this project. This session cannot inspect the clone's actual configured URL
   string (no GPT Builder access) to confirm or rule this out directly.
3. **Less likely: an OpenAPI schema issue causing client-side request-construction
   failure before sending (hypothesis d).** Reviewed
   `gpt_builder/pathology_hub_gpt_v0_2_rebuild_package_20260706/GPT_ACTION_OPENAPI_CURRENT_RECOMMENDED.yaml`
   carefully for known OpenAI Action schema gotchas (unsupported `oneOf`/`allOf`
   patterns, missing `operationId`, malformed `$ref`, missing `servers`, incorrect
   `security` placement) — found none. This file is **byte-for-byte identical to
   the schema already proven working in the original, non-cloned production GPT**
   for the entire duration of this release, except for one added optional response
   property (`query_expansion_applied: boolean`) that cannot affect request
   construction (it is a response field, not a request field). This makes a
   schema-triggered client-side failure the least likely of the three
   explanations — though it cannot be fully ruled out if Charlie made a manual
   transcription error while copying the schema into GPT Builder rather than using
   the file verbatim.
4. **Ruled out: a real backend/production problem.** Directly disproven by Step 1's
   8/8 successful reproductions of Charlie's exact queries, and by the total
   absence of any error, slow-response, or crash signal anywhere in the backend's
   own logs during the relevant window (there is nothing there to have failed).
5. **Ruled out as the primary explanation: a pure timeout issue.** This session's
   own timing data shows single-source queries consistently sub-second when warm
   (0.13-0.72s), and Charlie reported *uniform* failure across every single
   separately-tested source/query combination — a timeout is much more likely to be
   intermittent (dependent on cold-start timing, as documented in
   `docs/PRODUCTION_COLD_START_FIX_APPLIED_20260706.md`) than to fail 100% of
   attempts identically. A pure timeout also would not explain the total absence of
   any corresponding proxy-level log entry, since Cloud Run logs a request as soon
   as it is received, before the response is generated — a slow request that later
   times out client-side would still show up in the proxy request log with a long
   `latency` value, which none of the 9 real entries exhibit (all are from this
   investigation, all fast).

## Recommendation for Charlie (concrete, specific)

1. **Open the duplicated GPT's Action configuration in GPT Builder
   ("Pathology Hub GPT — Search Only v1.00 (copy)" → Configure → Actions →
   Authentication).** Check whether an API key value is actually present in the
   Authentication field at all. If it is empty, or shows a placeholder/masked value
   that doesn't look right, **re-paste the correct API key value.** The secret name
   in Secret Manager is `pathology-hub-api-key` — this session does not have and
   will not print its plaintext value; Charlie should retrieve it himself (e.g. via
   `gcloud secrets versions access latest --secret=pathology-hub-api-key
   --project=pathology-annotation-project` in his own terminal, or from wherever he
   originally sourced it for the live GPT) and paste it into the clone's
   Authentication field.
2. **Confirm the Authentication *type* is still set correctly** — API Key,
   Custom Header, header name exactly `X-API-Key` (not `Authorization` or
   `Bearer`). A duplicate can sometimes reset this to a default that doesn't match.
3. **Confirm the Action's server URL field reads exactly
   `https://pathology-hub-v04-vorn5q2kga-uc.a.run.app`** with no typo, trailing
   slash mismatch, or accidental reference to a different service.
4. **Click Update/Save**, then retry one of the exact failing queries (e.g. "SSL
   colon" via `who` only) in Preview.
5. **If it still fails after re-confirming all three of the above**, the next
   diagnostic step would be for Charlie to check GPT Builder's own Action-call debug
   trace (if visible in Preview) for the *exact* error ChatGPT received — this
   session cannot see that trace and can only infer from the "ClientResponseError"
   name and the backend-side absence of evidence.

## Files referenced

- `audits/gpt_action_client_error_investigation_20260706/health.json`
- `audits/gpt_action_client_error_investigation_20260706/probe_sessile_serrated_lesion_multi_source.json`
- `audits/gpt_action_client_error_investigation_20260706/probe_tubular_adenoma_colon.json`
- `audits/gpt_action_client_error_investigation_20260706/single_source_*.json` (6 files)
- `audits/gpt_action_client_error_investigation_20260706/logs_90m.json` (app-level access logs)
- `audits/gpt_action_client_error_investigation_20260706/logs_requests_90m.json` (proxy-level request logs, the decisive evidence)
