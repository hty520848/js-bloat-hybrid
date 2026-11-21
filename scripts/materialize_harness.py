#!/usr/bin/env python3
"""Apply a resolved harness plan only within an explicitly named new private root."""
import argparse,json,subprocess,hashlib
from pathlib import Path
def main():
 p=argparse.ArgumentParser();p.add_argument('plan');p.add_argument('--private-root',required=True);a=p.parse_args()
 root=Path(a.private_root).resolve();plan=json.loads(Path(a.plan).read_text());assert not plan['missing'],plan['missing']
 records=[];seen=set()
 for item in plan['rows']:
  source=Path(item['source']).resolve();dest=Path(item['dest']).absolute();resolved=dest.resolve()
  assert root in resolved.parents,'Destination escapes private root'
  if str(dest) in seen:continue
  seen.add(str(dest))
  if dest.exists():
   # Existing root provider was copied from the same source. Never overwrite
   # a different package version silently.
   s=json.loads((source/'package.json').read_text());d=json.loads((dest/'package.json').read_text());assert (s['name'],s['version'])==(d['name'],d['version'])
  else:
   dest.parent.mkdir(parents=True,exist_ok=True);subprocess.run(['cp','--reflink=auto','-aL',str(source),str(dest)],check=True)
  records.append(item)
 Path(a.plan).with_suffix('.materialized.json').write_text(json.dumps(records,indent=2)+'\n')
 print('Materialized',len(records),'private harness package instances')
if __name__=='__main__':main()
