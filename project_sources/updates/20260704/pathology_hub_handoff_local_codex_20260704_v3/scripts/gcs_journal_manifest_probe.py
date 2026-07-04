#!/usr/bin/env python3
import json, subprocess, tempfile, pathlib, os, sys
GCS='gs://pathology_hub/03_indexes/journals/vector/journal_vector_manifest.json'
with tempfile.TemporaryDirectory() as td:
    p=pathlib.Path(td)/'journal_vector_manifest.json'
    subprocess.run(['gcloud','storage','cp',GCS,str(p)], check=True)
    m=json.loads(p.read_text())
print(json.dumps({
    'schema_version':m.get('schema_version'),
    'created_at_utc':m.get('created_at_utc'),
    'record_count':m.get('record_count'),
    'article_count':m.get('article_count'),
    'journal_counts':m.get('journal_counts'),
    'checks':m.get('checks'),
    'artifact_paths':m.get('artifact_paths')
}, indent=2))
