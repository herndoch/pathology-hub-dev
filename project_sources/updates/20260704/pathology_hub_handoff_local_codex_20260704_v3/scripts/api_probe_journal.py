#!/usr/bin/env python3
import argparse, json, os, sys, requests
try:
    from dotenv import load_dotenv
    load_dotenv()
except Exception:
    pass

parser=argparse.ArgumentParser(description='Probe Pathology Hub journal API and optionally require a journal in results.')
parser.add_argument('--query', required=True)
parser.add_argument('--require-journal', default='')
parser.add_argument('--max-results', type=int, default=10)
parser.add_argument('--base', default=os.getenv('PATHOLOGY_HUB_API_BASE','https://pathology-hub-v04-vorn5q2kga-uc.a.run.app'))
args=parser.parse_args()
key=os.getenv('PATHOLOGY_HUB_API_KEY') or os.getenv('HUB_API') or os.getenv('X_API_KEY')
if not key:
    sys.exit('Missing PATHOLOGY_HUB_API_KEY/HUB_API/X_API_KEY')
headers={'X-API-Key': key}
health=requests.get(args.base.rstrip()+'/health', timeout=60)
print('HEALTH', health.status_code)
print(health.text[:1500])
payload={'query':args.query,'sources':['journals'],'max_results':args.max_results,'compact':True,'excerpt_char_limit':1200}
r=requests.post(args.base.rstrip()+'/evidence/search', headers=headers, json=payload, timeout=120)
print('SEARCH', r.status_code)
try:
    data=r.json()
except Exception:
    print(r.text[:5000]); sys.exit(2)
print(json.dumps(data, indent=2)[:8000])
results=data.get('journal_results') or []
if args.require_journal:
    hits=[]
    for x in results:
        vals=[x.get('journal'), x.get('source_name'), x.get('source'), x.get('title')]
        if any(args.require_journal.lower() in str(v or '').lower() for v in vals):
            hits.append(x)
    print('REQUIRED_JOURNAL_HITS', len(hits))
    if not hits:
        sys.exit(3)
