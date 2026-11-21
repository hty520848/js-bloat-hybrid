"""Controlled deadline repair and exact-artifact reuse of completed RQ2 blocks."""
import ast,copy,hashlib,json,traceback
from pathlib import Path
from .common import ROOT,read,write,sha,same
from . import ordered_revision as phases,clients,metrics

TIMEOUT_MS=20000
CLIENT_LIBRARY='css-loader'
CLIENT_NAME='style-loader'
DRIVER=ROOT/'scripts/harness/client_jest_deadline.cjs'

def require(value,message):
 if not value:raise ValueError(message)

def function_ast(filename,name):
 node=next(n for n in ast.parse(Path(filename).read_text()).body if isinstance(n,ast.FunctionDef) and n.name==name)
 return ast.dump(node,include_attributes=False)

def verify_preserved_rq1(source,proof):
 source=Path(source).resolve();status=read(source/'status.json');builds=read(source/'rq1/components.json')
 require(status['status']=='completed' and len(builds)==50 and all(b['valid'] for b in builds),'Completed RQ1 evidence is unavailable')
 require({b['library'] for b in builds}==set(proof['libraries']),'RQ1 library cohort differs')
 frozen=read(source/'executed-source-sha256.json')
 for rel,digest in frozen.items():
  if rel.startswith('src/') or rel in ['experiments/common.py','experiments/metrics.py','experiments/clients.py','experiments/rq1/run.py']:
   require(sha(ROOT/rel)==digest,'Scientific implementation differs from completed RQ1: '+rel)
 for name in ['rq1','build_one','cached_analyses']:
  require(function_ast(source/'executed-source/experiments/ordered_revision.py',name)==function_ast(ROOT/'experiments/ordered_revision.py',name),'RQ1 computation changed: '+name)
 require(read(source/'runtime-admission.json')==proof,'RQ1 runtime/source admission differs')
 return {'source':str(source),'statusSha256':sha(source/'status.json'),'componentsSha256':sha(source/'rq1/components.json'),'builds':50,'replayed':False}

def deadline_command(node):
 return [str(node),str(DRIVER),'--timeout-ms='+str(TIMEOUT_MS)]

def reconcile_payload_events(events,artifact):
 """Use the saved expansion operand, never a producer's pre-transformation size."""
 root=Path(artifact).resolve();result=[];changed=0
 for event in events:
  require(event.get('kind') in ['file','function'],'Unknown recovery event kind')
  file=Path(event['path']).resolve()
  require(root in file.parents and file.name.endswith('.BIGG') and file.is_file(),'Recovery operand is absent or outside the certified artifact: '+str(file))
  row=copy.deepcopy(event);actual=file.stat().st_size;reported=int(event['bytes'])
  row.update(bytes=actual,reportedBytes=reported,payloadSha256=sha(file));changed+=actual!=reported;result.append(row)
 return result,{'policy':'Physical expanded .BIGG bytes, de-duplicated by kind/path; raw producer counters retained separately','eventCount':len(events),'reportedByteCountMismatches':changed,'rawUniquePayloadBytes':metrics.loaded_bytes(events),'actualUniquePayloadBytes':metrics.loaded_bytes(result)}

def require_matched_deadline_controls(baseline,controls):
 require(set(controls)==set(phases.METHODS),'Deadline validation must include all three methods')
 require(all(same(baseline,stage) for stage in controls.values()),'A method did not preserve the complete shared-deadline suite')
 require(all(stage['command']==baseline['command'] for stage in controls.values()),'Deadline commands must match on original and all methods')

def qualify_original(c):
 old=next(x for x in c.clients[CLIENT_LIBRARY] if x['name']==CLIENT_NAME)
 cfg=copy.deepcopy(old['cfg']);require(cfg['command']==['npm','test'],'Unexpected original client command')
 cfg.pop('baselineEvidence',None);cfg['command']=deadline_command(c.machine['nodeTest'])
 saved_clients=c.clients;saved_machine=c.machine['clients']
 try:
  c.machine['clients']={CLIENT_LIBRARY:[cfg]}
  rows=clients.qualify(c)
  require(len(rows)==1 and rows[0]['qualified'],'Revised original or independent-truth control failed')
  replacement=c.clients[CLIENT_LIBRARY][0]
 finally:
  c.clients=saved_clients;c.machine['clients']=saved_machine
 require(same(old['baseline'],replacement['baseline']),'Revised original suite changed test discovery or snapshots')
 original_ids={x for x in read(old['hits']) if not x.startswith('@file:')}
 revised_ids={x for x in read(replacement['hits']) if not x.startswith('@file:')}
 require(original_ids==revised_ids,'Deadline change altered independent function truth; do not reuse RQ1')
 c.clients[CLIENT_LIBRARY]=[replacement if x['name']==CLIENT_NAME else x for x in c.clients[CLIENT_LIBRARY]]
 c.machine['clients'][CLIENT_LIBRARY]=[cfg if x['directory']==CLIENT_NAME else x for x in c.machine['clients'][CLIENT_LIBRARY]]
 row=rows[0]
 return replacement,{'schemaVersion':1,'status':'controls-pending','library':CLIENT_LIBRARY,'client':CLIENT_NAME,'timeoutMilliseconds':TIMEOUT_MS,'baseCommand':old['cfg']['command'],'command':cfg['command'],'inputManifestSha256':cfg['inputManifestSha256'],'targetBindings':cfg['targetBindings'],'driver':{'path':str(DRIVER),'sha256':sha(DRIVER)},'original':replacement['baseline'],'independentTruth':row['truth'],'hits':replacement['hits'],'hitsSha256':sha(replacement['hits']),'priorHits':old['hits'],'priorHitsSha256':sha(old['hits']),'functionTruthUnchanged':True,'methodControls':{},'policy':'Same 20-second Jest deadline for original and all three methods; complete pretest lint, coverage, tests and snapshots retained. Original 5-second failures remain separate. This certificate is not a timing result.'}

def apply_client_protocol(c,path):
 cert=read(path);require(cert['status']=='qualified','Client deadline certificate is not qualified')
 require(cert['timeoutMilliseconds']==TIMEOUT_MS and cert['command']==deadline_command(c.machine['nodeTest']),'Client deadline command differs')
 require(sha(cert['driver']['path'])==cert['driver']['sha256'],'Client driver changed')
 require_matched_deadline_controls(cert['original'],cert['methodControls'])
 for stage in [cert['original'],cert['independentTruth']]+list(cert['methodControls'].values()):phases.assert_stage(stage)
 require(same(cert['original'],cert['independentTruth']),'Independent truth suite differs')
 for name in ['hits','priorHits']:require(sha(cert[name])==cert[name+'Sha256'],'Independent truth file changed')
 require({x for x in read(cert['hits']) if not x.startswith('@file:')}=={x for x in read(cert['priorHits']) if not x.startswith('@file:')},'Function truth differs')
 entry=next(x for x in c.clients[CLIENT_LIBRARY] if x['name']==CLIENT_NAME)
 for field in ['inputManifestSha256','targetBindings']:require(entry['cfg'][field]==cert[field],'Client input/binding differs')
 entry['cfg']=copy.deepcopy(entry['cfg']);entry['cfg']['command']=cert['command'];entry['baseline']=cert['original'];entry['hits']=cert['hits']
 c.machine['clients'][CLIENT_LIBRARY]=[entry['cfg'] if x['directory']==CLIENT_NAME else x for x in c.machine['clients'][CLIENT_LIBRARY]]
 write(c.out/'client-execution-protocol.json',{'source':str(path),'sha256':sha(path),'certificate':cert})
 return cert

def completed_blocks(c,source,proof):
 source=Path(source).resolve();frozen=read(source/'executed-source-sha256.json');oldproof=read(source/'runtime-admission.json')
 for rel,digest in frozen.items():
  if rel.startswith('src/') or rel in ['experiments/common.py','experiments/clients.py','experiments/baselines.py','experiments/rq1/run.py','experiments/stubbifier_baselines.py','experiments/metrics.py','experiments/coverage_map.py','experiments/deployment.py']:
   require(sha(ROOT/rel)==digest,'RQ2 source differs; cached block cannot be reused: '+rel)
 for name in ['build_one','cached_analyses','reuse_recovery','payload_map']:
  require(function_ast(source/'executed-source/experiments/ordered_revision.py',name)==function_ast(ROOT/'experiments/ordered_revision.py',name),'RQ2 cache computation changed: '+name)
 oldrows=read(source/'rq2/loading.json')['rows'];reused={};receipts=[]
 for lib in sorted(c.qualified):
  if lib==CLIENT_LIBRARY:continue  # Requalify this affected library under the corrected client protocol.
  eligible=[x for x in c.clients[lib] if clients.comparison_eligible(x)]
  selected={(r['arm'],r['client']):r for r in oldrows if r['library']==lib and r.get('eligible') and r.get('valid')}
  if not all((arm,client['name']) in selected for arm in phases.METHODS for client in eligible):continue
  require(oldproof['libraries'][lib]['sourceHashes']==proof['libraries'][lib]['sourceHashes'],'Cached source scope differs')
  block={}
  for arm in phases.METHODS:
   tag='rq2-'+lib+'-'+arm;core=read(source/'commands'/(tag+'-core.json'));phases.assert_stage(core)
   require(same(c.qualified[lib]['original'],core),'Cached target core suite differs')
   phases.assert_stage(read(source/'commands'/(tag+'-transform.json')))
   cold=ROOT/'work'/source.name/'variants'/hashlib.sha256(tag.encode()).hexdigest()[:16]/'Data'/lib
   for client in eligible:
    original=selected[(arm,client['name'])];phases.assert_stage(original['clientStage']);require(same(client['baseline'],original['clientStage']),'Cached client suite differs')
    prior_cfg=next(x for x in read(source/'machine.json')['clients'][lib] if x['directory']==client['name'])
    for field in ['inputManifestSha256','targetBindings','command']:require(prior_cfg[field]==client['cfg'][field],'Cached client binding/source differs')
    client_root=Path(original['clientStage']['cwd'])/client['cfg']['targetBindings'][0]
    require(phases.payload_map(client_root)==phases.payload_map(cold),'Cold and measured client payload bytes differ')
    events,audit=reconcile_payload_events(original.get('rawPayloadEvents',original['payloadEvents']),cold)
    result=copy.deepcopy(original);result.update(rawPayloadEvents=original.get('rawPayloadEvents',original['payloadEvents']),payloadEvents=events,uniquePayloadBytes=metrics.loaded_bytes(events),byteAccounting=audit,reused=True,reuseSource=str(source/'rq2/loading.json'),reuseSourceSha256=sha(source/'rq2/loading.json'),reuseCertificate={'payloadHashesEqual':True,'clientSourceAndBindingEqual':True,'transformerSourceEqual':True,'rawCountersReconciledAgainstPhysicalPayloads':True})
    result['artifactReuseMode']='Original qualified cold artifact and existing measurement; no replacement artifact generated or workload replayed'
    block[(lib,arm,client['name'])]=result
  reused.update(block);receipts.append({'library':lib,'cells':len(block),'source':str(source),'sourceSha256':sha(source/'rq2/loading.json'),'exactArtifactAndClientCertificates':True})
 write(c.out/'rq2/completed-block-reuse.json',receipts)
 return reused

def run(run_id,proof,source_rq2):
 c=phases.setup(run_id,proof);c.protocol['arms']=list(phases.METHODS);c.protocol['researchQuestions']=['rq2'];c.protocol['clientDeadlineOverrides']={CLIENT_LIBRARY+'/'+CLIENT_NAME:TIMEOUT_MS}
 write(c.out/'effective-protocol.json',c.protocol)
 values={};builds={};cert_path=c.out/'repair/client-deadline-certificate.json'
 def save():write(c.out/'rq2/loading.json',{'rows':[values[k] for k in sorted(values)],'plannedEligibleCells':129,'correctedClientProtocol':str(cert_path),'failuresRetainedAt':str(source_rq2)})
 def measure(b,client,tag):
  root=clients.bind(c,client['cfg'],b['target'],tag);payload=c.out/'rq2/payload-events'/b['library']/b['arm']/client['name']
  stage=c.run(tag+'-client',client['cfg']['command'],root,{'HYBRID_PAYLOAD_OUT':payload});events=[]
  for file in sorted(payload.glob('payload-*.jsonl')):events.extend(json.loads(line) for line in file.read_text().splitlines())
  normalized,audit=reconcile_payload_events(events,b['target'])
  row={'library':b['library'],'arm':b['arm'],'client':client['name'],'workload':client['name'],'eligible':True,'valid':same(client['baseline'],stage),'clientStage':stage,'rawPayloadEvents':events,'payloadEvents':normalized,'byteAccounting':audit,'uniquePayloadBytes':metrics.loaded_bytes(normalized),'reused':False,'baselineStage':client['baseline'],'artifactTarget':b['target']}
  values[(b['library'],b['arm'],client['name'])]=row;save();require(row['valid'],'Repaired RQ2 client did not preserve full suite: '+str((b['library'],b['arm'],client['name'])))
  return row
 try:
  values.update(completed_blocks(c,source_rq2,proof));save()
  client,cert=qualify_original(c);write(cert_path,cert);write(c.out/'effective-machine.json',c.machine)
  analyses=phases.cached_analyses(c,proof)
  # Finish the affected client's matched controls first, before the long missing-cell batch.
  for arm in phases.METHODS:
   b=phases.build_one(c,CLIENT_LIBRARY,arm,analyses,'rq2-'+CLIENT_LIBRARY+'-'+arm,instrument=True);builds[(CLIENT_LIBRARY,arm)]=b;write(c.out/'rq2/builds.json',list(builds.values()))
   row=measure(b,client,'repair-'+arm+'-'+CLIENT_NAME);cert['methodControls'][arm]=row['clientStage'];write(cert_path,cert)
  require_matched_deadline_controls(cert['original'],cert['methodControls']);cert['status']='qualified';write(cert_path,cert)
  c.record['stages'].append({'name':'client-deadline-repair','status':'passed','originalAndIndependentTruth':True,'methods':list(phases.METHODS),'functionTruthUnchanged':True,'deadlineMillis':TIMEOUT_MS});c.save()
  for lib in sorted(c.qualified):
   for arm in phases.METHODS:
    for client in c.clients[lib]:
     key=(lib,arm,client['name'])
     if key in values:continue
     if not clients.comparison_eligible(client):values[key]={'library':lib,'arm':arm,'client':client['name'],'eligible':False,'valid':None,'uniquePayloadBytes':None};save();continue
     if (lib,arm) not in builds:
      builds[(lib,arm)]=phases.build_one(c,lib,arm,analyses,'rq2-'+lib+'-'+arm,instrument=True);write(c.out/'rq2/builds.json',list(builds.values()))
     measure(builds[(lib,arm)],client,'rq2-'+lib+'-'+arm+'-'+client['name'])
  eligible=[r for r in values.values() if r['eligible']];require(len(eligible)==129 and all(r['valid'] for r in eligible),'Repaired recovery matrix is incomplete')
  c.record['stages'].append({'name':'rq2','status':'completed','eligibleCells':len(eligible),'reusedCells':sum(bool(r.get('reused')) for r in eligible),'clientProtocol':str(cert_path)});c.finish();require(c.record['status']=='completed','Repaired RQ2 source or inputs changed')
  return str(c.out),str(cert_path)
 except Exception:
  if cert_path.exists():
   cert=read(cert_path)
   if cert['status']!='qualified':cert.update(status='failed',error=traceback.format_exc());write(cert_path,cert)
  c.record.update(status='failed',error=traceback.format_exc());c.save();raise
