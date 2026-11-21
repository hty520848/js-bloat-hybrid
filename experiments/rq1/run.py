import json,re,shutil
from pathlib import Path
from ..common import ROOT,read,write,sha,clone,same,variant_directory,register_recovery,retained_paths,completion_gate
from .static_benchmark import run as static_benchmark,flags,canonical_arm
def arm_env(arm):
 """Arm name -> switch environment. Unknown arms raise instead of silently
 keeping both switches on; a wrong arm name previously turned every cell into
 the full configuration."""
 return flags(canonical_arm(arm))
def static(c,lib,q,arm,tag,extra_env=None,ablation=False):
 graph=c.out/'rq1/graphs'/(tag+'.json');graph.parent.mkdir(parents=True,exist_ok=True)
 stats=graph.with_name(graph.stem+'.ablation.json')
 extra={'NODE_PATH':c.machine['staticNodeModules'],'SQJ_SCOPE_FILES':q['scope'],'SQJ_PUBLISHED_MANIFEST':q['allow'],'SQJ_PUBLISHED_ROOT':q['root']}
 extra.update(arm_env(arm))
 # `no-file-scope` removes the paper's file-range step instead of a runtime
 # guard. An empty SQJ_SCOPE_FILES is falsy, so getAllFiles walks the whole
 # package (tests, benchmarks, dev-only sources) exactly as it would without the
 # scope manifest.
 if canonical_arm(arm)=='no-file-scope':extra['SQJ_SCOPE_FILES']=''
 if extra_env:extra.update(extra_env)
 if ablation:extra['MCG_ABLATION_STATS']=str(stats)
 stage=c.run(tag,[c.machine['nodeStatic'],ROOT/'src/static/src/index.js',q['root'],graph],ROOT,extra)
 result={'stage':stage,'graph':str(graph),'valid':stage['exitCode']==0 and graph.is_file()}
 if ablation:result['ablation']=read(stats) if stats.is_file() else None
 return result
def canonical(edges,origin,lib):
 out=[];excluded=[]
 for edge in edges:
  parts=[]
  for n in edge.split(' -> '):
   n=n.replace('(Native):',':');prefix=str(origin)+'/'
   if n.startswith(prefix):n=n[len(prefix):]
   n=n.lstrip('/')
   if not re.fullmatch(r'(.+\.js):<(\d+),(\d+)>--<(\d+),(\d+)>',n) or not (origin/n.split(':<')[0]).is_file():break
   parts.append('Data/'+lib+'/'+n)
  if len(parts)==2:out.append(' -> '.join(parts))
  else:excluded.append(edge)
 return sorted(set(out)),excluded
def dynamic(c,lib,q,tag):
 raw=c.out/'rq1/dynamic'/(tag+'.json');raw.parent.mkdir(parents=True,exist_ok=True)
 runtime=dict(c.machine,**c.machine.get('runtimeOverrides',{}).get(lib,{}))
 args=[runtime['graalNode']]+runtime.get('profileArguments',[])+['--vm.classpath='+runtime['nodeprofJar'],'--experimental-options','--nodeprof',runtime['nodeprofLoader'],'--analysis',ROOT/'src/dynamic/dyn-with-source.js']+q['command'][1:]
 if len(q['command'])>1 and 'mocha' in q['command'][1] and not any(arg.startswith('--timeout') for arg in q['command'][2:]):
  args+=['--timeout',str(c.protocol.get('profileTestCaseTimeoutMillis',20000))]
 env=dict(runtime.get('profileEnvironment',{}),SQJ_SCOPE_FILES=q['scope'],BLOAT_DYN_ROOT=q['root'],BLOAT_DYN_OUT=raw,BLOAT_TYPECHECK_NODE=c.machine['nodeTest'])
 stage=c.run(tag,args,q['root'],env,timeout=c.protocol.get('profileTimeoutByLibrary',{}).get(lib,c.protocol['profileTimeoutSeconds']))
 meta=read(str(raw)+'.meta.json') if Path(str(raw)+'.meta.json').is_file() else {}
 valid=same(q['original'],stage) and raw.is_file() and Path(str(raw)+'.sources.json').is_file() and bool(meta) and not meta.get('stackMismatches') and not meta.get('remainingUserFrames')
 result={'stage':stage,'metadata':meta,'valid':valid}
 if not valid:return result
 mapped=raw.with_name(tag+'-mapped.json');spec=raw.with_name(tag+'-mapping-spec.json')
 write(spec,{'graph':str(raw),'records':str(raw)+'.sources.json','originalRoot':str(q['root']),'executedRoot':str(q['root']),'remap':{},'output':str(mapped),'audit':str(raw.with_name(tag+'-mapping-audit.json'))})
 result['mapping']=c.run(tag+'-map',[c.machine['nodeTest'],ROOT/'src/dynamic/map_executed_source.js',spec],ROOT)
 result.update(mapped=str(mapped),valid=result['mapping']['exitCode']==0 and mapped.is_file())
 return result
def build(c,lib,q,arm,sg,dg,tag,instrument=False,validate=True):
 lab=variant_directory(c,tag);shutil.copytree(str(ROOT/'src/transformer'),str(lab),ignore=shutil.ignore_patterns('node_modules','__pycache__'))
 (lab/'node_modules').symlink_to(c.machine['transformerNodeModules']);target=clone(q.get('deployment',q['root']),lab/'Data'/lib);register_recovery(c,target,lab)
 sc=read(q['scope']);deps=[x['path'].split('node_modules/',1)[1] for x in sc['dependencies']]
 (target/'dep_list.txt').write_text('\n'.join(deps)+'\n');(target/'coverage').mkdir(exist_ok=True);write(target/'coverage/coverage-final.json',{})
 graph,excluded=canonical(read(sg['graph']),q['root'],lib) if sg else ([],[])
 loads=lab/'loads'/lib;loads.mkdir(parents=True)
 retained=retained_paths(c,lib,target)
 env={'SQJ_SCOPE_FILES':q['scope'],'STUBBIFIER_INSTRUMENTATION':'1' if instrument else '0','STUBBIFIER_USE_NODEPROF':'1' if arm in ['hybrid','nodeprof-only'] else '0','STUBBIFIER_DYNAMIC_GRAPH':dg.get('mapped','') if dg else '', 'STUBBIFIER_RESULT_ROOT':lab/'Data','STUBBIFIER_LOAD_ROOT':lab/'loads','STUBBIFIER_RETAIN_ROOTS':json.dumps(retained)}
 target_extraction=None
 if arm=='nodeprof-only':
  code="const fs=require('fs');const m=require(process.argv[1]).getNodeProfTargets(process.argv[2],process.argv[3],process.argv[4]);fs.writeFileSync(process.argv[5],JSON.stringify(m));"
  mp=lab/'nodeprof-mapping.json';st=c.run(tag+'-targets',[c.machine['nodeTest'],'-e',code,lab/'nodeprofTargets.js',dg['mapped'],target,'Data/'+lib,mp],lab,env)
  target_extraction=st
  if st['exitCode']:return {'valid':False,'mapping':st,'arm':arm,'library':lib}
  targets=read(mp);graph=['Data/'+lib+'/index.js:<1,0>--<1,0> -> '+n for n in targets['targets']];env['STUBBIFIER_RETAIN_ROOTS']=json.dumps(sorted(set(retained+targets['retainedFiles'])))
 write(target/'static.csv',graph)
 transform=c.run(tag+'-transform',[c.machine['nodeTest'],'deboater.js','hybrid' if arm=='hybrid' else 'static',lib],lab,env)
 tested=target
 if validate and q.get('deployment'):
  from ..baselines import harness
  tested=harness(c,lib,q,target,tag+'-core')
 core=c.run(tag+'-core',q['command'],tested,{'HYBRID_PAYLOAD_OUT':loads} if instrument else None) if validate else None
 errors=re.findall(r'ERROR:.*|Yikes.*',Path(transform['log']).read_text(errors='replace'))
 spec=c.out/'rq1/manifests'/(tag+'-spec.json');manifest=spec.with_name(tag+'.json')
 write(spec,{'root':str(q['root']),'scopeFiles':sc['files'],'variants':{arm:str(target)},'instrument':False,'output':str(manifest)})
 inventory=c.run(tag+'-manifest',[c.machine['nodeTest'],ROOT/'src/metrics/truth_manifest.js',spec],ROOT)
 result={'library':lib,'arm':arm,'transform':transform,'targetExtraction':target_extraction,'core':core,'coreValidationRoot':str(tested) if validate else None,'coldDeploymentMeasured':True,'generatedRootCharacters':len(str(lab)),'retainedDeploymentPaths':retained,'errors':errors,'target':str(target),'lab':str(lab),'manifest':str(manifest),'inventory':inventory,'excludedStaticEdges':excluded,'valid':transform['exitCode']==0 and not errors and not excluded and (not validate or same(q['original'],core)) and inventory['exitCode']==0}
 if result['valid']:
  hits=set(read(q['coreHits']));count={k:0 for k in ['TP','FP','TN','FN']}
  for f in read(manifest)['functions']:
   predicted=f['predictedBloated'][arm]
   if predicted is None:raise ValueError('Prediction lacks a source identity')
   count[('FP' if f['id'] in hits else 'TP') if predicted else ('TN' if f['id'] in hits else 'FN')]+=1
  result['coreConditionedConfusion']=count
  files=sc['files'];osize=sum((q['root']/n).stat().st_size for n in files);tsize=sum((target/n).stat().st_size for n in files)
  payload=sum(p.stat().st_size for p in target.rglob('*.BIGG'));result['size']={'originalJSBytes':osize,'transformedJSBytes':tsize,'savedImplementationBytes':payload,'reductionPercent':100.0*(osize-tsize)/osize,'withRecoveryPayloadBytes':tsize+payload,'boundary':'Fixed production .js cohort; recovery payload reported separately; no claim of deployment saving after adding payload, loader and metadata.'}
 return result
def run(c,qualification=True):
 static_benchmark(c)
 c.builds=[];c.graphs={};c.dynamic={}
 for lib,q in sorted(c.qualified.items()):
  gs={}
  for arm in ['mcg-only','mcg-no-index','mcg-no-module-filter','mcg-no-both']:gs[arm]=static(c,lib,q,arm,'rq1-static-'+lib+'-'+arm)
  dg=dynamic(c,lib,q,'rq1-profile-'+lib);c.graphs[lib]=gs;c.dynamic[lib]=dg
  for arm in c.protocol['arms']:
   sg=gs.get(arm,gs['mcg-only'])
   if not sg['valid'] or (arm in ['hybrid','nodeprof-only'] and not dg['valid']):
    c.builds.append({'library':lib,'arm':arm,'valid':False,'reason':'Analysis graph failed qualification'});continue
   c.builds.append(build(c,lib,q,arm,sg,dg,'rq1-'+lib+'-'+arm));write(c.out/'rq1/components.json',c.builds)
 if not qualification:
  from ..clients import bind,comparison_eligible
  client_results=[]
  for b in c.builds:
   for i,client in enumerate(c.clients.get(b['library'],[])):
    if not comparison_eligible(client):
     client_results.append({'library':b['library'],'client':client['name'],'arm':b['arm'],'eligible':False,'valid':None,'status':'not-run-target-unexercised','confusion':None});continue
    if not b['valid'] or not b.get('target') or not b.get('manifest'):
     client_results.append({'library':b['library'],'client':client['name'],'arm':b['arm'],'valid':False,'status':'not-run-analysis-or-build-failed','reason':b.get('reason','Build did not qualify')});continue
    target=bind(c,client['cfg'],b['target'],'rq1-'+b['library']+'-'+b['arm']+'-'+str(i))
    stage=c.run('rq1-client-'+b['library']+'-'+b['arm']+'-'+str(i),client['cfg']['command'],target)
    hits=set(read(client['hits']));count={k:0 for k in ['TP','FP','TN','FN']}
    for f in read(b['manifest'])['functions']:
     predicted=f['predictedBloated'][b['arm']];count[('FP' if f['id'] in hits else 'TP') if predicted else ('TN' if f['id'] in hits else 'FN')]+=1
    client_results.append({'library':b['library'],'client':client['name'],'arm':b['arm'],'valid':b['valid'] and same(client['baseline'],stage),'stage':stage,'confusion':count})
  write(c.out/'rq1/clients.json',client_results)
 gate=completion_gate(c.protocol,c.qualified,[(x['library'],x['arm']) for x in c.builds if x['valid']],[(x['library'],x['arm']) for x in c.builds if not x['valid']])
 if not qualification:
  comparable=[x for x in client_results if x.get('eligible',True)]
  if not comparable or not all(x['valid'] for x in comparable):gate['status']='blocked'
 row=dict(gate,name='rq1',scope='Full original unit workloads, fresh same-source truth. Client results are separate; valid target-unexercised workloads remain explicit coverage gaps.',qualifiedLibraries=sorted(c.qualified),components=len(c.builds),formalResult=not qualification)
 c.record['stages'].append(row);c.save()
