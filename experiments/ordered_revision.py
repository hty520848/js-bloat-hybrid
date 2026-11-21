"""Missing-measurement revision runner with explicit cache certificates and RQ gates."""
import copy,hashlib,json,random,statistics,time,traceback
from pathlib import Path
from .common import ROOT,Context,read,write,sha,same,snapshot
from .admission import units
from .clients import reuse,comparison_eligible,bind
from .rq1 import run as own
from . import stubbifier_baselines as baseline,metrics

ARMS=['sscg','sdcg','mcg-only','nodeprof-only','hybrid']
METHODS=['sscg','sdcg','hybrid']
BASELINE_SOURCE=ROOT/'runs/val-cost-baselines-20261101-001'
CLIENT_INDEX=ROOT/'artifacts/revision-20261025b/consolidated-client-index-002.json'

def require(ok,message):
 if not ok:raise ValueError(message)

def runtime_for(proof,library):
 """A runtime change is scoped to its qualified library, never silently global."""
 return proof.get('runtimeByLibrary',{}).get(library,proof['runtime'])

def assert_stage(stage):
 require(stage and stage.get('exitCode')==0,'A source stage did not pass')
 require(sha(stage['log'])==stage['logSha256'],'A source log changed')

def dynamic_cache_paths(stage):
 label=stage['label'];require(bool(__import__('re').fullmatch(r'[A-Za-z0-9_.-]+',label)),'Unsafe producing-stage label')
 origin=Path(stage['log']).resolve().parent.parent
 require(ROOT/'runs' in origin.parents,'Dynamic cache producer is outside declared run storage')
 return origin/'rq1/dynamic'/(label+'-mapped.json'),origin/'rq1/dynamic'/(label+'.json.meta.json')

def setup(run_id,proof,clients=True,libraries=None):
 c=Context(run_id)
 effective=runtime_for(proof,libraries[0]) if libraries and len(libraries)==1 else proof['runtime']
 for name,x in effective.items():c.machine[name]=x['path']
 write(c.out/'runtime-by-library.json',{lib:runtime_for(proof,lib) for lib in proof['libraries']})
 c.machine['stubbifierBaselines']=read(BASELINE_SOURCE/'stubbifier-baselines/config.json')
 require(sha(ROOT/'src/baselines/stubbifier-recovery.ql')==c.machine['stubbifierBaselines']['querySha256'],'CodeQL query identity changed')
 if libraries:c.manifest=[r for r in c.manifest if r['library'] in libraries]
 units(c);require(len(c.qualified)==len(c.manifest),'Unit evidence failed identity validation')
 for lib,q in c.qualified.items():
  row=proof['libraries'][lib];require(row['sourceRoot']==str(q['root']),'Admission root differs: '+lib)
  require(read(q['scope'])['hashes']==row['sourceHashes'],'Admission source scope differs: '+lib)
 if clients:
  reuse(c,CLIENT_INDEX);index=read(CLIENT_INDEX)
  require(len(index['rows'])==57 and sum(bool(r.get('qualified')) for r in index['rows'])==43,'Frozen client roster changed')
  for lib,entries in c.clients.items():
   universe={f['id'] for f in read(c.qualified[lib]['functions'])['functions']}
   for client in entries:
    ref=next(r for r in index['rows'] if r['library']==lib and r['client']==client['name'])
    cfg=client['cfg'];require(cfg['inputManifestSha256']==ref['inputManifestSha256'],'Client identity mismatch')
    current=snapshot(cfg['root'],include_all=True)
    c.inputSnapshots[cfg['root']]=current;c.inputSnapshotAlgorithms[cfg['root']]=True
    frozen=hashlib.sha256(json.dumps(current,sort_keys=True).encode()).hexdigest()
    require(frozen==ref['inputManifestSha256'],'Frozen client files changed: '+client['name'])
    hits=set(read(client['hits']));require(not {v for v in hits-universe if not v.startswith('@file:')},'Unknown client truth IDs')
  require(sum(comparison_eligible(x) for rows in c.clients.values() for x in rows)==43,'Eligible roster is incomplete')
  write(c.out/'client-reuse.json',{'source':str(CLIENT_INDEX),'sha256':sha(CLIENT_INDEX),'rows':c.clientReuse,'workloadsExecuted':0})
 write(c.out/'effective-machine.json',c.machine);write(c.out/'runtime-admission.json',proof)
 return c

def cached_analyses(c,proof):
 results={};receipts=[]
 frozen=read(BASELINE_SOURCE/'executed-source-sha256.json')
 for p in ['src/baselines/stubbifier-recovery.ql','src/baselines/instrument_coverage.js','experiments/coverage_map.py']:
  require(frozen.get(p)==sha(ROOT/p),'Baseline analysis implementation changed: '+p)
 for lib,q in sorted(c.qualified.items()):
  sgpath=ROOT/'runs/formal-20261027-001/rq1/graphs'/('rq1-static-'+lib+'-mcg-only.json')
  prior=ROOT/'runs/formal-20261027-001';old=read(prior/'executed-source-sha256.json')
  compatible=sgpath.is_file() and read(prior/'inputs'/(lib+'-scope.json'))['hashes']==read(q['scope'])['hashes'] and all(sha(ROOT/p)==h for p,h in old.items() if p.startswith('src/static/') and p.endswith('.js'))
  if compatible:
   require(read(prior/'inputs'/(lib+'-scope.json'))['hashes']==read(q['scope'])['hashes'],'Static scope changed')
   assert_stage(read(prior/'commands'/('rq1-static-'+lib+'-mcg-only.json')))
   sg={'valid':True,'graph':str(sgpath),'reused':True,'graphSha256':sha(sgpath)}
  else:sg=own.static(c,lib,q,'mcg-only','rq1-static-'+lib)
  row=proof['libraries'][lib]
  if row.get('dynamic'):dg=copy.deepcopy(row['dynamic'])
  else:
   mapped,meta=dynamic_cache_paths(row['profiled'])
   require(mapped.is_file() and meta.is_file(),'A qualified dynamic graph is absent: '+lib)
   dg={'valid':True,'mapped':str(mapped),'metadata':read(meta),'stage':row['profiled']}
  require(dg['valid'] and not dg['metadata'].get('stackMismatches') and not dg['metadata'].get('remainingUserFrames'),'Dynamic graph failed qualification')
  assert_stage(dg['stage']);require(Path(dg['mapped']).is_file(),'Mapped graph absent')
  analyses={'mcg':sg,'dynamic':dg}
  for method in ['sscg','sdcg']:
   folder=BASELINE_SOURCE/'stubbifier-baselines'/method/lib;cert=read(folder/'qualification.json')
   require(cert['scopeSha256']==sha(q['scope']),'Baseline scope differs: '+lib+'/'+method)
   if method=='sscg':
    require(cert.get('databaseQualified') and cert.get('queryAndInventoryCompleted'),'Incomplete CodeQL certificate')
    analyses[method]={'valid':True,'graph':str(folder/'canonical.csv'),'emptyGraphCertificate':str(folder/'qualification.json') if cert.get('qualifiedEmptyGraph') else ''}
   else:
    require(not cert.get('unmappedFunctionIds'),'Unmapped Istanbul functions')
    stage=read(BASELINE_SOURCE/'commands'/('sdcg-profile-'+lib+'.json'));assert_stage(stage);require(same(q['original'],stage),'Cached Istanbul suite differs')
    analyses[method]={'valid':True,'coverage':str(folder/'coverage-final.json'),'coverageRoot':read(folder/'spec.json')['root']}
  results[lib]=analyses
  receipts.append({'library':lib,'MCG':sg,'NodeProf':{'graph':dg['mapped'],'sha256':sha(dg['mapped'])},'SSCG':{'file':analyses['sscg']['graph'],'sha256':sha(analyses['sscg']['graph'])},'SDCG':{'file':analyses['sdcg']['coverage'],'sha256':sha(analyses['sdcg']['coverage'])}})
 write(c.out/'analysis-reuse.json',receipts)
 return results

def build_one(c,lib,method,analyses,tag,instrument=False):
 q=c.qualified[lib];a=analyses[lib]
 if method in ['sscg','sdcg']:
  b=baseline.build(c,lib,q,method,a[method],tag,instrument=instrument);b['arm']=method
  require(b.get('valid'),'Transformed target suite failed: '+lib+'/'+method)
  spec=c.out/'rq1/manifests'/(tag+'-spec.json');manifest=spec.with_name(tag+'.json')
  write(spec,{'root':str(q['root']),'scopeFiles':read(q['scope'])['files'],'variants':{method:b['target']},'instrument':False,'output':str(manifest)})
  inventory=c.run(tag+'-manifest',[c.machine['nodeTest'],ROOT/'src/metrics/truth_manifest.js',spec],ROOT)
  require(inventory['exitCode']==0,'Baseline function inventory failed');b.update(manifest=str(manifest),inventory=inventory)
 else:b=own.build(c,lib,q,method,a['mcg'] if method!='nodeprof-only' else None,a['dynamic'],tag,instrument=instrument)
 require(b.get('valid'),'Build failed: '+lib+'/'+method)
 functions=read(b['manifest'])['functions'];expected={f['id'] for f in read(q['functions'])['functions']}
 require({f['id'] for f in functions}==expected,'Function universe changed')
 require(all(isinstance(f['predictedBloated'][method],bool) for f in functions),'Missing function predictions')
 if 'size' not in b:
  files=read(q['scope'])['files'];old=sum((q['root']/f).stat().st_size for f in files);new=sum((Path(b['target'])/f).stat().st_size for f in files)
  b['size']={'originalJSBytes':old,'transformedJSBytes':new,'reductionPercent':100*(old-new)/old,'savedImplementationBytes':sum(p.stat().st_size for p in Path(b['target']).rglob('*.BIGG'))}
 return b

def rq1(run_id,proof):
 c=setup(run_id,proof);c.protocol['arms']=ARMS;analyses=cached_analyses(c,proof);builds=[];rows=[]
 try:
  for lib in sorted(c.qualified):
   for arm in ARMS:
    b=build_one(c,lib,arm,analyses,'rq1-'+lib+'-'+arm);builds.append(b)
    for client in c.clients[lib]:
     row={'library':lib,'arm':arm,'client':client['name'],'eligible':comparison_eligible(client),'sourceTruth':client['hits']}
     if row['eligible']:
      hits=set(read(client['hits']));conf={k:0 for k in ['TP','FP','TN','FN']}
      for f in read(b['manifest'])['functions']:
       pred=f['predictedBloated'][arm];conf[('FP' if f['id'] in hits else 'TP') if pred else ('TN' if f['id'] in hits else 'FN')]+=1
      row.update(valid=True,confusion=conf,validation='Complete transformed target suite; independent held-out function truth. Transformed client behavior is checked separately in RQ2/RQ3.')
     else:row.update(valid=None,status='target-unexercised',confusion=None)
     rows.append(row)
    write(c.out/'rq1/components.json',builds);write(c.out/'rq1/clients.json',rows)
  require(len(builds)==50 and all(b['valid'] for b in builds),'Incomplete ten-library/five-configuration matrix')
  for lib in c.qualified:require(len({b['generatedRootCharacters'] for b in builds if b['library']==lib})==1,'Generated path widths differ between methods')
  c.record['stages'].append({'name':'rq1','status':'completed','libraries':10,'configurations':5,'builds':50,'eligibleClientCells':sum(r['eligible'] for r in rows),'clientTruthWorkloadsRerun':0});c.finish();require(c.record['status']=='completed','RQ1 input or implementation changed')
  return str(c.out)
 except Exception:
  c.record.update(status='failed',error=traceback.format_exc());c.save();raise

def payload_map(root):
 root=Path(root);require(root.is_dir(),'Missing payload tree is not an empty payload measurement')
 return {str(p.relative_to(root)):sha(p) for p in root.rglob('*.BIGG')}

def old_recovery_rows():
 result=[]
 for path in [ROOT/'runs/formal-20261027-001/rq2/loading.json',ROOT/'runs/supp-sscg-sdcg-loading-20261101-003/stubbifier-baselines/rq2-loading.json']:
  for r in read(path)['rows']:
   if r.get('valid') and r.get('eligible',True):result.append((r,path))
 return result

def reuse_recovery(c,b,client,candidates):
 for row,source in candidates:
  if row['library']!=b['library'] or row.get('arm',row.get('method'))!=b['arm'] or row.get('workload',row.get('client'))!=client['name']:continue
  try:
   stage=row.get('clientStage');require(same(client['baseline'],stage),'Client signature differs');assert_stage(stage)
   prior=source.parents[1] if source.parent.name=='rq2' else source.parent.parent
   frozen=read(prior/'executed-source-sha256.json')
   require(all(sha(ROOT/p)==h for p,h in frozen.items() if p.startswith('src/transformer/')),'Transformer implementation differs')
   old_cfg=read(prior/'machine.json');old_client=next(x for x in old_cfg['clients'][b['library']] if x['directory']==client['name'])
   for k in ['inputManifestSha256','targetBindings','command']:require(old_client[k]==client['cfg'][k],'Client binding differs')
   old_root=Path(stage['cwd'])/client['cfg']['targetBindings'][0]
   old_payload=payload_map(old_root);new_payload=payload_map(b['target'])
   require(old_payload==new_payload,'Selected payload set or bytes differ')
   require(all(Path(e['path']).is_file() and Path(e['path']).stat().st_size==int(e['bytes']) for e in row['payloadEvents']),'Recorded payload operands are unavailable or differ')
   require(metrics.loaded_bytes(row['payloadEvents'])==row['uniquePayloadBytes'],'Payload accounting differs')
   return dict(row,arm=b['arm'],client=client['name'],reused=True,reuseSource=str(source),reuseSourceSha256=sha(source),reuseCertificate={'payloadFiles':len(new_payload),'payloadHashesEqual':True,'clientSourceAndBindingEqual':True,'transformerSourceEqual':True})
  except (AssertionError,ValueError,KeyError,OSError,StopIteration):continue
 return None

def rq2(run_id,proof):
 c=setup(run_id,proof);c.protocol['arms']=METHODS;analyses=cached_analyses(c,proof);rows=[];candidates=old_recovery_rows()
 try:
  for lib in sorted(c.qualified):
   for method in METHODS:
    b=build_one(c,lib,method,analyses,'rq2-'+lib+'-'+method,instrument=True);loads=Path(b['lab'])/'loads'/lib
    for i,client in enumerate(c.clients[lib]):
     if not comparison_eligible(client):rows.append({'library':lib,'arm':method,'client':client['name'],'eligible':False,'valid':None,'uniquePayloadBytes':None});continue
     row=reuse_recovery(c,b,client,candidates)
     if row is None:
      tag='rq2-'+lib+'-'+method+'-'+str(i);root=bind(c,client['cfg'],b['target'],tag);payload=loads/'workloads'/client['name']
      stage=c.run(tag+'-client',client['cfg']['command'],root,{'HYBRID_PAYLOAD_OUT':payload});events=[]
      for p in sorted(payload.glob('payload-*.jsonl')):events.extend(json.loads(line) for line in p.read_text().splitlines())
      from .recovery_repair import reconcile_payload_events
      normalized,audit=reconcile_payload_events(events,b['target'])
      row={'library':lib,'arm':method,'client':client['name'],'workload':client['name'],'eligible':True,'valid':same(client['baseline'],stage),'clientStage':stage,'rawPayloadEvents':events,'payloadEvents':normalized,'byteAccounting':audit,'uniquePayloadBytes':metrics.loaded_bytes(normalized),'reused':False}
     rows.append(row);write(c.out/'rq2/loading.json',{'rows':rows})
     require(row['valid'],'Client recovery validation failed: '+lib+'/'+method+'/'+client['name'])
  eligible=[r for r in rows if r['eligible']];require(len(eligible)==129,'Recovery cohort incomplete')
  c.record['stages'].append({'name':'rq2','status':'completed','eligibleCells':len(eligible),'reusedCells':sum(bool(r.get('reused')) for r in eligible)});c.finish();require(c.record['status']=='completed','RQ2 input or implementation changed');return str(c.out)
 except Exception:c.record.update(status='failed',error=traceback.format_exc());c.save();raise

def rq3(run_id,proof,client_protocol=None):
 from .rq3 import run as timing
 c=setup(run_id,proof);c.protocol['arms']=METHODS;analyses=cached_analyses(c,proof);c.builds=[]
 c.protocol['researchQuestions']=['rq3']
 if client_protocol:
  from .recovery_repair import apply_client_protocol
  apply_client_protocol(c,client_protocol);c.protocol['clientExecutionProtocol']=str(client_protocol)
 write(c.out/'effective-protocol.json',c.protocol);write(c.out/'effective-machine.json',c.machine)
 try:
  for lib in sorted(c.qualified):
   for method in METHODS:c.builds.append(build_one(c,lib,method,analyses,'rq3-'+lib+'-'+method))
  c.record['timingReusePolicy']='No exact-byte timing series exists for the newly generated artifacts. Earlier series remain preserved and are not pooled.'
  timing.run(c,qualification=False);c.finish();require(c.record['status']=='completed' and c.record['stages'][-1]['status']=='completed','Timing matrix incomplete or inputs changed');return str(c.out)
 except Exception:c.record.update(status='failed',error=traceback.format_exc());c.save();raise

def rq4(run_id,proof):
 parent=ROOT/'runs'/run_id;parent.mkdir(exist_ok=False);rows=[]
 record={'status':'running','runId':run_id,'phase':'rq4','plannedCells':300,'methods':METHODS,'repetitions':10,'rows':rows,'policy':'Fresh repeated analyses, interleaved method order, isolated equal-width cell IDs. No old single costs or changed-runtime Hybrid costs are pooled.'};write(parent/'status.json',record)
 try:
  for lib in sorted(proof['libraries']):
   for rep in range(10):
    methods=list(METHODS);random.Random('20261104/'+lib+'/'+str(rep)).shuffle(methods)
    for method in methods:
     cell='rq4cell-'+hashlib.sha256((run_id+'/'+lib+'/'+method+'/'+str(rep)).encode()).hexdigest()[:24]
     c=setup(cell,proof,clients=False,libraries=[lib]);q=c.qualified[lib];start=time.monotonic()
     c.protocol['arms']=METHODS;c.protocol['researchQuestions']=['rq4'];write(c.out/'effective-protocol.json',c.protocol)
     if method=='hybrid':
      sg=own.static(c,lib,q,'mcg-only','cost-static');dg=own.dynamic(c,lib,q,'cost-profile');require(sg['valid'] and dg['valid'],'Fresh Hybrid analysis failed')
      b=own.build(c,lib,q,'hybrid',sg,dg,'cost-transform');s=sg['stage']['seconds'];d=dg['stage']['seconds'];mapping=dg.get('mapping',{}).get('seconds',0);selection=(b.get('targetExtraction') or {}).get('seconds',0)
      analysis=s+d+mapping+selection;extra={'staticSeconds':s,'dynamicSeconds':d,'mappingSeconds':mapping,'selectionSeconds':selection}
     else:
      a=(baseline.sscg if method=='sscg' else baseline.sdcg)(c,lib,q);require(a.get('valid'),'Fresh baseline analysis failed')
      b=baseline.build(c,lib,q,method,a,'cost-transform');analysis=sum(x['seconds'] for x in a['stages'] if not x['label'].startswith('sscg-index-control-'));extra={}
     require(b.get('valid'),'Fresh cost output did not preserve target suite')
     transform=b['transform']['seconds'];row=dict(extra,library=lib,method=method,repetition=rep,cellRun=cell,valid=True,analysisSeconds=analysis,transformSeconds=transform,totalSeconds=analysis+transform,graalRuntime=runtime_for(proof,lib),driverWallIncludingCopyValidationAndInventory=time.monotonic()-start,boundary='Measured subprocess analysis stages plus transformation; copying, inventory, source checks and post-transform target validation excluded. Python adapter bookkeeping is not separately estimated. Runtime is pinned per library; compare matched methods within each library and report runtime strata explicitly.')
     c.record['stages'].append({'name':'rq4-cost-cell','status':'completed'});c.finish();require(c.record['status']=='completed','Cost cell inputs changed');rows.append(row);write(parent/'rq4/preparation-cost.json',{'rows':rows});write(parent/'status.json',record)
  require(len(rows)==300,'Cost repetitions incomplete');record.update(status='completed');write(parent/'status.json',record);return str(parent)
 except Exception:record.update(status='failed',error=traceback.format_exc());write(parent/'status.json',record);raise
