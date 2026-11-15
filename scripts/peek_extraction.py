"""Show the entities and relations extracted for one paper.
Usage: python scripts/peek_extraction.py [paper_id]   (random extracted paper if no id)
"""
import sys

from open_intelligence.database import postgres

SQL = ("SELECT p.paper_id, p.title, e.entities, e.relations, e.seconds "
       "FROM paper_extractions e JOIN papers p ON p.paper_id = e.paper_id WHERE e.status = 'done'")

with postgres.connect() as conn:
    if len(sys.argv) > 1:
        row = conn.execute(SQL + " AND p.paper_id = %s", (int(sys.argv[1]),)).fetchone()
    else:
        row = conn.execute(SQL + " ORDER BY random() LIMIT 1").fetchone()

if not row:
    sys.exit("no extracted paper found")

paper_id, title, entities, relations, seconds = row
print(f"paper {paper_id}: {title}  ({seconds:.0f}s)\n")
print("entities:")
for e in entities:
    print(f"  {e['type']:8} {e['role']:9} {e['name']}")
print("\nrelations:")
for r in relations:
    print(f"  {r['source']}  --{r['relation']}-->  {r['target']}")