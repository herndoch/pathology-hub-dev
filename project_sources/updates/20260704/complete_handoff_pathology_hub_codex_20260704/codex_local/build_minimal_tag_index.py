import argparse, json, sqlite3
FORBIDDEN = ["::Lectures::", "::Textbooks::", "Slide_", "Page_", "Digital_Pathology_Slide", "Pathology_Slide", "Benign_Cystic_Neck_Mass_Case_01", "::Error"]
def iter_jsonl(path):
    with open(path, 'r', encoding='utf-8') as f:
        for line in f:
            line=line.strip()
            if line: yield json.loads(line)
def get_tag(row):
    tag = row.get('primary_tag_governed') or row.get('primary_tag')
    if not tag or tag == '__UNMAPPED__': return None
    if any(p in str(tag) for p in FORBIDDEN): return None
    return tag
def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--sqlite', required=True); ap.add_argument('--source-jsonl', action='append', nargs=2, metavar=('SOURCE','PATH'), required=True); args=ap.parse_args()
    db=sqlite3.connect(args.sqlite)
    db.executescript('''DROP TABLE IF EXISTS tag_records; CREATE TABLE tag_records (id INTEGER PRIMARY KEY, source TEXT, record_id TEXT, title TEXT, url TEXT, primary_tag TEXT, tag_root TEXT, text_excerpt TEXT, source_record_json TEXT); CREATE INDEX idx_tag_records_source ON tag_records(source); CREATE INDEX idx_tag_records_primary_tag ON tag_records(primary_tag); CREATE INDEX idx_tag_records_root ON tag_records(tag_root);''')
    n=0
    for source, path in args.source_jsonl:
        for row in iter_jsonl(path):
            tag=get_tag(row)
            if not tag: continue
            root=tag.split('::',1)[0]
            rid=str(row.get('id') or row.get('chunk_id') or row.get('page_id') or row.get('url') or n)
            title=str(row.get('title') or row.get('source_id') or row.get('lecture_id') or '')
            url=str(row.get('url') or row.get('source_url') or row.get('source_page_url') or row.get('video_url') or '')
            text=str(row.get('text') or row.get('excerpt') or row.get('content') or '')[:1200]
            db.execute('INSERT INTO tag_records(source,record_id,title,url,primary_tag,tag_root,text_excerpt,source_record_json) VALUES (?,?,?,?,?,?,?,?)', (source,rid,title,url,tag,root,text,json.dumps(row, ensure_ascii=False)))
            n+=1
    db.commit(); print('indexed records', n)
if __name__ == '__main__': main()
