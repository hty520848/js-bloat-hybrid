"""Source, scope, complete original suite and fresh independent-truth gates."""
import tarfile,shutil
from pathlib import Path
from .common import ROOT,read,write,sha,snapshot,clone,same
def run(c):
 rows=[];c.qualified={};expected={x['library']:x for x in c.manifest}
 for lib,ref in sorted(expected.items()):
  row={'library':lib,'version':ref['version'],'status':'checking'};rows.append(row)
  archive=ROOT/'artifacts/npm'/ref['archive'];row['archiveVerified']=archive.is_file() and sha(archive)==ref['sha256']
  cfg=c.machine.get('targets',{}).get(lib)
  if not row['archiveVerified'] or not cfg:
   row.update(status='blocked',reason='Missing verified release archive or prepared private dependency/test tree');continue
  root=Path(cfg['root']);before=snapshot(root);c.inputSnapshots[str(root)]=before
  row['inputManifestSha256']=sha_bytes(before)
  release={}
  with tarfile.open(str(archive),'r:gz') as tar:
   for m in tar.getmembers():
    if m.isfile():
     rel=m.name.split('/',1)[1];release[rel]=__import__('hashlib').sha256(tar.extractfile(m).read()).hexdigest()
  mismatch=[n for n,h in release.items() if not (root/n).is_file() or sha(root/n)!=h]
  row['releaseByteMismatches']=mismatch
  lock=root/'package-lock.json';row['dependencyLockVerified']=lock.is_file() and sha(lock)==cfg['dependencyLockSha256']
  if mismatch or not row['dependencyLockVerified']:
   row.update(status='blocked',reason='Release files or frozen lock do not match');continue
  own=sorted(n for n in release if n.endswith('.js'));allow=c.out/'inputs'/(lib+'-published.json');write(allow,own)
  scope=c.out/'inputs'/(lib+'-scope.json')
  row['scopeStage']=c.run('prepare-scope-'+lib,[c.machine['nodeTest'],ROOT/'src/metrics/scope.js',root,allow,scope],ROOT)
  if row['scopeStage']['exitCode']:
   row.update(status='blocked',reason='Production dependency or scope resolution failed');continue
  sc=read(scope);row['scopeSha256']=sha(scope);row['files']=len(sc['files'])
  control=clone(root,c.work/'controls'/lib);command=list(cfg['command'])
  timeout=c.protocol.get('targetTestCaseTimeoutMillis',{}).get(lib)
  if timeout and len(command)>1 and 'mocha' in command[1] and not any(arg.startswith('--timeout') for arg in command[2:]):
   command.insert(2,'--timeout='+str(timeout))
  row['originalCore']=c.run('prepare-core-'+lib,command,control)
  row['inputUnchanged']=before==snapshot(root)
  row['controlSourceUnchanged']=all((control/n).is_file() and sha(control/n)==h for n,h in sc['hashes'].items())
  original=row['originalCore']
  if not same(original,original) or not row['controlSourceUnchanged']:
   row.update(status='blocked',reason='Original complete suite failed, empty, or changed measured source');continue
  instrumented=clone(root,c.work/'truth'/lib)
  spec=c.out/'inputs'/(lib+'-truth-spec.json');manifest=c.out/'inputs'/(lib+'-functions.json')
  write(spec,{'root':str(instrumented),'scopeFiles':sc['files'],'variants':{},'instrument':True,'output':str(manifest)})
  row['truthInstrumentation']=c.run('prepare-truth-instrument-'+lib,[c.machine['nodeTest'],ROOT/'src/metrics/truth_manifest.js',spec],ROOT)
  if row['truthInstrumentation']['exitCode']:
   row.update(status='blocked',reason='Independent truth instrumentation failed');continue
  out=c.out/'truth'/lib
  row['truthCore']=c.run('prepare-truth-core-'+lib,command,instrumented,{'NODE_OPTIONS':'--require '+str(ROOT/'src/metrics/truth_preload.cjs'),'HYBRID_TRUTH_OUT':str(out)})
  hits=set()
  for p in out.glob('*.json'):hits.update(read(p)['hits'])
  universe={x['id'] for x in read(manifest)['functions']};row['exercisedProductionFunctions']=len(hits&universe)
  own={x['id'] for x in read(manifest)['functions'] if x['scope']=='library'};row['exercisedOwnFunctions']=len(hits&own)
  write(c.out/'truth'/(lib+'-core-hits.json'),sorted(hits))
  good=same(original,row['truthCore']) and bool(hits&own) and row['inputUnchanged']
  row.update(status='qualified-for-core-pilot' if good else 'blocked',reason=None if good else 'Instrumented suite incomplete or no production exercise')
  if good:c.qualified[lib]={'root':root,'command':command,'original':original,'allow':allow,'scope':scope,'functions':manifest,'coreHits':str(c.out/'truth'/(lib+'-core-hits.json')),'unitTruthRoot':str(instrumented)}
  write(c.out/'preparation.json',{'rows':rows,'formalReady':False})
 from .clients import qualify
 from .deployment import materialize
 for lib,q in sorted(c.qualified.items()):materialize(c,lib,q)
 client_rows=qualify(c);qualified_clients=sum(x['qualified'] for x in client_rows)
 from .clients import formal_ready
 ready=formal_ready(c,expected)
 record={'rows':rows,'qualifiedLibraries':sorted(c.qualified),'requiredLibraries':10,'qualifiedClientEntries':qualified_clients,'validClientTruthEntries':sum(len(v) for v in c.clients.values()),'formalReady':ready,'formalClientQuorum':c.protocol.get('formalClientQuorum',3),'formalCoverage':getattr(c,'formalCoverage',{}),'formalGaps':getattr(c,'formalGaps',[]),'reason':'Libraries must all qualify and every library must reach the stated client quorum. Valid zero-hit workloads remain coverage gaps and are skipped in method comparisons; failed originals are reported per library in formalGaps and are never counted as zero-hit clients. Historical truth cannot qualify new release bytes.'}
 c.record['preparation']=record;write(c.out/'preparation.json',record);c.record['stages'].append({'name':'prepare','status':'qualified-for-core-pilot' if c.qualified else 'blocked'});c.save()
def sha_bytes(x):return __import__('hashlib').sha256(__import__('json').dumps(x,sort_keys=True).encode()).hexdigest()
