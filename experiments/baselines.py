"""Pinned native baselines on a pure deployment, with separate complete tests.

Qualifying adapters does not resample the existing primary RQ tables. Native
dependency/file removals do not provide source-position function predictions.
"""
import os,re,json,shutil,tarfile,time,traceback
from pathlib import Path
from .common import ROOT,read,write,sha,clone,snapshot,same,completed

def cohort(root,scope):
 return {f:{'bytes':(Path(root)/f).stat().st_size,'sha256':sha(Path(root)/f)} for f in scope['files'] if (Path(root)/f).is_file()}

def harness(c,lib,q,deployment,tag):
 """Graft only nondeployment material; never restore removed production data."""
 dest=clone(deployment,c.work/'external-validation'/tag);before=snapshot(dest,include_all=True)
 ref=next(x for x in c.manifest if x['library']==lib)
 with tarfile.open(str(ROOT/'artifacts/npm'/ref['archive']),'r:gz') as t:
  published={m.name.split('/',1)[1] for m in t.getmembers() if m.isfile()}
 prefixes=[x['path'] for x in read(q['scope'])['dependencies']]
 def protected(rel):return rel in published or any(rel==p or rel.startswith(p+'/') for p in prefixes)
 source=Path(q['root'])
 # Test tools must have their own dependency closure. A removed production
 # package can also have been hoisted for Jest/Babel; sharing that path makes
 # the test runner fail before it exercises the transformed application.
 providers=None
 if (source/'node_modules').is_dir():
  providers=c.work/'unit-test-providers'/lib/'node_modules'
  if not providers.exists():clone(source/'node_modules',providers)
 for dp,dn,fn in os.walk(str(source),followlinks=False):
  dn[:]=[d for d in dn if d not in ['.git','coverage','.nyc_output','__pycache__'] and (Path(dp)/d)!=source/'node_modules' and not protected((Path(dp)/d).relative_to(source).as_posix())]
  for name in dn+fn:
   p=Path(dp)/name;rel=p.relative_to(source).as_posix();out=dest/rel
   if protected(rel) or out.exists() or out.is_symlink():continue
   if p.is_symlink():
    actual=p.resolve();assert actual==source or source in actual.parents,'External test-provider link'
    out.parent.mkdir(parents=True,exist_ok=True);out.symlink_to(os.path.relpath(str(dest/actual.relative_to(source)),str(out.parent)))
   elif p.is_file():out.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(str(p),str(out))
 after=snapshot(dest,include_all=True)
 assert all(after.get(f)==h for f,h in before.items()),'Harness changed transformed deployment bytes'
 # Check absence as well as bytes. No deleted published or dependency path may
 # reappear when test-only providers are added.
 for f in published:
  if not (Path(deployment)/f).exists():assert not (dest/f).exists(),f
 for prefix in prefixes:
  if not (Path(deployment)/prefix).exists():assert not (dest/prefix).exists(),prefix
 provider_links=[]
 if providers:
  # Webpack's loader resolver does not consult NODE_PATH. Expose only
  # nonproduction tool names through links to this Context's private tools.
  # A removed production path stays absent and Node fallback stays guarded.
  entries=[]
  for p in providers.iterdir():
   if p.name.startswith('@') and p.is_dir():entries.extend(p.iterdir())
   elif not p.name.startswith('.'):entries.append(p)
  for p in entries:
   rel='node_modules/'+p.relative_to(providers).as_posix();out=dest/rel
   if protected(rel) or out.exists() or out.is_symlink():continue
   assert c.work.resolve() in p.resolve().parents
   out.parent.mkdir(parents=True,exist_ok=True);out.symlink_to(os.path.relpath(str(p),str(out.parent)))
   provider_links.append({'path':rel,'privateTool':str(p)})
 if not hasattr(c,'harnesses'):c.harnesses={}
 c.harnesses[str(dest)]={'environment':{'NODE_PATH':''},'timeoutSeconds':c.protocol['testTimeoutSeconds'],'scope':'Full unit suite; original published/dependency paths cannot be restored','deploymentBoundaries':[dict(q['dependencyBoundary'],root=str(dest))],'recoveryHelpers':getattr(c,'recovery_helpers',{}).get(str(Path(deployment)),[])}
 if providers:
  c.harnesses[str(dest)]['testProviderModules']=str(providers)
 write(c.out/'harnesses'/(tag+'.json'),c.harnesses[str(dest)])
 write(c.out/'external-baselines'/(tag+'-graft.json'),{'originalDeployment':str(deployment),'validationRoot':str(dest),'deploymentSnapshot':before,'productionUnchangedByGraft':True,'privateTestProviderLinks':provider_links})
 return dest

def tool(c,name):
 cfg=c.machine['externalBaselines'][name];source=Path(cfg['root']);expected=read(cfg['manifest'])
 assert snapshot(source,include_all=True)==expected,'External tool input hash mismatch'
 c.inputSnapshots[str(source)]=expected;c.inputSnapshotAlgorithms[str(source)]=True
 return clone(source,c.work/'external-tools'/name)

def mininode(c,lib,q,mode,tools):
 source=clone(q['deployment'],c.work/'external-inputs'/('mininode-'+mode)/lib);dest=c.work/'external-output'/('mininode-'+mode)/lib;dest.parent.mkdir(parents=True)
 assert all(not (Path(dp)/n).is_symlink() for dp,dn,fn in os.walk(str(source)) for n in dn+fn),'Native analysis requires physical dependencies'
 allowed=json.dumps([str(c.work)])
 stage=c.run('external-mininode-'+mode+'-'+lib,[c.machine['nodeStatic'],'--require',ROOT/'scripts/harness/fs_guard.js',tools['mininode']/'src/index.js',source,'--mode='+mode,'--destination='+str(dest),'--silent'],tools['mininode']/'src',{'NODE_PATH':'','SQJ_ALLOWED_WRITE_ROOTS':allowed},timeout=600)
 return {'transform':stage,'target':str(dest),'validOutput':stage['exitCode']==0 and (dest/'package.json').is_file(),'granularity':'native file/function removal; no function-position Accuracy mapping'}

def depp(c,lib,q,tools):
 # strace profiles unchanged complete core tests. Only dependency paths from
 # the frozen production closure are eligible; test providers are excluded.
 trace_root=harness(c,lib,q,q['deployment'],'depp-trace-'+lib);trace=c.out/'external-baselines'/(lib+'-strace.log')
 stage=c.run('external-depp-trace-'+lib,['strace','-f','-e','trace=open,openat','-o',str(trace)]+q['command'],trace_root,timeout=c.protocol.get('profileTimeoutByLibrary',{}).get(lib,c.protocol['profileTimeoutSeconds']))
 out={'trace':stage,'traceSameCompleteSuite':same(q['original'],stage),'granularity':'native production dependency removal; function-position Accuracy unavailable'}
 if not out['traceSameCompleteSuite']:return dict(out,validOutput=False)
 sandbox=c.work/'depp-metadata'/lib;pg=sandbox/'Playground'/lib;pg.mkdir(parents=True)
 shutil.copy2(str(Path(q['deployment'])/'package.json'),str(pg/'package.json'));shutil.copy2(str(Path(q['deployment'])/'package-lock.json'),str(pg/'package-lock.json'))
 original=read(pg/'package-lock.json')
 out['nativeLockStage']=c.run('external-depp-native-lock-'+lib,['python3',tools['DepPrune']/'identify_runtime_from_lock.py',lib,'Playground'],sandbox)
 if 'packages' not in original:
  sandbox=c.work/'depp-adapted-metadata'/lib;pg=sandbox/'Playground'/lib;pg.mkdir(parents=True)
  shutil.copy2(str(Path(q['deployment'])/'package.json'),str(pg/'package.json'))
  packages={'':{'name':lib}}
  for dep in read(q['scope'])['dependencies']:packages[dep['path']]={'name':dep['name'],'version':dep['version']}
  write(pg/'package-lock.json',{'name':lib,'lockfileVersion':2,'packages':packages})
  out.update(lockAdapter='packages table from exact frozen installed production closure; no version resolution or reinstall',adapterLockStage=c.run('external-depp-adapted-lock-'+lib,['python3',tools['DepPrune']/'identify_runtime_from_lock.py',lib,'Playground'],sandbox))
 else:
  # The native helper includes every non-dev lock entry. Supply a separate
  # projection when the authenticated test lock also records test providers.
  actual={x['path'] for x in read(q['scope'])['dependencies']};native=set((pg/'runtime_deps.txt').read_text().splitlines())
  if native!=actual:
   sandbox=c.work/'depp-projected-metadata'/lib;pg=sandbox/'Playground'/lib;pg.mkdir(parents=True)
   shutil.copy2(str(Path(q['deployment'])/'package.json'),str(pg/'package.json'));write(pg/'package-lock.json',{'lockfileVersion':2,'packages':dict({'':original.get('packages',{}).get('',{})},**{x:original['packages'][x] for x in sorted(actual)})})
   out.update(lockAdapter='Exact production closure projected from authenticated lock; native output retained',adapterLockStage=c.run('external-depp-projected-lock-'+lib,['python3',tools['DepPrune']/'identify_runtime_from_lock.py',lib,'Playground'],sandbox))
 opened=set();relative=[]
 for line in trace.read_text(errors='replace').splitlines():
  match=re.search(r'open(?:at)?\([^\"]*\"([^\"]+)\"',line)
  if not match:continue
  name=match.group(1)
  if not name.endswith(('.js','.json')):continue
  if not name.startswith('/'):relative.append(name);name=str(trace_root/name)
  if name.startswith(str(trace_root)+'/'):opened.add(name)
 (pg/'npm_test_opened_files.txt').write_text('\n'.join(sorted(opened))+'\n')
 detection=c.run('external-depp-candidates-'+lib,['python3',tools['DepPrune']/'extract_bloated_candidates.py',lib,'Playground'],sandbox);out.update(detection=detection,relativeOpenPaths=sorted(set(relative)),traceSha256=sha(trace))
 if detection['exitCode']:return dict(out,validOutput=False)
 candidates=(pg/'unreachable_os_all.txt').read_text().splitlines();eligible={x['path'] for x in read(q['scope'])['dependencies']};assert set(candidates)<=eligible,'Candidate outside production closure'
 dest=clone(q['deployment'],c.work/'external-output/depp'/lib);removed=[];removal_start=time.monotonic()
 for rel in sorted(candidates,key=lambda n:len(Path(n).parts),reverse=True):
  p=dest/rel;assert p.resolve()==p and dest in p.parents and rel.startswith('node_modules/')
  if p.is_dir():shutil.rmtree(str(p));removed.append(rel)
 return dict(out,target=str(dest),validOutput=True,candidateDependencies=candidates,removedDependencies=removed,removalSeconds=time.monotonic()-removal_start)

def run(c,methods):
 rows=[];tools={}
 if any(m.startswith('mininode-') for m in methods):tools['mininode']=tool(c,'mininode')
 if 'depp' in methods:tools['DepPrune']=tool(c,'DepPrune')
 for lib,q in sorted(c.qualified.items()):
  # Adapter control is necessary to distinguish harness defects from native
  # reduction failures. It is not a primary-table timing observation.
  control=harness(c,lib,q,q['deployment'],'original-'+lib);control_stage=c.run('external-control-'+lib,q['command'],control)
  for method in methods:
   row={'library':lib,'method':method,'originalControl':control_stage,'primaryExperimentResampled':False};rows.append(row)
   try:
    if not same(q['original'],control_stage):row.update(status='blocked-original-adapter-control');continue
    out=depp(c,lib,q,tools) if method=='depp' else mininode(c,lib,q,method.split('-',1)[1],tools);row.update(out)
    if not out['validOutput']:row.update(status='native-tool-or-trace-failed');continue
    tested=harness(c,lib,q,out['target'],method+'-'+lib);core=c.run('external-core-'+method+'-'+lib,q['command'],tested)
    before=cohort(q['deployment'],read(q['scope']));after=cohort(out['target'],read(q['scope']));a=sum(x['bytes'] for x in before.values());b=sum(x['bytes'] for x in after.values())
    row.update(status='validated' if same(control_stage,core) else 'transformed-full-suite-failed',core=core,validCore=same(control_stage,core),originalCohortBytes=a,transformedCohortBytes=b,cohortReductionPercent=100*(1-b/a),missingOriginalFiles=sorted(set(before)-set(after)),functionAccuracy=None,timingScope='Single adapter qualification; no primary RQ3/RQ4 timing inference')
    write(c.out/'external-baselines'/(method+'-'+lib+'-before.json'),before);write(c.out/'external-baselines'/(method+'-'+lib+'-after.json'),after)
   except Exception:row.update(status='adapter-exception',error=traceback.format_exc())
   finally:write(c.out/'external-baselines/results.json',rows)
 c.record['stages'].append({'name':'external-baseline-adapters','status':'passed' if rows and all(r.get('status')=='validated' for r in rows) else 'completed-with-failures','rows':len(rows)});c.save();return rows
