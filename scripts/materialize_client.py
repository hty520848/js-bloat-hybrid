#!/usr/bin/env python3
"""Build an owned, closed client cache; measured targets are binding placeholders."""
import argparse,json,os,shutil,subprocess,sys
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def write(p,x):p.parent.mkdir(parents=True,exist_ok=True);p.write_text(json.dumps(x,indent=2)+'\n')
def main():
 p=argparse.ArgumentParser();p.add_argument('--source',required=True);p.add_argument('--destination',required=True);p.add_argument('--library',required=True);p.add_argument('--version',required=True);p.add_argument('--node',required=True);p.add_argument('--plan',required=True);a=p.parse_args()
 source=Path(a.source).resolve();dest=Path(a.destination).absolute();plan=Path(a.plan)
 assert R/'artifacts' in dest.parents and not dest.exists() and not dest.is_symlink()
 spec=plan.with_suffix('.spec.json');write(spec,{'source':str(source),'library':a.library,'version':a.version,'output':str(plan)})
 subprocess.run([a.node,str(R/'scripts/plan_client.js'),str(spec)],check=True)
 data=json.loads(plan.read_text());dest.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run(['cp','--reflink=auto','-a',str(source),str(dest)],check=True)
 def owned(p):
  p=Path(p).absolute();assert dest in p.parents;return p
 def remove(p):
  p=owned(p)
  parent=p.parent.resolve();assert parent==dest or dest in parent.parents,'Parent link escapes private cache'
  if p.is_symlink():p.unlink()
  elif p.is_dir():shutil.rmtree(str(p))
  elif p.exists():p.unlink()
 def symlink(p,target):
  p=owned(p);target=(dest/target).absolute();assert target==dest or dest in target.parents
  remove(p);p.parent.mkdir(parents=True,exist_ok=True);p.symlink_to(os.path.relpath(str(target),str(p.parent)))
 for row in data['packages']:
  target=dest/row['dest'];target.mkdir(parents=True,exist_ok=False)
  if row['binding']:continue
  for q in Path(row['source']).iterdir():
   if q.name in ['node_modules','.git']:continue
   d=target/q.name
   if q.is_symlink():
    real=q.resolve()
    if real.is_file():shutil.copy2(str(real),str(d))
    elif real.is_dir():subprocess.run(['cp','--reflink=auto','-aL',str(real),str(d)],check=True)
   elif q.is_dir():shutil.copytree(str(q),str(d),symlinks=True)
   else:shutil.copy2(str(q),str(d))
  for edge in row['edges']:symlink(target/'node_modules'/edge['name'],edge['target'])
 for link in data['links']:
  q=dest/link['path']
  if 'externalAsset' in link:
   remove(q);q.parent.mkdir(parents=True,exist_ok=True);subprocess.run(['cp','--reflink=auto','-aL',link['externalAsset'],str(q)],check=True)
  else:symlink(q,link['target'])
 for rel in data['bindings']:
  q=dest/rel;remove(q);q.mkdir(parents=True)
  write(q/'package.json',{'name':a.library,'version':a.version,'private':True,'description':'Binding placeholder; never execute before replacing with the frozen official target.'})
  write(q/'HYBRID_BINDING_PLACEHOLDER.json',{'library':a.library,'version':a.version})
 # Reject every surviving external/dangling-to-external link, including links
 # inside an uncommon vendor subtree, before this cache can enter qualification.
 unsafe=[]
 for dp,dn,fn in os.walk(str(dest),followlinks=False):
  dn[:]=[d for d in dn if d!='.git']
  for n in dn+fn:
   q=Path(dp)/n
   if q.is_symlink():
    try:t=q.resolve()
    except RuntimeError:unsafe.append(str(q));continue
    if os.path.isabs(os.readlink(str(q))) or not (t==dest or dest in t.parents):unsafe.append(str(q))
 if unsafe:write(plan.with_suffix('.unsafe.json'),unsafe);raise ValueError('Unclosed client links: '+str(len(unsafe)))
 write(plan.with_suffix('.materialized.json'),{'root':str(dest),'bindings':data['bindings'],'links':len(data['links']),'externalPackages':len(data['packages']),'unresolvedDeclaredDependencies':data['missing']})
 print(json.dumps({'status':'materialized','root':str(dest),'bindings':len(data['bindings'])}))
if __name__=='__main__':main()
