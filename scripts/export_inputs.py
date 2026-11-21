#!/usr/bin/env python3
"""Export admitted and blocked inputs alike; no credentials or experiment results."""
import argparse,hashlib,json,os,tarfile
from pathlib import Path
R=Path(__file__).resolve().parents[1]
def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for b in iter(lambda:f.read(1024*1024),b''):h.update(b)
 return h.hexdigest()
def main():
 p=argparse.ArgumentParser();p.add_argument('--output',required=True);p.add_argument('--include-runtimes',action='store_true');a=p.parse_args();out=Path(a.output).absolute();assert not out.exists()
 m=json.loads((R/'config/machine.local.json').read_text());mapping={};roots=[]
 for lib,q in m['targets'].items():roots.append((Path(q['root']),'targets/'+lib))
 roots.extend([(Path(m['staticNodeModules']),'tools/static/node_modules'),(Path(m['transformerNodeModules']),'tools/transformer/node_modules')])
 if (R/'artifacts/npm').is_dir():roots.append((R/'artifacts/npm','npm'))
 if m.get('harnessRoot'):roots.append((Path(m['harnessRoot']),'harness'))
 for name,cfg in m.get('externalBaselines',{}).items():
  roots.extend([(Path(cfg['root']),'external/'+name+'/source'),(Path(cfg['manifest']),'external/'+name+'/source-sha256.json')])
 for lib,clients in m.get('clients',{}).items():
  for client in clients:
   roots.append((Path(client['root']),'clients/'+lib+'/'+client['directory']))
   # Current immutable client manifests are input identities. Historical
   # source plans/logs remain provenance references and are not active paths.
   if client.get('sourceManifest'):roots.append((Path(client['sourceManifest']),'client-manifests/'+lib+'/'+client['directory']+'.json'))
 if a.include_runtimes:
  roots.extend([(Path(m['nodeTest']).parent.parent,'runtimes/node-test'),(Path(m['nodeStatic']).parent.parent,'runtimes/node-static'),(Path(m['graalNode']).parent.parent,'runtimes/graal')])
 for source,target in roots:
  mapping[str(source.absolute())]='{INPUTS}/'+target
  mapping[str(source.resolve())]='{INPUTS}/'+target
 mapping[str(R)]='{PACKAGE}'
 def remap(value):
  if isinstance(value,str):
   for s,t in sorted(mapping.items(),key=lambda x:-len(x[0])):value=value.replace(s,t)
   return value
  if isinstance(value,list):return [remap(v) for v in value]
  if isinstance(value,dict):return {k:remap(v) for k,v in value.items()}
  return value
 portable=remap(m);portable['bundleNote']='Prepared targets and client binding placeholders include both eligible and blocked inputs. This bundle carries no qualification certificate or experiment results. Run fresh preparation after import; use --unit-evidence-run to select that new evidence.'
 # A recipient has no access to this machine's protected legacy checkout.
 portable['protectedLegacyRoots']=[]
 config=out.with_name(out.name+'.machine.json');assert not config.exists();config.parent.mkdir(parents=True,exist_ok=True);config.write_text(json.dumps(portable,indent=2)+'\n')
 out.parent.mkdir(parents=True,exist_ok=True)
 with tarfile.open(str(out),'w:gz',compresslevel=3) as tar:
  for source,target in roots:
   print('ADD '+target,flush=True);tar.add(str(source.resolve()),arcname=target)
  tar.add(str(config),arcname='portable-machine.json')
 report={'archive':out.name,'bytes':out.stat().st_size,'sha256':sha(out),'includesRuntimes':a.include_runtimes,'targets':sorted(m['targets']),'clients':sum(len(v) for v in m.get('clients',{}).values()),'sourceRootCount':len(roots),'notAQualificationCertificate':True}
 manifest=out.with_name(out.name+'.manifest.json');assert not manifest.exists();manifest.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
