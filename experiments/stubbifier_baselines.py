"""SSCG/SDCG adapters with fresh, hash-bound analysis on the declared scope.

These routines keep full test controls. A failed extraction never falls back
to historical graphs/coverage. Availability is distinct from qualification.
"""
import csv,json,os,re,shutil
from pathlib import Path
from .common import ROOT,read,write,sha,clone,same,variant_directory,register_recovery,retained_paths

def sscg(c,lib,q):
 cfg=c.machine['stubbifierBaselines'];query=ROOT/'src/baselines/stubbifier-recovery.ql';assert sha(query)==cfg['querySha256']
 view=clone(q['root'],c.work/'sscg'/lib/'source');changes=[];main=read(view/'package.json').get('main','index.js');compiled=view/main
 # Index the same runtime JavaScript as the existing compiled-test resolver.
 # Only nonproduction tests are rewritten, and the unchanged suite must pass.
 if compiled.is_file() and compiled.suffix=='.js':
  for folder in ['test','tests','__tests__']:
   for p in (view/folder).rglob('*'):
    if p.suffix not in ['.js','.ts'] or 'typescript' in p.parts:continue
    before=p.read_text();old=sha(p)
    def replace(m):
     logical=(p.parent/m.group(2)).resolve()
     if logical!=view:return m.group(0)
     request=os.path.relpath(str(compiled),str(p.parent));return m.group(1)+(request if request.startswith('.') else './'+request)
    after=re.sub(r"((?:from\s*|require\()['\"])(\.[^'\"\n]+)",replace,before)
    if after!=before:p.write_text(after);changes.append({'file':str(p.relative_to(view)),'beforeSha256':old,'afterSha256':sha(p)})
 sc=read(q['scope']);assert all(sha(view/f)==h for f,h in sc['hashes'].items())
 stages=[]
 if changes:
  stage=c.run('sscg-index-control-'+lib,q['command'],view);stages.append(stage)
  if not same(q['original'],stage):return {'valid':False,'stages':stages,'reason':'Index-view control differs','changes':changes}
 output=c.out/'stubbifier-baselines/sscg'/lib;output.mkdir(parents=True);database=view.parent/'database';cli=cfg['codeql'];search=cfg['searchPath']
 # CodeQL 2.3.4 takes exactly one positional argument (the database) and needs
 # the extractor pack on --search-path at creation time. The previous form
 # appended the source root as a second positional, which this CLI rejects with
 # "Unmatched argument at index 4", so every SSCG cell failed before analysis.
 stages.append(c.run('sscg-database-'+lib,[cli,'database','create','--language=javascript','--threads=2','--search-path='+search,'--source-root='+str(view),str(database)],c.work,{'LGTM_INDEX_FILTERS':'include:/'},timeout=3600))
 if stages[-1]['exitCode']:return {'valid':False,'stages':stages,'reason':'Database creation failed'}
 queries=view.parent/'queries';queries.mkdir();(queries/'qlpack.yml').write_text('name: hybrid-sscg-queries\nversion: 0.0.0\nlibraryPathDependencies: codeql-javascript\n')
 for name,body in [('static',query.read_text()),('inventory','import javascript\nfrom Function f\nwhere f.getFile().getAbsolutePath().matches('+json.dumps(str(view)+'/%')+')\nselect f.getFile().getAbsolutePath(), f.getLocation().getStartLine(), f.getLocation().getStartColumn(), f.getLocation().getEndLine(), f.getLocation().getEndColumn()\n')]:
  file=queries/(name+'.ql');file.write_text(body);bqrs=output/(name+'.bqrs');raw=output/(name+'.csv')
  stages.append(c.run('sscg-'+name+'-'+lib,[cli,'query','run','--ram=32768','--threads=0','--search-path='+search,'--database='+str(database),'--output='+str(bqrs),str(file)],c.work,timeout=1800))
  if stages[-1]['exitCode']:return {'valid':False,'stages':stages,'reason':'Query failed'}
  stages.append(c.run('sscg-decode-'+name+'-'+lib,[cli,'bqrs','decode','--format=csv','--output='+str(raw),str(bqrs)],c.work))
  if stages[-1]['exitCode']:return {'valid':False,'stages':stages,'reason':'Decode failed'}
 inventory=list(csv.reader((output/'inventory.csv').read_text().splitlines()))[1:];scope=set(sc['files']);indexed={str(Path(r[0]).relative_to(view)) for r in inventory if r and r[0].startswith(str(view)+'/')};expected={f['file'] for f in read(q['functions'])['functions']}
 if not expected<=indexed:return {'valid':False,'stages':stages,'reason':'Measured function files not indexed','missingFiles':sorted(expected-indexed)}
 rows=[];excluded=[]
 for row in list(csv.reader((output/'static.csv').read_text().splitlines()))[1:]:
  m=re.fullmatch(r'Fun\((.*):<(\d+),(\d+)>--<(\d+),(\d+)>\)',row[1]) if len(row)>1 else None
  if not m or not m[1].startswith(str(view)+'/'):excluded.append(row);continue
  rel=str(Path(m[1]).relative_to(view))
  if rel not in scope:excluded.append(row);continue
  rows.append([x.replace(str(view),'/Data/'+lib) for x in row])
 graph=output/'canonical.csv'
 with graph.open('w',newline='') as f:w=csv.writer(f,lineterminator='\n',quoting=csv.QUOTE_ALL);w.writerow(['col0','col1']);w.writerows(rows)
 certificate=output/'qualification.json'
 write(certificate,{'databaseQualified':True,'queryAndInventoryCompleted':True,'qualifiedEmptyGraph':not rows,'querySha256':sha(query),'scopeSha256':sha(q['scope']),'indexedMeasuredFiles':len(expected),'indexedMeasuredFunctionFiles':sorted(expected),'rows':len(rows),'excludedRows':excluded,'indexAdaptations':changes})
 return {'valid':True,'stages':stages,'graph':str(graph),'querySha256':sha(query),'graphRows':len(rows),'emptyGraphCertificate':str(certificate) if not rows else '', 'reason':None if rows else 'Qualified database and complete measured-file inventory; unchanged unsound native query returned no scoped callees'}

def sdcg(c,lib,q):
 cfg=c.machine['stubbifierBaselines'];root=clone(q['root'],c.work/'sdcg'/lib);sc=read(q['scope']);out=c.out/'stubbifier-baselines/sdcg'/lib;out.mkdir(parents=True)
 initial=out/'initial.json';audit=out/'instrumentation.json';spec=out/'spec.json';write(spec,{'root':str(root),'files':sc['files'],'initial':str(initial),'audit':str(audit),'ignored':str(out/'instrumenter-ignore.json')})
 st=c.run('sdcg-instrument-'+lib,[c.machine['nodeTest'],ROOT/'src/baselines/instrument_coverage.js',spec],ROOT,{'NODE_PATH':cfg['coverageNodeModules']})
 if st['exitCode']:return {'valid':False,'stages':[st],'reason':'Independent Istanbul instrumentation failed'}
 assert all(x['originalSha256']==sc['hashes'][x['file']] for x in read(audit))
 observed=out/'observed';st2=c.run('sdcg-profile-'+lib,q['command'],root,{'NODE_OPTIONS':'--require '+str(ROOT/'scripts/harness/istanbul_preload.cjs'),'HYBRID_ISTANBUL_OUT':str(observed)})
 if not same(q['original'],st2):return {'valid':False,'stages':[st,st2],'reason':'Instrumented full suite differs'}
 coverage=read(initial)
 for file in observed.glob('*.json'):
  for name,value in read(file).items():
   if name not in coverage:continue
   expected=coverage[name];assert expected['fnMap']==value['fnMap'],'Istanbul function map changed'
   for counter in ['s','f']:
    for k,n in value[counter].items():expected[counter][k]+=n
   for k,counts in value['b'].items():expected['b'][k]=[a+b for a,b in zip(expected['b'][k],counts)]
 assert any(n>0 for v in coverage.values() for n in v['f'].values()),'No scoped production exercise'
 # Every measured function must be accounted for, but "absent from fnMap" is
 # not by itself a mapping loss. Istanbul deliberately skips nodes guarded by
 # `istanbul ignore next|file` (morgan's on-finished/defer is one), and the
 # instrumenter itself is asked which nodes those are. Only functions that are
 # absent *and* not instrumenter-ignored fail qualification.
 from .coverage_map import load_ignored,map_manifest
 mapped=map_manifest(read(q['functions'])['functions'],coverage,root,load_ignored(out/'instrumenter-ignore.json'))
 path=out/'coverage-final.json';write(path,coverage);write(out/'qualification.json',{'scopeSha256':sha(q['scope']),'instrumentationSha256':sha(audit),'mapping':mapped['totals'],'unmappedFunctionIds':[x['id'] for x in mapped['missing']],'unmappedDetail':mapped['missing'][:20],'instrumenterIgnored':mapped['ignored'],'filesAbsentFromCoverage':mapped['filesAbsentFromCoverage'],'policy':'A function absent from fnMap is classified as instrumenter-ignored only when re-instrumenting the same source with the ignore keyword neutralised makes it appear. Ignored functions have no measurement by construction, so SDCG treats them as uncovered; the count is reported instead of being absorbed as a zero.','producer':'Pinned Istanbul instrumenter, offline exact .js scope; no independent truth file read'})
 return {'valid':not mapped['missing'],'stages':[st,st2],'coverage':str(path),'coverageRoot':str(root),'mapping':mapped['totals'],'instrumenterIgnoredCount':len(mapped['ignored']),'reason':None if not mapped['missing'] else '%d of %d measured functions are absent from fnMap and are not explained by an istanbul-ignore hint'%(len(mapped['missing']),mapped['totals']['measured'])}

def build(c,lib,q,method,analysis,tag,instrument=False):
 if not analysis['valid']:return {'valid':False,'reason':'Fresh baseline analysis failed qualification','analysis':analysis}
 lab=variant_directory(c,tag);shutil.copytree(str(ROOT/'src/transformer'),str(lab),ignore=shutil.ignore_patterns('node_modules','__pycache__'));(lab/'node_modules').symlink_to(c.machine['transformerNodeModules']);target=clone(q.get('deployment',q['root']),lab/'Data'/lib);sc=read(q['scope']);register_recovery(c,target,lab)
 (target/'dep_list.txt').write_text('\n'.join(x['path'].split('node_modules/',1)[1] for x in sc['dependencies'])+'\n');(target/'coverage').mkdir(exist_ok=True)
 loads=lab/'loads'/lib
 if instrument:loads.mkdir(parents=True)
 if method=='sscg':shutil.copy2(analysis['graph'],str(target/'sscg_path.csv'))
 else:
  relocated={}
  for name,value in read(analysis['coverage']).items():
   rel=Path(name).relative_to(analysis['coverageRoot']);value['path']=str(target/rel);relocated[str(target/rel)]=value
  write(target/'coverage/coverage-final.json',relocated)
 stage=c.run(tag+'-transform',[c.machine['nodeTest'],'deboater.js',method,lib],lab,{'SQJ_SCOPE_FILES':q['scope'],'STUBBIFIER_INSTRUMENTATION':'1' if instrument else '0','STUBBIFIER_RESULT_ROOT':lab/'Data','STUBBIFIER_LOAD_ROOT':lab/'loads','STUBBIFIER_RETAIN_ROOTS':json.dumps(retained_paths(c,lib,target)),'STUBBIFIER_EMPTY_SSCG_CERTIFICATE':analysis.get('emptyGraphCertificate','')})
 tested=target
 if q.get('deployment'):
  from .baselines import harness
  tested=harness(c,lib,q,target,tag+'-core')
 errors=re.findall(r'ERROR:.*|Yikes.*',Path(stage['log']).read_text(errors='replace'));core=c.run(tag+'-core',q['command'],tested,{'HYBRID_PAYLOAD_OUT':loads} if instrument else None) if stage['exitCode']==0 and not errors else None
 return {'library':lib,'method':method,'valid':not errors and same(q['original'],core),'analysis':analysis,'transform':stage,'core':core,'coreValidationRoot':str(tested),'target':str(target),'lab':str(lab),'loads':str(loads) if instrument else None,'coldDeploymentMeasured':True,'generatedRootCharacters':len(str(lab)),'errors':errors,'scopeSha256':sha(q['scope'])}
