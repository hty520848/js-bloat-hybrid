"""Deployment copies exclude the library's borrowed unit-test providers."""
import json,shutil,tarfile,os
from pathlib import Path
from .common import ROOT,read,write,sha
def copy_package(source,dest):
 source,dest=Path(source),Path(dest);dest.mkdir(parents=True,exist_ok=True)
 for p in source.iterdir():
  if p.name in ['node_modules','.git']:continue
  q=dest/p.name
  if q.exists() or q.is_symlink():continue
  if p.is_symlink():raise ValueError('Production package is not physical: '+str(p))
  if p.is_dir():shutil.copytree(str(p),str(q),symlinks=False)
  else:shutil.copy2(str(p),str(q))
def materialize(c,lib,q):
 root=c.work/'deployments'/lib;assert not root.exists();root.mkdir(parents=True)
 ref=next(x for x in c.manifest if x['library']==lib);archive=ROOT/'artifacts/npm'/ref['archive'];assert sha(archive)==ref['sha256']
 with tarfile.open(str(archive),'r:gz') as tar:
  for m in tar.getmembers():
   if not m.isfile():continue
   rel=m.name.split('/',1)[1];p=root/rel;assert root in p.resolve().parents;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(tar.extractfile(m).read());p.chmod(m.mode)
 scope=read(q['scope'])
 for item in sorted(scope['dependencies'],key=lambda x:len(Path(x['path']).parts)):copy_package(q['root']/item['path'],root/item['path'])
 shutil.copy2(str(q['root']/'package-lock.json'),str(root/'package-lock.json'))
 bad=[f for f,h in scope['hashes'].items() if not (root/f).is_file() or sha(root/f)!=h];assert not bad,bad
 truth=c.work/'truth-deployments'/lib;shutil.copytree(str(root),str(truth),symlinks=False)
 unit_truth=Path(q['unitTruthRoot']);manifest=read(q['functions'])
 for item in manifest['files']:
  expected=item.get('instrumentedSha256',item['sha256']);source=unit_truth/item['file'];assert sha(source)==expected
  shutil.copy2(str(source),str(truth/item['file']))
 q.update(deployment=str(root),truthDeployment=str(truth))
 packages=[{'path':'','dependencies':sorted(read(q['root']/'package.json').get('dependencies',{}))}]
 for item in scope['dependencies']:
  packages.append({'path':item['path'],'dependencies':sorted(read(q['root']/item['path']/'package.json').get('dependencies',{}))})
 q['dependencyBoundary']={'files':scope['files'],'packages':packages}
 write(c.out/'inputs'/(lib+'-deployment.json'),{'root':str(root),'truthRoot':str(truth),'scopeSha256':sha(q['scope']),'validatedJSFiles':len(scope['files']),'borrowedUnitTestProvidersIncluded':False})
 return q
