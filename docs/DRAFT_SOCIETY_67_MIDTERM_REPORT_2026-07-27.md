# DRAFT — Society of ’67 Trainee Project Grant Mid-Term Report

**Paste into the official Mid-Term Report Template.** Have Dr. Balassanian review before sending. Due July 31.

**Acknowledgment (for publications/presentations):**  
*This work was supported by a Pathology Trainee Project Grant in Healthcare Innovation from the Society of ’67 of the Association for Academic Pathology (AAPath).*

---

### 1. Date of Report
July __, 2026

### 2. Project Title
The UCSF Pathology Knowledge Hub: Unlocking Dormant Institutional Knowledge to Improve Diagnostic Education

### 3. Short Project Title
Unlocking Institutional Pathology Knowledge

### 4. Current Status / Progress

**Where it started**

The grant proposed a cytopathology proof-of-concept, then bulk ingest of UCSF’s teaching archive, with resident surveys to measure confidence and time-to-answer.

- A searchable demo that finds the right moment in a lecture or slide deck.
- Ingest of departmental teaching materials (didactics only; no patient tumor boards).
- Pre/post surveys with pathology trainees.
- A write-up for *Academic Pathology* with Society of ’67 acknowledgment.

**1. Searchable is not the same as findable**

Early work showed that transcripts and keyword search are necessary but not sufficient. Trainees need to browse by diagnosis and organ system—the way they study for boards—not hunt for exact phrases.

**What we built:** a Hub where residents browse by ABPath/WHO-aligned topics and open cited answers from textbooks, PathologyOutlines, WHO material, journals, and lectures.

**2. The archive only becomes an asset once it is verified**

A lecture library on disk is dormant until each source is transcribed, chunked, tagged, and checked. Public board-review lectures (PathCast PATHBOARDS, hematopathology boards content) were ingested first because access was straightforward.

**What we built:** a verified public layer with timestamped lecture search—residents jump to the relevant teaching moment instead of scrubbing whole videos.

**3. Answer by pointing, not by generating**

The educational goal is to connect a trainee’s question to trusted source material with citations—not to produce unsourced prose. The interface emphasizes links, excerpts, and video timestamps.

**What we built:** a teaching-oriented chat and browse experience that returns cited evidence and opens videos at the matched segment.

**4. Finding, choosing, and answering are three different problems**

Search retrieves candidates; browse helps a trainee pick the right source; the answer layer summarizes with pointers back to originals. Treating these as one step produces noisy or untrustworthy results.

**What we built:** separate browse (taxonomy navigation), search (multi-source retrieval), and answer (cited synthesis) layers that work together on the same Hub.

**Where it stands now**

Mid-term, the project is on track educationally and has grown beyond the original cytopathology demo into a broader **Pathology Knowledge Hub** that residents can browse and query. The public proof-of-concept is richer than planned. The funded core for the second half of the award year remains UCSF internal ingest and the trainee evaluation surveys.

### 5. Challenges or obstacles?

**Online lecture access**

Some high-yield board-review videos are behind platform restrictions (e.g. age gates), which slows systematic ingest.

**What changed:** We use a supervised upload workflow and skip titles that cannot be processed cleanly rather than blocking the whole pipeline.

**Turning lectures into study “bites”**

Full talks must be segmented into topic-matched chunks. Not every spoken sentence belongs in search results.

**What changed:** We prioritize the clearest, diagnosis-aligned segments. This improves finding the right teaching point; it is not a substitute for watching the whole lecture.

**UCSF internal content**

Departmental teaching materials require coordination with faculty, privacy-safe handling, and confirmation that content is didactic only.

**What changed:** Public board-review lectures advanced first to demonstrate resident value while internal collection proceeds in parallel.

**Resident survey timing**

Formal pre/post surveys need scheduling around clinical rotations and call schedules.

**What changed:** IRB preparation and baseline survey design are underway; surveys will follow once the UCSF ingest reaches a testable milestone.

**Build scope took longer than the original timeline assumed**

Getting search, browse, tagging, and lecture timestamps to work together as one Hub required more engineering iteration than a single-source demo.

**What changed:** Evaluation was sequenced after the build milestone rather than in parallel with early prototyping. The end date of the project is unchanged.

**Demonstrating value before full institutional ingest**

Reviewers and trainees need to see a working tool, not a plan, before the full UCSF archive is online.

**What changed:** The public Hub, diagnosis browse, and board-lecture search shipped early to show resident and board relevance while Phase 1 institutional work continues.

### 6. Future Goals and Plan for Project Completion

**Phase 1 — UCSF ingest and baseline evaluation (second half of award year)**

1. Complete bulk ingest of the UCSF Pathology teaching library (videos/slides; didactic content only).
2. Obtain IRB approval and administer the baseline pre-use survey with UCSF trainees.
3. Continue adding PathCast / board-review lectures so the Hub stays useful for exam-oriented study.

**Phase 2 — Testing and follow-up evaluation**

4. Trainee testing of the Hub with departmental content online.
5. Administer the post-use survey (confidence, speed of finding answers, use of teaching videos).
6. Document limitations and prepare materials for the final report.

**Phase 3 — Dissemination**

7. Prepare a manuscript for *Academic Pathology* and/or an informatics education abstract, with Society of ’67 acknowledgment.
8. Longer-term (future funding, not required to finish this grant): extend toward a tutor-like system that reasons across sources—not search alone.

### 7. Update to timeline, if any

Building the integrated Hub—browse, search, lecture timestamps, and cited answers—took longer than the original one-year plan assumed for a cytopathology-only demo.

Evaluation was therefore sequenced **after** the build milestone rather than running in parallel with early prototyping. IRB submission and the baseline trainee survey are the immediate next steps, followed by UCSF internal ingest and post-use testing.

The **project end date is unchanged.** Completing UCSF internal ingestion, both surveys, and the write-up remains the priority for the remainder of the award year.

### 8. End Date of Project
[Exact date from award letter]

### 9. Journal you plan to submit a manuscript to
*Academic Pathology* (AAPath). Possible secondary: education/informatics meeting abstract.

### 10. Status of budget

[Amount spent / remaining — from UCSF grants administrator.]  
First installment received for departmental processing; remaining funds requested with this mid-term report, per Society of ’67 terms. Spending supports transcription, search infrastructure, and hosting needed for the educational tool.

### 11. Applicant Information

- **Name:** Charles Herndon, DO  
- **Degree(s):** DO  
- **Academic Level:** Resident Physician, PGY-[__]  
- **Program/Institution:** Anatomic Pathology Residency, UCSF  
- **Email:** Charlie.Herndon@ucsf.edu  

### 12. Faculty advisor / check address

- **Faculty Advisor:** Ronald Balassanian, MD — **same**  
- **Check / department address:** **same** (as on acceptance / ATF), unless grants office updates it  

---

## Short “ABPath / resident” blurb (optional if they ask)

The Hub is aimed at pathology residents: it organizes material the way trainees study for boards, links questions to trusted sources with citations, and opens teaching videos at the exact discussion of a diagnosis—supporting just-in-time learning during real case work and board preparation.
