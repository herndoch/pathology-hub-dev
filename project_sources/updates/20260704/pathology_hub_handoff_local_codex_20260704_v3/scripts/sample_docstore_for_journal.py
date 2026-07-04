#!/usr/bin/env python3
import argparse, subprocess, tempfile, pathlib, json, itertools
parser=argparse.ArgumentParser()
parser.add_argument('--journal', required=True)
parser.add_argument('--docstore', default='gs://pathology_hub/03_indexes/journals/vector/journal_vector_docstore.jsonl')
parser.add_argument('--max', type=int, default=20)
args=parser.parse_args()
with tempfile.TemporaryDirectory() as td:
    p=pathlib.Path(td)/'docstore.jsonl'
    subprocess.run(['gcloud','storage','cp',args.docstore,str(p)], check=True)
    hits=[]
    with open(p,encoding='utf-8',errors='replace') as f:
        for line in f:
            try: r=json.loads(line)
            except Exception: continue
            vals=[r.get('journal'), r.get('source_name'), r.get('source')]
            if any(args.journal.lower() in str(v or '').lower() for v in vals):
                hits.append({k:r.get(k) for k in ['title','journal','source_name','doi','url','article_id','chunk_id','section']})
                if len(hits)>=args.max: break
print(json.dumps(hits, indent=2))
