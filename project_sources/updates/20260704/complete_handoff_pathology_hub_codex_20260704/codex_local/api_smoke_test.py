"""Pathology Hub API smoke test.
Usage: export PATHOLOGY_HUB_API_KEY="..."; python api_smoke_test.py
"""
import os, json, requests
BASE = os.environ.get("PATHOLOGY_HUB_BASE", "https://pathology-hub-v04-vorn5q2kga-uc.a.run.app")
API_KEY = os.environ.get("PATHOLOGY_HUB_API_KEY")
if not API_KEY:
    raise SystemExit("Set PATHOLOGY_HUB_API_KEY to the working key value.")
FORBIDDEN = ["::Lectures::", "::Textbooks::", "Slide_", "Page_", "Digital_Pathology_Slide", "Pathology_Slide", "Benign_Cystic_Neck_Mass_Case_01", "::Error"]
def collect_tags(data):
    tags=[]
    if isinstance(data, dict):
        for k,v in data.items():
            if k.endswith("_results") and isinstance(v, list):
                for item in v:
                    if isinstance(item, dict) and item.get("primary_tag"):
                        tags.append(item["primary_tag"])
    return tags
payloads = [
    {"query":"melanoma invasive overview","sources":["lectures"],"max_results":5,"compact":True,"excerpt_char_limit":900},
    {"query":"ovarian high grade serous carcinoma p53 BRCA","sources":["who","textbooks","pathout","journals"],"max_results":5,"compact":True,"excerpt_char_limit":900},
    {"query":"prostate adenocarcinoma cribriform pattern 4","sources":["textbooks","pathout"],"max_results":5,"compact":True,"excerpt_char_limit":900},
]
print("Health", requests.get(f"{BASE}/health", timeout=60).status_code)
for p in payloads:
    r = requests.post(f"{BASE}/evidence/search", headers={"X-API-Key": API_KEY}, json=p, timeout=90)
    print(p["sources"], r.status_code)
    if r.status_code != 200:
        print(r.text[:500]); raise SystemExit(1)
    tags=collect_tags(r.json())
    bad=[t for t in tags if any(x in str(t) for x in FORBIDDEN)]
    print("  returned tags", len(tags), "forbidden", len(bad))
    if bad:
        print(json.dumps(bad, indent=2)); raise SystemExit(2)
print("OK")
