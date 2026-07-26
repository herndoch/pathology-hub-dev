# ExpertPath / WHO comparison report — review10 (v0.2)

**Date:** 2026-07-24 (re-comparison after pipeline fixes / redeploy)  
**Sessions used:** existing logged-in Chrome tabs (ExpertPath as C Hendon; WHO BlueBooksOnline) — no fresh/incognito browser, no agent-initiated login.  
**Our pages:** live Cloud Run review URLs; Critic pass present on all 10 (`verdict: revise` on all).  
**Primary reference:** ExpertPath. **Secondary:** WHO Blue Books (dedicated page only).  
**Baseline:** [`docs/EXPERTPATH_WHO_COMPARISON_REPORT_review10_v0_1.md`](EXPERTPATH_WHO_COMPARISON_REPORT_review10_v0_1.md) (0/10 comparable).

**Rebuild status observed from live HTML `generated` timestamps:**
- **Rebuilt (~15:49–15:53Z):** Adenoid cystic, Secretory carcinoma, Prostatic acinar, DLBCL, Melanoma, Colon arising-in-adenoma
- **Unchanged from v0.1 (~04:21–04:24Z):** Pleomorphic adenoma, DCIS, Clear cell RCC, Lipoma

---

## 1. Pleomorphic Adenoma

**Our page:** ⚠️ Same page as v0.1 — correct organ/sections; PLAG1/HMGA2 still absent from Essential; Critic `revise`.
**ExpertPath found:** yes — *Pleomorphic Adenoma, Salivary Gland* (~74 images).
**WHO dedicated page found:** yes — Head and Neck Tumours → Pleomorphic adenoma.
**vs v0.1:** unchanged — identical `generated` timestamp / byte size; no rebuild applied.

Missing essential criteria:
- PLAG1 / HMGA2 rearrangements still not in Essential (EP/WHO definitional molecular)
- Capsule site differences and CEPA transform risk framing still thin
- Benign metastasizing PA still Critic-flagged

Missing DDx entities:
- Carcinoma ex-PA, AdCC (vs cellular PA), polymorphous adenocarcinoma, EMC / myoepithelial carcinoma, intercalated duct adenoma (EP list still broader)

Factual errors / entity conflation: none major in prose

Off-organ content found: none

Figure quality: On-entity PA gallery (primary/recurrent, cut surface, encapsulation); no wrong-entity contamination detected. Still not feature-mapped at ExpertPath density.

Depth verdict: adequate

---

## 2. Adenoid Cystic Carcinoma

**Our page:** ⚠️ Major content/gallery cleanup — biphasic + basement-membrane matrix + MYB::NFIB/MYBL1::NFIB now in **Essential**; pattern/PNI/HGT figures on-topic; Critic `revise` (DDx completeness).
**ExpertPath found:** yes — *Adenoid Cystic Carcinoma* (~85 images); biphasic + MYB confirmed; HPV-related multiphenotypic sinonasal in DDx.
**WHO dedicated page found:** yes — Head and Neck Tumours → Adenoid cystic carcinoma.
**vs v0.1:** improved — cystadenoma gallery contamination cleared; molecular moved into Essential; body regenerated (`15:50Z`, 32 figures).

Missing essential criteria:
- High-grade transformation called out more as a figure than as Essential text
- Prognostic molecular associations (NOTCH1, 1p36, TP53) still absent (depth, not definitional core)

Missing DDx entities:
- HPV-related multiphenotypic sinonasal carcinoma (EP top DDx — still absent)
- Basaloid squamous cell carcinoma, hyalinizing clear cell carcinoma, polymorphous adenocarcinoma (EP broader)
- Critic also wants sialoblastoma / EMC emphasized (they appear in our DDx text; Critic may be stale vs draft)

Factual errors / entity conflation: none material in current prose/gallery (cystadenoma conflation from v0.1 resolved in captions)

Off-organ content found: none in gallery (cystadenoma string still appears in evidence-card tail, not as index figures)

Figure quality: **Clean relative to v0.1** — tubular / cribriform / solid / PNI / HGT / clear myoepithelial cells. No cystadenoma index figures. Good feature labeling.

Depth verdict: adequate

---

## 3. Secretory Carcinoma (salivary gland)

**Our page:** ⚠️ ETV6::NTRK3 + mammaglobin/S100/SOX10 + p63/p40/DOG1− now in **Essential**; thyroid-SC figure gone; Critic `revise` (microsecretory figure conflation).
**ExpertPath found:** yes — *Secretory Carcinoma, Salivary Gland* (~41 images); Microsecretory adenocarcinoma is an EP DDx entity.
**WHO dedicated page found:** yes — Head and Neck Tumours → Secretory carcinoma.
**vs v0.1:** improved — thyroid off-site figure removed; ETV6 promoted to Essential; gallery mostly on-entity (`15:51Z`, 27 figures).

Missing essential criteria:
- Alternate non-NTRK3 fusions (ETV6::RET etc.) / pan-TRK context still thin
- Otherwise definitional molecular/IHC now present

Missing DDx entities:
- **Microsecretory adenocarcinoma** — present as a gallery caption (#10) but **not listed in our DDx section** (EP lists it)
- Microcribriform adenocarcinoma, intraductal carcinoma (EP)

Factual errors / entity conflation:
- Critic: microsecretory adenocarcinoma figure treated as index-entity content (should be clearly DDx-labeled if kept)

Off-organ content found: none (thyroid-SC contamination cleared; only a weak “thyroid differentiation marker” desirable line remains — acceptable)

Figure quality: Mostly excellent on-entity (circumscription, microcysts, secretions, S100/p63). **One wrong-role figure:** “Microsecretory adenocarcinoma” appears as gallery item #10 without DDx framing — residual contamination pattern (milder than v0.1 thyroid).

Depth verdict: adequate

---

## 4. Ductal Carcinoma In Situ (DCIS), breast

**Our page:** ⚠️ Same as v0.1 — architectures present; Essential still wrongly elevates imaging microcalcifications; myoepithelium wording still weak; Critic `revise`.
**ExpertPath found:** yes — dedicated *Ductal Carcinoma In Situ* (~84 images).
**WHO dedicated page found:** yes — Breast Tumours → Ductal carcinoma in situ.
**vs v0.1:** unchanged — not in rebuilt set.

Missing essential criteria:
- Intact myoepithelium / confinement to ductal-lobular system still not cleanly Essential
- Nuclear grade / comedonecrosis significance still Desirable-ish
- ER/HER2 phenotype patterns still absent

Missing DDx entities:
- UDH, ADH, collagenous spherulosis, radiation atypia (EP) still absent
- Ours still mainly LCIS / microinvasive / Paget

Factual errors / entity conflation:
- Microcalcifications as Essential diagnostic criterion remains incorrect framing

Off-organ content found: none

Figure quality: On-topic cribriform/papillary grade examples; no wrong-entity contamination. Still far below EP image depth.

Depth verdict: adequate

---

## 5. Clear Cell RCC

**Our page:** ⚠️ Same as v0.1 — VHL/clear-cell story OK, but Essential still misses CA9/vasculature precision; **gallery still polluted**; Critic `revise`.
**ExpertPath found:** yes — main Genitourinary *Clear Cell Renal Cell Carcinoma* (~55 images).
**WHO dedicated page found:** yes — Urinary and Male Genital Tumours → Clear cell renal cell carcinoma.
**vs v0.1:** unchanged — not rebuilt; PEComa/CDC/CCSK figure issues persist.

Missing essential criteria:
- Delicate branching vasculature + CA9 box-like staining still not Essential
- PBRM1/BAP1/SETD2 / ISUP nucleolar grade still absent

Missing DDx entities:
- MiT/TFE translocation RCC, ELOC-mutated RCC, TSC-associated RCC, adrenal cortical tumors (EP)

Factual errors / entity conflation:
- Critic still flags collecting duct carcinoma association
- Gallery still includes PEComa, collecting duct carcinoma, clear cell sarcoma of kidney

Off-organ content found:
- Clear cell sarcoma of kidney / PEComa figures remain

Figure quality: **Still contaminated (main remaining v0.1-class defect among unrebuilt pages)** — PEComa caption explicitly present; Critic lists CDC/CCSK figures.

Depth verdict: adequate

---

## 6. Prostatic Acinar Adenocarcinoma

**Our page:** ⚠️ Gleason/Grade Groups + basal-loss/AMACR now in **Essential**; Skene figures cleared from gallery; DDx still skewed to rare entities and **ASAP still absent**; Critic `revise`.
**ExpertPath found:** yes — *Acinar Adenocarcinoma* (~134 images); Gleason/Grade Groups confirmed; **ASAP is first DDx**.
**WHO dedicated page found:** yes — Urinary and Male Genital Tumours → Prostatic acinar adenocarcinoma.
**vs v0.1:** improved — Gleason essential + Skene off-organ gallery removed (`15:49Z`, 16 figures). DDx quality still weak.

Missing essential criteria:
- ASAP / benign-mimic workup not Essential (and ASAP not even in DDx)
- Pathognomonic helpful features (collagenous micronodules etc.) still underplayed vs EP
- TMPRSS2-ERG / PTEN molecular Key-Fact level still thin

Missing DDx entities:
- **Atypical small acinar proliferation (ASAP)** — critical EP miss
- Common benign mimics (atrophy, adenosis/AHAP, seminal vesicle, Cowper, etc.)
- Ours still lists prostatic cystadenoma, stromal sarcoma, **Skene gland adenocarcinoma** in DDx text (Skene is off-organ DDx — should not be primary teaching DDx)

Factual errors / entity conflation:
- Critic flags adenoid cystic/basal cell, adenosquamous, squamous as inappropriate DDx emphasis
- Skene still in DDx prose (figures gone, text remains)

Off-organ content found:
- Skene gland adenocarcinoma remains in **DDx text** (not gallery) — residual off-organ teaching content

Figure quality: **Much improved** — prostatectomy, EPE, SVI, glomerulations, nucleoli, PNI; **0 Skene gallery captions**. Fewer figures (16) than EP (134).

Depth verdict: adequate

---

## 7. Diffuse Large B Cell Lymphoma, NOS

**Our page:** ⚠️ Hans GCB vs ABC + mature B-cell phenotype now in **Essential**; double-hit exclusion framed in Key Facts; Critic `revise`.
**ExpertPath found:** yes (partial) — HN/Waldeyer-oriented DLBCL NOS page still the practical hit; WHO has full NOS chapter page.
**WHO dedicated page found:** yes — Haematolymphoid Tumours → Diffuse large B-cell lymphoma NOS.
**vs v0.1:** improved — Hans/COO essential; less pyothorax skew; gallery looks on-entity (`15:52Z`, 33 figures).

Missing essential criteria:
- Explicit rule-out of high-grade B-cell lymphoma with MYC+BCL2/BCL6 rearrangements could be Essential (currently desirable “absence of rearrangements” — still slightly muddled)
- Otherwise core NOS criteria much better

Missing DDx entities:
- Burkitt lymphoma, lymphoblastic lymphoma, classic Hodgkin / grey-zone depth still thin
- Critic wants high-grade B-cell lymphoma NOS / EBV+ DLBCL more prominent (they appear in our DDx text)

Factual errors / entity conflation:
- Critic notes PTCL-NOS attribution awkwardness — minor

Off-organ content found: none

Figure quality: On-entity cytology/site variants (tonsil, ileum, CNS, bone, CD20); no wrong-entity gallery contamination detected.

Depth verdict: adequate

---

## 8. Lipoma (soft tissue)

**Our page:** ⚠️ Same as v0.1 — mature fat + MDM2 exclusion present; Critic still flags myolipoma figure conflation.
**ExpertPath found:** yes — *Lipoma* (~29 images).
**WHO dedicated page found:** yes — Soft Tissue and Bone Tumours → Lipoma.
**vs v0.1:** unchanged — not rebuilt.

Missing essential criteria:
- 12q13-15 / HMGA2 cytogenetics still not Essential
- MDM2 absence remains Desirable rather than Essential for deep lesions

Missing DDx entities:
- Dysplastic lipoma / atypical spindle cell lipomatous tumor; myxoid liposarcoma vs myxolipoma (EP)

Factual errors / entity conflation:
- Critic: myolipoma pictures under Lipoma

Off-organ content found: none

Figure quality: Mostly mature adipocyte / intramuscular lipoma images; Critic still reports myolipoma contamination (not obvious in top-10 captions — may be deeper gallery/evidence). Residual risk.

Depth verdict: adequate

---

## 9. Melanoma, invasive, overview/NOS (skin)

**Our page:** ❌ Still thin Essential criteria; Breslow in Key Facts only; Critic flags **conjunctival melanoma figures** as off-organ.
**ExpertPath found:** yes (partial) — subtype pages only; spot-check baseline remains Melanoma, Nodular Type / related invasive subtypes (no NOS overview).
**WHO dedicated page found:** yes (pathway/subtype pages; no single Melanoma NOS) — e.g. Low-CSD melanoma / SSM.
**vs v0.1:** improved slightly — page regenerated (`15:53Z`); metastatic-to-skin added to DDx; PRAME appears in some captions — but conjunctival off-organ figures remain, depth still shallow.

Missing essential criteria:
- Structured malignancy-vs-nevus checklist (maturation failure, deep mitoses, pagetoid scatter, asymmetry)
- Breslow / ulceration / mitoses as staging essentials (mitoses/ulceration still Desirable)
- Pathway-based overview framing (low-CSD / high-CSD / acral / desmoplastic) still weak for an NOS leaf
- PRAME/p16 interpretive use not Essential

Missing DDx entities:
- Spitz / atypical Spitz, deep penetrating nevus, cellular blue nevus, AFX/sarcoma mimics still thin
- Nodular melanoma listed as DDx of “melanoma overview” remains odd

Factual errors / entity conflation:
- Conjunctival melanoma figures mixed into skin NOS page (Critic)

Off-organ content found:
- **Conjunctival melanoma figures** (Critic + page text mentions)

Figure quality: Mix of useful subtype overview images (SSM, nodular, acral, LMM, desmoplastic) plus **off-site conjunctival melanoma contamination** — fails the zero off-organ target.

Depth verdict: shallow

---

## 10. Colonic Adenocarcinoma arising in adenoma

**Our page:** ⚠️ Malignant-polyp framing restored — pT1 invasion, **Haggitt**, **Kikuchi/Kudo**, **pseudoinvasion DDx** present; adenosquamous gallery gone; Critic `revise` (odd MSI essential bullet + figure-feature binding).
**ExpertPath found:** yes — dedicated *Adenoma With Invasive Carcinoma* (~10 images); Haggitt + Kikuchi/Kudo + pseudoinvasion confirmed.
**WHO dedicated page found:** **no** — separate adenoma vs colorectal adenocarcinoma pages only (not substituted).
**vs v0.1:** improved — largest turnaround; regenerated (`15:51Z`); Essential systems present; gallery no longer adenosquamous-dominated.

Missing essential criteria:
- High-risk histology bundle (poor diff, LVI, margin distance, high-grade budding, poorly differentiated clusters, deep Sm invasion) incomplete vs EP checklist
- “Villous adenocarcinoma demonstrates microsatellite instability” as Essential is overstated/odd (Critic also flags)
- Colitis cystica profunda still absent from DDx

Missing DDx entities:
- Localized colitis cystica profunda (EP)
- Ours has non-invasive adenoma, pseudoinvasion, lymphoglandular-complex-like CRC — better focus than v0.1

Factual errors / entity conflation:
- MSI-universal claim for villous adenocarcinoma is not a sound Essential criterion
- Evidence-card tail may still mention adenosquamous/gastroblastoma (not in top gallery captions)

Off-organ content found: none in current top gallery captions

Figure quality: **Much improved** — low/high power, dirty necrosis, cribriforming, desmoplasia, LVI, poorly differentiated adenocarcinoma. Not clearly showing Haggitt levels or classic pseudoinvasion side-by-side (feature-binding gap), but **no adenosquamous index contamination**.

Depth verdict: adequate

---

## Summary

- **Comparable to ExpertPath: 0 / 10** (v0.1 was 0/10) — still none match ExpertPath depth/image density, but several crossed from shallow → adequate.
- **Adequate:** Pleomorphic Adenoma, Adenoid Cystic Carcinoma, Secretory Carcinoma, DCIS, Clear Cell RCC, Prostatic Acinar Adenocarcinoma, DLBCL NOS, Lipoma, Colonic adenocarcinoma arising in adenoma (**9**)
- **Shallow:** Melanoma invasive overview/NOS (**1**)
- **Most improved since v0.1:**
  1. **Colonic adenocarcinoma arising in adenoma** — Haggitt/Kikuchi/pseudoinvasion + adenosquamous gallery cleared
  2. **Adenoid cystic carcinoma** — MYB/biphasic Essential + cystadenoma figures cleared
  3. **Secretory carcinoma** — ETV6 Essential + thyroid figure cleared (tie with **Prostatic acinar** Gleason Essential + Skene gallery cleared)
- **Still worst:**
  1. **Melanoma overview/NOS** — only remaining shallow; conjunctival off-organ figures
  2. **Clear cell RCC** — unrebuilt; PEComa/CDC/CCSK gallery contamination persists
  3. **Prostatic acinar adenocarcinoma** — content systems fixed, but ASAP/benign-mimic DDx still missing and Skene remains in DDx text
- **Recurring patterns:**
  - **Figure pipeline fixes worked where rebuilds ran** (ACC/Secretory/Prostate/Colon galleries largely cleaned).
  - **Unrebuilt pages retain v0.1 figure defects** (CCRCC PEComa/CDC/CCSK; Lipoma myolipoma Critic flag; PA/DCIS unchanged).
  - **Essential molecular/grading promotion largely succeeded** on rebuilt leaves (MYB, ETV6, Gleason, Haggitt/Kikuchi, Hans).
  - **DDx quality still lags ExpertPath** (ASAP, HPV multiphenotypic sinonasal Ca, microsecretory adenocarcinoma as named DDx, UDH/ADH).
  - **Critic remains `revise` on all 10** — useful for flags, not a pass/fail depth gate.
  - **Zero “comparable”** still blocked by thin bodies vs EP image/reference density and incomplete practical DDx.
  - New residual contamination mode: **DDx-entity images without DDx labeling** (Secretory ← microsecretory) and **off-organ subtype bleed** (Melanoma ← conjunctival).

**Suggested next actions:**
1. Rebuild unrebuilt contaminated pages: **Clear cell RCC**, **Lipoma** (myolipoma filter), optionally PA/DCIS for PLAG1/HMGA2 + myoepithelium Essential.
2. Melanoma NOS: ban conjunctival/mucosal figures; add pathway overview essentials + nevus-vs-melanoma checklist.
3. Prostate: inject ASAP + common benign mimics; remove Skene from DDx text.
4. Secretory: keep microsecretory only as explicitly labeled DDx figure; add it to DDx list.
5. ACC: add HPV-related multiphenotypic sinonasal carcinoma to DDx.
6. Re-run v0.3 aiming for ≥1 comparable candidate (Colon or ACC/Secretory) and **zero** off-organ/wrong-entity index figures across all 10.
