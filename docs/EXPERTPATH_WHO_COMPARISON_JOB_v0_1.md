# Job: compare our topic pages against ExpertPath/WHO (paste into the GUI-enabled agent)

You have a working browser with active logins to **ExpertPath** and **WHO Blue Books**
(tumourclassification.iarc.who.int). Use those sessions — do not open a fresh
Playwright/incognito browser, and do not try to log in yourself.

## Task

For each of the 10 entities below, do ALL of the following, then produce ONE
consolidated markdown comparison report (format specified at the bottom).

### Entities (label — our live review URL)

1. Pleomorphic Adenoma — https://pathology-hub-chat-mvp-vorn5q2kga-uc.a.run.app/review/topic?tag=HN::Salivary_Gland::Benign_Tumor::Pleomorphic_Adenoma
2. Adenoid Cystic Carcinoma — https://pathology-hub-chat-mvp-vorn5q2kga-uc.a.run.app/review/topic?tag=HN::Salivary_Gland::Malignant_Tumor::Adenoid_Cystic_Carcinoma
3. Secretory Carcinoma (salivary gland) — https://pathology-hub-chat-mvp-vorn5q2kga-uc.a.run.app/review/topic?tag=HN::Salivary_Gland::Malignant_Tumor::Secretory_Carcinoma
4. Ductal Carcinoma In Situ (DCIS), breast — https://pathology-hub-chat-mvp-vorn5q2kga-uc.a.run.app/review/topic?tag=Breast::Neoplastic::Epithelial::In_Situ::Ductal_Carcinoma_In_Situ_DCIS
5. Clear Cell RCC — https://pathology-hub-chat-mvp-vorn5q2kga-uc.a.run.app/review/topic?tag=GU::Kidney::Renal_cell::Clear_Cell_RCC
6. Prostatic Acinar Adenocarcinoma — https://pathology-hub-chat-mvp-vorn5q2kga-uc.a.run.app/review/topic?tag=GU::Prostate::Glandular_neoplasms::Prostatic_Acinar_Adenocarcinoma
7. Diffuse Large B Cell Lymphoma, NOS — https://pathology-hub-chat-mvp-vorn5q2kga-uc.a.run.app/review/topic?tag=Heme::Mature_B_Cell::Large_B_Cell::Diffuse_Large_B_Cell_Lymphoma_NOS
8. Lipoma (soft tissue) — https://pathology-hub-chat-mvp-vorn5q2kga-uc.a.run.app/review/topic?tag=BST::Soft_TissueAdipocytic::Lipoma
9. Melanoma, invasive, overview/NOS (skin) — https://pathology-hub-chat-mvp-vorn5q2kga-uc.a.run.app/review/topic?tag=Skin::Neoplastic::Melanocytic::Malignant::Melanoma_Invasive_Overview_NOS
10. Colonic Adenocarcinoma arising in adenoma — https://pathology-hub-chat-mvp-vorn5q2kga-uc.a.run.app/review/topic?tag=GI::Colon::Neoplastic::Adenocarcinoma::Colonic_Adenocarcinoma_Arising_In_Adenoma

### Per-entity steps

1. **Open our page first.** Fetch/open the review URL above. Note its section headers,
   approximate length, number of figures shown, and whether a "Critic pass" panel is
   present (it will show a verdict + any flagged issues — note the verdict and issue count).
2. **Open the matching ExpertPath page** (search the entity name under the matching
   organ/category — e.g. Head and Neck > Salivary Glands for #1-3). Screenshot the
   full page. Note its section headers and read through Key Facts, Terminology,
   Etiology/Pathogenesis, Clinical Issues, Macroscopic, Microscopic, Ancillary Tests,
   Differential Diagnosis, and the "Selected Images" gallery.
3. **Open the matching WHO Blue Books entity** if a dedicated page exists for that
   exact entity (search within the correct organ chapter). If NO dedicated WHO page
   exists for this exact entity (e.g. only a related/malignant-transformation entity
   exists), say so explicitly — do not substitute a different entity's WHO content.
4. **Compare** our page against ExpertPath (primary reference) and WHO (secondary,
   when it exists) using this checklist:
   - Missing essential diagnostic criteria present in ExpertPath/WHO but absent in ours
   - Missing DDx entities ExpertPath/WHO lists that ours omits
   - Any factual errors or entity conflation in our page (a fact attributed to the
     wrong entity)
   - Any content in our page about a different organ/site than this entity (should be
     zero — flag immediately if found)
   - Figure quality/relevance: do our embedded/gallery images actually illustrate a
     named histologic feature, or are they generic/off-topic/low-resolution?
   - Overall depth verdict: **shallow** / **adequate** / **comparable to ExpertPath**

## Output format (one file, all 10 entities)

For each entity, output exactly this block:

```
## <N>. <Entity label>

**Our page:** <verdict emoji ✅/⚠️/❌> <one-line summary>
**ExpertPath found:** yes/no — <notes>
**WHO dedicated page found:** yes/no — <notes>

Missing essential criteria: <list or "none">
Missing DDx entities: <list or "none">
Factual errors / entity conflation: <list or "none">
Off-organ content found: <list or "none">
Figure quality: <one line>
Depth verdict: shallow / adequate / comparable to ExpertPath
```

After all 10, add a final `## Summary` section: how many of the 10 are
"comparable to ExpertPath", which 2-3 entities need the most work, and any
pattern you noticed across multiple entities (e.g. a recurring missing section,
a recurring bad figure type).

Paste that full report back into the other chat (the one working on
`pathology-hub-dev`, branch `cursor/topic-prebuild-review10-9231`) so it can act
on the findings.
