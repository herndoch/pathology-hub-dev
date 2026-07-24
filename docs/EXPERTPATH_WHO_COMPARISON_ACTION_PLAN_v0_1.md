# Action plan from ExpertPath/WHO comparison report (review10)

**Source report:** `docs/EXPERTPATH_WHO_COMPARISON_REPORT_review10_v0_1.md`  
**Branch:** `cursor/topic-prebuild-review10-9231`

## Findings summary

- **0/10** pages rated comparable to ExpertPath; **4 adequate**, **6 shallow**
- **Top systemic defect:** figure pipeline pollution (wrong-entity galleries)
- **Second defect:** Essential criteria too morphologic; molecular/grading systems demoted

## Implemented in this iteration

1. **Figure hardening** (`pathology_backend.py`)
   - Removed `_pathout_deep_verified` bypass in entity matching
   - Re-run entity filter after PathOutlines deep enrichment
   - Per-page confusable-entity blocklists (cystadenoma→ACC, Skene→prostate, etc.)
   - Site-context exclusions (e.g. thyroid figures on salivary pages)
   - Skip deep-index enrichment for PathOutlines URLs whose entity does not match the leaf

2. **Essential-criteria guidance** (`prompts.py`, `topic_page_essential_hints()`)
   - Prompt now requires definitional molecular, Gleason/Haggitt/Hans systems in Essential
   - Per-leaf hints for review10 shallow entities

## Rebuild queue (shallow pages)

1. Colonic adenocarcinoma arising in adenoma
2. Prostatic acinar adenocarcinoma
3. Adenoid cystic carcinoma (+ Secretory carcinoma tie)
4. DLBCL NOS
5. Melanoma invasive overview/NOS

## Success criteria for re-review

- Zero off-organ / wrong-entity figures in gallery
- Essential criteria include definitional molecular or grading systems when evidence supports
- Depth verdict ≥ adequate on previously shallow pages
