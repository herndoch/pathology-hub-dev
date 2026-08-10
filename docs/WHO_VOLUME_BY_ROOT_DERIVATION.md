# WHO_VOLUME_BY_ROOT derivation (2026-08-03)

`WHO_VOLUME_BY_ROOT` in `frontend/pathology_hub_chat_mvp/static/app.js` maps each Browse root
to its dominant WHO Classification of Tumours 5th-edition volume number, used to disambiguate
entity names that appear in `who_genetic_syndromes_links_v0_1.json` under more than one volume
(432 of 2,175 normalized names — ~20% — are ambiguous across volumes; e.g. "Osteoma" is a
distinct chapter in at least 3 different volumes).

## Method

For every current browse-index leaf, normalize the tag's last segment the same way as
`normalizeSyndromeName()` in `app.js`, look up every `{volume, url}` candidate for that name in
`who_genetic_syndromes_links_v0_1.json`, and tally volume-number hits per browse root. The
volume with the highest hit count per root is almost always an unambiguous, large plurality —
consistent with each root corresponding to one (or a small, related handful of) real WHO 5th
edition volume(s).

## Measured counts (top 3 volumes per root, `node` one-off against the live browse index)

```
bst                 -> [ [ '33', 110 ], [ '44', 42 ], [ '51', 32 ] ]
breast              -> [ [ '32', 57 ],  [ '52', 17 ], [ '65', 12 ] ]
cyto                -> [ [ '51', 61 ],  [ '33', 55 ], [ '52', 47 ] ]   # no clean dominant volume — cytopathology cross-cuts every organ system
skin                -> [ [ '64', 127 ], [ '33', 40 ], [ '65', 34 ] ]
endo                -> [ [ '53', 54 ],  [ '52', 12 ], [ '44', 10 ] ]
eye_orbit           -> [ [ '65', 93 ],  [ '64', 28 ], [ '52', 25 ] ]
forensic            -> []                                              # not a WHO-covered domain
gi                  -> [ [ '31', 75 ],  [ '44', 17 ], [ '52', 16 ] ]
gu                  -> [ [ '36', 55 ],  [ '34', 16 ], [ '52', 16 ] ]
gyn                 -> [ [ '34', 195 ], [ '44', 25 ], [ '52', 16 ] ]
hn                  -> [ [ '52', 182 ], [ '44', 28 ], [ '33', 26 ] ]
heme                -> [ [ '63', 51 ],  [ '64', 14 ], [ '49', 8 ] ]
molecular           -> []                                              # not a WHO-covered domain
neuro               -> [ [ '44', 39 ],  [ '64', 11 ], [ '52', 10 ] ]
peds                -> [ [ '44', 156 ], [ '33', 48 ], [ '52', 39 ] ]
thorax_mediastinum  -> [ [ '35', 88 ],  [ '48', 7 ],  [ '34', 6 ] ]
```

## Resulting mapping (`WHO_VOLUME_BY_ROOT` in app.js)

| Root | Volume | Inferred WHO 5th-ed. volume |
|---|---|---|
| bst | 33 | Soft Tissue and Bone Tumours |
| breast | 32 | Breast Tumours |
| skin | 64 | Skin Tumours |
| endo | 53 | Endocrine and Neuroendocrine Tumours |
| eye_orbit | 65 | Eye Tumours |
| gi | 31 | Digestive System Tumours |
| gu | 36 | Urinary and Male Genital Tumours |
| gyn | 34 | Female Genital Tumours |
| hn | 52 | Head and Neck Tumours |
| heme | 63 | Haematolymphoid Tumours |
| peds | 44 | Paediatric Tumours |
| thorax_mediastinum | 35 | Thoracic Tumours |
| neuro | 44 | Shared plurality with `peds` (many CNS entities are pediatric-heavy) — tentative, lowest-confidence entry in this table |
| cyto, forensic, molecular | (none) | No clean dominant volume / not WHO-covered; ambiguous names for these roots fall back to the first parsed candidate |

## Known limitation

This is a name-frequency heuristic, not a verified volume-number-to-title mapping obtained from
WHO/IARC directly. If a future WHO Classification volume list becomes available, replace this
table with a verified one rather than re-deriving it from browse-leaf overlap.
