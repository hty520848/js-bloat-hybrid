#!/usr/bin/env python3
"""Offline prepublication structural audit. Does not certify experiment success."""
import ast,hashlib,json,re,sys,argparse,os
from pathlib import Path
from import_inputs import digest
R=Path(__file__).resolve().parents[1]
def main():
 parser=argparse.ArgumentParser();parser.add_argument('--output');parser.add_argument('--source-only',action='store_true',help='Allow unstaged external archives');args=parser.parse_args()
 errors=[];files=[]
 public=[]
 for directory,subdirs,names in os.walk(str(R),followlinks=False):
  subdirs[:]=[name for name in subdirs if name not in ['.git','artifacts','work','runs','evidence','node_modules','__pycache__']]
  public.extend(Path(directory)/name for name in names)
 for p in public:
  if not p.is_file() or any(x in p.parts for x in ['.git','artifacts','work','runs','evidence','node_modules','__pycache__']) or p.name in ['machine.local.json','machine.frozen.json','package-audit.json','code-archive.json','SHA256SUMS.txt'] or p.relative_to(R).as_posix()=='docs/reviewer-comments-zh.md':continue
  files.append(p)
  if p.suffix=='.py':
   try:ast.parse(p.read_text(encoding='utf-8'))
   except Exception as e:errors.append(str(p.relative_to(R))+': '+str(e))
  if p.suffix in ['.py','.js','.cjs','.mjs','.json','.md']:
   s=p.read_text(encoding='utf-8')
   if re.search(r'(?i)(?:password|passwd)\s*[:=]\s*[\"\x27][^\"\x27]{4,}',s):errors.append('Possible embedded credential: '+str(p.relative_to(R)))
 libs=json.loads((R/'datasets/manifests/libraries.json').read_text());client_manifest=json.loads((R/'datasets/manifests/clients.json').read_text());clients=client_manifest['libraries'];static=json.loads((R/'datasets/manifests/static-benchmark.json').read_text())
 roster=json.loads((R/'datasets/manifests/client-roster.json').read_text())['clients']
 identities=[(library,row['directory']) for library,rows in clients.items() for row in rows]
 roster_ids=[(row['library'],row['directory']) for row in roster]
 if len(libs)!=10 or set(x['library'] for x in libs)!=set(clients):errors.append('Incorrect ten-library manifest')
 if len(identities)!=50 or any(len(rows)!=5 for rows in clients.values()) or len(set(identities))!=50:errors.append('Client cohort must contain five distinct bindings for each of ten libraries')
 if len(roster_ids)!=len(set(roster_ids)) or set(roster_ids)!=set(identities):errors.append('Planned roster and client manifest identities differ')
 if len(static['sources'])!=26:errors.append('Incomplete static corpus')
 hashes={p.relative_to(R).as_posix():digest(p) for p in files}
 external=[]
 inputs=json.loads((R/'manifest/inputs.json').read_text(encoding='utf-8'))
 for key,identity in inputs.items():
  if 'file' not in identity:continue
  path=(R/'manifest'/identity['file']).resolve()
  rel=path.relative_to(R).as_posix()
  if args.source_only and key not in ('codeqlModules','portableConfiguration') and not path.exists():
   external.append(rel)
   continue
  if hashes.get(rel)!=identity['sha256'] or path.stat().st_size!=identity['bytes']:
   errors.append('Input identity mismatch: '+rel)
 results=R/'results/paper'
 paper=json.loads((results/'index.json').read_text(encoding='utf-8'))['items']
 if {p.name for p in results.iterdir()}!={'index.json'}|{item['file'] for item in paper}:
  errors.append('Unexpected file in selected paper results')
 for item in paper:
  if hashes.get('results/paper/'+item['file'])!=item['sha256']:
   errors.append('Paper result identity mismatch: '+item['file'])
 report={'status':'passed' if not errors else 'failed','auditScope':'Input and manuscript-result identity, cohort, and Python syntax','sourceOnly':args.source_only,'unstagedExternalInputs':external,'files':len(files),'libraries':len(libs),'clients':len(identities),'staticPrograms':len(static['sources']),'paperItems':len(paper),'errors':errors,'fileSha256':hashes}
 dest=Path(args.output) if args.output else R/'provenance/package-audit.json';dest.parent.mkdir(parents=True,exist_ok=True);dest.write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
 print(json.dumps({k:v for k,v in report.items() if k!='fileSha256'},ensure_ascii=False));return 0 if not errors else 1
if __name__=='__main__':sys.exit(main())
