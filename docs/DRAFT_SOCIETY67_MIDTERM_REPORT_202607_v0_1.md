# DRAFT — Society of ’67 Trainee Project Grant Mid-Term Report

**For paste into:** Mid-Term Report Template (`S67-TPG2026-Mid-TermReport…`)  
**Do not submit this file as-is** — copy into the official template, tighten numbers you want to claim, and have Balassanian review.

**Citation / acknowledgment (for any site or abstract):**  
*This work was supported by a Pathology Trainee Project Grant in Healthcare Innovation from the Society of ’67 of the Association for Academic Pathology (AAPath). The content is solely the responsibility of the authors and does not necessarily represent the official views of the AAPath.*

---

### 1. Date of Report
July __, 2026

### 2. Project Title
The UCSF Pathology Knowledge Hub: Unlocking Dormant Institutional Knowledge to Improve Diagnostic Education

### 3. Short Project Title
Unlocking Institutional Pathology Knowledge

### 4. Current Status / Progress

**Phase 0 (public proof-of-concept) — expanded and hardened beyond the original cyto-focused demo.**

Original proposal described a specialty-specific search engine over public cytopathology resources and YouTube. Mid-term, that engine has grown into a multi-source **Pathology Hub** with a resident-facing Chat/Browse UI (HTTPS Cloud Run) over a live evidence API, not only a raw search endpoint.

**Content & retrieval (public corpus — live):**
- Multi-source evidence search (textbooks, journals, PathologyOutlines / Pathoutlines, WHO, lectures/videos) with citation-grounded answers.
- Lecture/video index: **~915** timed, searchable chunks with deep links (GCS institutional-style lecture packages + live YouTube PathCast board-review ingest). Playback includes timestamped YouTube `&t=` URLs for newly ingested PathCast talks.
- PathCast **#PATHBOARDS** playlist inventoried (29 titles); Colab → GCS → semantic-gate → FAISS pipeline operational; first board-review packages (e.g. High-Yield GU; Molecular/Heme Part 2) already searchable.

**Content mapping / taxonomy (major expansion vs original proposal):**
- Built a **WHO + ABPath-aligned browse taxonomy** (nested organ/system → subcategory → diagnosis leaves) so residents navigate and retrieve by the same disease ontology used in board-oriented training—not only free-text search.
- Topic pages, multi-query retrieval, root-narrowing (keep retrieval on the relevant organ system), diagnosis compare, figure filtering, and WHO cross-mention surfacing.
- Semantic gating of lecture chunks to browse leaves (embeddings over ABPath/WHO-style tags), so video hits carry a diagnosis tag + timestamp, not only a video title.

**Resident-facing product (expansion):**
- **Pathology Hub Chat MVP** — Browse + Ask modes, teaching notes, citations, topic pages, compare diagnoses — deployed for iterative use while we continue ingestion.
- Board-study adjacent tooling (e.g. Heme contextual-cloze Anki builder handoffs) using the same taxonomy discipline; kept as a separate workstream but same ABPath/resident exam relevance.

**Phase 1 (grant-funded institutional ingestion) — in progress, not complete:**
- Pipeline pieces proposed (Whisper / captions-first, chunking, vector index, timestamp jump) are proven on public/board-review video at scale.
- Systematic batch ingest of **UCSF proprietary** didactics (department video library, PHI-safe didactic only) and formal pre/post trainee surveys remain the funded core and are the next execution block for months 4–7 style batch work and months 1–3 / 11–12 evaluation.

**Honest “expanded from original” one-liner for reviewers:**  
We moved from a cyto PoC search box to a multi-source Hub with ABPath/WHO content mapping, a Chat/Browse teaching UI, and a repeatable PathCast/board-lecture ingest loop—while still targeting UCSF dormant institutional video as the grant’s primary Phase 1 deliverable.

### 5. Challenges or obstacles?

- **YouTube / age gates & bot checks:** Cloud agents cannot reliably download YouTube; Colab “one video per deleted runtime” + captions-first is the workable path. Age-restricted titles (e.g. some non-PathCast breast reviews) may be skipped or need cookies.
- **Semantic gate selectivity:** Thousands of caption segments consolidate to a small set of high-confidence tagged chunks (~8–15 per long board talk). Improves precision for search; some spoken content never becomes indexable—acceptable for JIT retrieval, not a full verbatim archive.
- **Institutional access & compliance:** UCSF proprietary library still requires coordinated collection, PHI-safe filtering (didactics only; no tumor boards), and IRB exemption / QI framing before bulk ingest—slower than public PathCast work.
- **Evaluation lag:** External/internal survey instruments were planned early; formal pre-implementation trainee survey + post at 3 months still need scheduling against residency calendar.
- **Infra reality vs proposal wording:** Production stack evolved on GCP (Cloud Run + GCS indexes) rather than only the Pinecone sketch in the proposal; educational function (vector RAG + timestamped retrieval) is unchanged.

### 6. Future Goals and Plan for Project Completion

1. **Finish Phase 1 institutional ingest:** Collect/authorize UCSF didactic video + slide materials; Whisper/OCR where needed; sanitize; index; expose only inside appropriate access boundaries.
2. **Complete PathCast #PATHBOARDS Colab queue** (gate-ready subset) to strengthen public board-review coverage while institutional batch runs.
3. **Evaluation:** Run pre-implementation survey (UCSF trainees); after ~3 months Hub use, post survey; compare diagnostic confidence, time-to-answer, and institutional asset utility (as proposed).
4. **Manuscript / abstract:** Target *Academic Pathology* and/or API meeting abstract; acknowledge Society of ’67 per award terms.
5. **Phase 2 prep (not this grant’s spend):** Use Phase 1 corpus toward knowledge-graph / tutor reasoning in a future funding ask—not required for Phase 1 completion.

### 7. Update to timeline, if any

Original year sketch (surveys → batch months 4–7 → integrate → post survey) remains the spine. **Adjustment:** Public corpus, taxonomy mapping, and Chat UI advanced earlier than expected (useful for demos and board-review value). **Institutional UCSF batch + formal surveys** are the critical path for second disbursement and final report—calendar to complete within the 2026 award year. Mid-term report submitted to unlock remaining funds per Society of ’67 terms.

### 8. End Date of Project
[Confirm from award letter — typically end of 2026 award period / one calendar year from start. Fill exact date.]

### 9. Journal you plan to submit a manuscript to
*Academic Pathology* (AAPath; Open Access Publication Award eligibility per award terms). Secondary: Association for Pathology Informatics (API) abstract.

### 10. Status of budget

$[Fill from UCSF CGA / Ellyn McCaffrey.] First installment received/processed for department account; remaining installment contingent on this mid-term. Spend to date focused on compute/API (transcription, embeddings, Cloud Run) aligning with proposed ingestion costs. No change to payable department routing unless noted in §12.

### 11. Applicant Information

- **Name:** Charles Herndon, DO  
- **Degree(s):** DO  
- **Academic Level:** Resident Physician (PGY-[update])  
- **Program/Institution:** Anatomic Pathology Residency, University of California, San Francisco (UCSF)  
- **Email:** Charlie.Herndon@ucsf.edu  

### 12. Faculty advisor / check address

- **Faculty Advisor:** Ronald Balassanian, MD — **same** (Professor of Pathology; Director, Pathology Residency Program; Ronald.Balassanian@ucsf.edu)  
- **Grant check / department address:** **same** (UCSF Dept of Pathology / M_Path-Anatomic Path; attn Ellyn McCaffrey / CGAsvcdesk@ucsf.edu — as on ATF), unless CGA provides an update.

---

## Optional “Page 2” detail — Expansion from original proposal (for §4 overflow)

| Original (proposal) | Mid-term expansion |
|---------------------|--------------------|
| Cyto-focused public PoC search | Multi-source Hub (textbooks, journals, Pathoutlines, WHO, lectures) |
| YouTube lectures mentioned | Operational PathCast #PATHBOARDS ingest + timestamped YouTube search hits |
| Index for retrieval | **ABPath + WHO content mapping** / browse tree / topic pages / compare |
| Search API mindset | Resident **Chat + Browse** teaching UI (Cloud Run HTTPS) |
| Whisper + vector DB for UCSF videos | Same methods proven; UCSF proprietary batch still the funded Phase 1 centerpiece |
| Outcome surveys planned | Instruments/design retained; administration pending residency logistics |

## ABPath / resident relevance (one paragraph you can reuse)

The Hub is built for pathology trainees preparing under the American Board of Pathology knowledge framework: navigation and tagging use **ABPath-aligned (and WHO) disease leaves**, PathCast **board-review** lectures are being indexed to timestamped chunks, and the Chat/Browse interface supports just-in-time retrieval at the microscope—matching the grant’s education aims (andragogy / JIT learning) rather than clinical autonomous diagnosis.

---

### Before you send
- [ ] Confirm budget numbers and project end date with CGA  
- [ ] Update PGY year  
- [ ] Balassanian review / sign-off  
- [ ] Attach any screenshot of Browse/Chat or PathCast hit if template allows appendix  
- [ ] Submit by **July 31** to Amelia Stephenson / awards channel per AAPath email  
