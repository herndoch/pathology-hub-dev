#!/usr/bin/env python3
import json, subprocess, tempfile, pathlib, collections, argparse
parser=argparse.ArgumentParser()
parser.add_argument('--chunks', default='gs://pathology_hub/02_normalized/journals_batches/histopathology/journal_chunks.jsonl')
parser.add_argument('--articles', default='gs://pathology_hub/02_normalized/journals_batches/histopathology/journal_articles.jsonl')
args=parser.parse_args()
def cp(uri, path): subprocess.run(['gcloud','storage','cp',uri,str(path)], check=True)
def iter_jsonl(path):
    with open(path,encoding='utf-8',errors='replace') as f:
        for line in f:
            line=line.strip()
            if line:
                try: yield json.loads(line)
                except Exception: pass
with tempfile.TemporaryDirectory() as td:
    td=pathlib.Path(td); chunks=td/'chunks.jsonl'; articles=td/'articles.jsonl'
    cp(args.chunks,chunks); cp(args.articles,articles)
    crows=list(iter_jsonl(chunks)); arows=list(iter_jsonl(articles))
    journals=collections.Counter(str(r.get('journal') or r.get('source_name') or r.get('source') or '') for r in crows)
    dois=set(str(r.get('doi') or '').lower() for r in crows if r.get('doi'))
    titles=set(str(r.get('title') or '').strip().lower() for r in crows if r.get('title'))
print(json.dumps({'chunk_rows':len(crows),'article_rows':len(arows),'journal_counts':journals,'unique_doi_count':len(dois),'unique_title_count':len(titles),'chunk_fields_sample':list(crows[0].keys()) if crows else []}, indent=2, default=dict))
