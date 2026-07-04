# Regression Tests and QA

Use working key under header `X-API-Key`.

## Standard proof payloads

```json
{"query":"melanoma invasive overview","sources":["lectures"],"max_results":5,"compact":true,"excerpt_char_limit":900}
```

```json
{"query":"ovarian high grade serous carcinoma p53 BRCA","sources":["who","textbooks","pathout","journals"],"max_results":5,"compact":true,"excerpt_char_limit":900}
```

```json
{"query":"prostate adenocarcinoma cribriform pattern 4","sources":["textbooks","pathout"],"max_results":5,"compact":true,"excerpt_char_limit":900}
```

Expected status 200 and forbidden tag count 0.
