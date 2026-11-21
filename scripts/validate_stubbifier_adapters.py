#!/usr/bin/env python3
"""Synthetic SSCG/SDCG checks, including independent on-demand recovery.

The supplied tool root contains codeql/ and codeql-1.26.0/. Tools are copied
before invocation. No real-library result or timing experiment is rerun.
"""
import argparse,sys,subprocess,traceback,shutil,tarfile
from pathlib import Path
P=Path(__file__).resolve().parents[1];sys.path.insert(0,str(P))
from experiments.common import Context,write,sha
from experiments.stubbifier_baselines import sscg,sdcg,build
from experiments.rq1.run import build as component_build
p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--codeql-root',required=True);a=p.parse_args()
c=Context(a.run_id);c.record['scope']='Synthetic adapter correctness only; no ten-library primary data resampled'
try:
 tools=c.work/'codeql-runtime';subprocess.run(['cp','--reflink=auto','-a',str(Path(a.codeql_root).resolve()),str(tools)],check=True)
 node=c.machine['nodeTest'];modules=Path(c.machine['targets']['css-loader']['root'])/'node_modules';cfg={'codeql':str(tools/'codeql/codeql'),'searchPath':str(tools/'codeql-1.26.0'),'querySha256':sha(P/'src/baselines/stubbifier-recovery.ql'),'coverageNodeModules':str(modules)};c.machine['stubbifierBaselines']=cfg;write(c.out/'validation-tools.json',cfg)
 version=c.run('codeql-version',[cfg['codeql'],'version'],c.work);assert version['exitCode']==0
 root=c.work/'fixture';root.mkdir();write(root/'package.json',{'name':'adapter-correctness-fixture','version':'1.0.0','main':'lib.js'});(root/'test').mkdir()
 (root/'lib.js').write_text('exports.double = function double(x) {\n  return x*2;\n};\nexports.unused = function unused(x) {\n  const y=x;\n  const z=y;\n  const a=z;\n  const b=a;\n  const d=b;\n  return d;\n};\n')
 (root/'test/test.js').write_text('const assert=require("assert"),api=require("..");describe("adapter correctness",()=>{it("preserves behavior",()=>{assert.equal(api.double(2),4);});});\n')
 (root/'dist/runtime').mkdir(parents=True);(root/'dist/runtime/runtime.js').write_text('module.exports=function browserRuntime(x){\n const y=x;\n const z=y;\n const a=z;\n const b=a;\n const d=b;\n return d;\n};\n')
 c.protocol['deploymentRetention']['synthetic-fixture']=['dist/runtime'];write(c.out/'fixture-retention-policy.json',c.protocol['deploymentRetention'])
 providers=c.work/'providers/node_modules';providers.parent.mkdir();subprocess.run(['cp','--reflink=auto','-a',str(Path(c.machine['targets']['morgan']['root'])/'node_modules'),str(providers)],check=True)
 mocha=providers/'mocha/bin/_mocha';command=[node,str(mocha),'test/test.js'];original=c.run('original-fixture',command,root)
 files=['lib.js','dist/runtime/runtime.js'];scope=c.out/'scope.json';write(scope,{'files':files,'hashes':{f:sha(root/f) for f in files},'dependencies':[]});manifest=c.out/'functions.json';spec=c.out/'spec.json';write(spec,{'root':str(root),'scopeFiles':files,'variants':{},'instrument':False,'output':str(manifest)})
 inventory=c.run('fixture-source-inventory',[node,P/'src/metrics/truth_manifest.js',spec],P);assert inventory['exitCode']==0
 deployment=c.work/'deployment';deployment.mkdir()
 for name in files+['package.json']:(deployment/name).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(str(root/name),str(deployment/name))
 archive=c.work/'fixture-package.tgz'
 with tarfile.open(str(archive),'w:gz') as t:
  for name in files+['package.json']:t.add(str(deployment/name),arcname='package/'+name)
 c.manifest=[{'library':'synthetic-fixture','archive':str(archive)}]
 from experiments.common import read
 hits=c.out/'toy-oracle-hits.json';write(hits,[f['id'] for f in read(manifest)['functions'] if f['file']=='lib.js' and f['loc']['start']['line']==1])
 q={'root':root,'original':original,'command':command,'scope':scope,'functions':manifest,'coreHits':str(hits),'deployment':str(deployment),'dependencyBoundary':{'files':files,'packages':[{'path':'','dependencies':[]}]}};rows=[]
 for method,producer in [('sscg',sscg),('sdcg',sdcg)]:
  analysis=producer(c,'synthetic-fixture',q);write(c.out/(method+'-analysis.json'),analysis);assert analysis['valid'],analysis
  if method=='sscg':assert analysis.get('graphRows',0)>0,'SSCG synthetic validation must exercise a non-empty graph (rows=%r); an empty result repeats the pre-fix index-scope failure'%analysis.get('graphRows')
  result=build(c,'synthetic-fixture',q,method,analysis,'synthetic-'+method);rows.append(result);write(c.out/'adapter-correctness.json',rows);assert result['valid'],result
  assert sha(Path(result['target'])/'dist/runtime/runtime.js')==sha(root/'dist/runtime/runtime.js'),'Retained browser source changed'
  assert not (Path(result['target'])/'test').exists(),'Unit harness leaked into deployment'
  recovery=c.run(method+'-recovery-check',[node,'-e','const assert=require("assert"),api=require(process.argv[1]);assert.equal(api.double(2),4);assert.equal(api.unused(3),3);',result['target']],c.work);assert recovery['exitCode']==0
 graph=c.out/'toy-empty-static-graph.json';write(graph,[]);component=component_build(c,'synthetic-fixture',q,'mcg-only',{'graph':str(graph)},None,'synthetic-own-component');assert component['valid'],component
 assert sha(Path(component['target'])/'dist/runtime/runtime.js')==sha(root/'dist/runtime/runtime.js')
 assert sum(component['coreConditionedConfusion'].values())==3,'Retained functions disappeared from denominator'
 write(c.out/'component-correctness.json',component)
 assert len({r['generatedRootCharacters'] for r in rows+[component]})==1,'Arm-dependent output root length'
 empty_root=c.work/'empty-fixture';empty_root.mkdir();write(empty_root/'package.json',{'name':'empty-sscg-fixture','version':'1.0.0','main':'lib.js'})
 (empty_root/'lib.js').write_text('exports.value = function value(x) {\n  return x;\n};\n')
 (empty_root/'test').mkdir()
 (empty_root/'test/neutral.js').write_text('const assert=require("assert");describe("no production call",()=>{it("holds",()=>assert.equal(1,1));});\n')
 ecommand=[node,str(providers/'mocha/bin/_mocha'),'test/neutral.js'];eoriginal=c.run('original-empty-fixture',ecommand,empty_root)
 efiles=['lib.js'];escope=c.out/'empty-scope.json';write(escope,{'files':efiles,'hashes':{f:sha(empty_root/f) for f in efiles},'dependencies':[]})
 emanifest=c.out/'empty-functions.json';espec=c.out/'empty-spec.json';write(espec,{'root':str(empty_root),'scopeFiles':efiles,'variants':{},'instrument':False,'output':str(emanifest)})
 assert c.run('empty-fixture-source-inventory',[node,P/'src/metrics/truth_manifest.js',espec],P)['exitCode']==0
 edeployment=c.work/'empty-deployment';edeployment.mkdir()
 for name in efiles+['package.json']:(edeployment/name).parent.mkdir(parents=True,exist_ok=True);shutil.copy2(str(empty_root/name),str(edeployment/name))
 earchive=c.work/'empty-fixture-package.tgz'
 with tarfile.open(str(earchive),'w:gz') as t:
  for name in efiles+['package.json']:t.add(str(edeployment/name),arcname='package/'+name)
 c.manifest=c.manifest+[{'library':'empty-sscg-fixture','archive':str(earchive)}]
 c.protocol['deploymentRetention']['empty-sscg-fixture']=[]
 ehits=c.out/'empty-oracle-hits.json';write(ehits,[])
 eq={'root':empty_root,'original':eoriginal,'command':ecommand,'scope':escope,'functions':emanifest,'coreHits':str(ehits),'deployment':str(edeployment),'dependencyBoundary':{'files':efiles,'packages':[{'path':'','dependencies':[]}]}}
 eanalysis=sscg(c,'empty-sscg-fixture',eq);write(c.out/'sscg-empty-analysis.json',eanalysis)
 assert eanalysis['valid'] and eanalysis.get('graphRows')==0 and eanalysis['emptyGraphCertificate'],'Empty probe must reproduce a certified empty graph'
 ebuild=build(c,'empty-sscg-fixture',eq,'sscg',eanalysis,'synthetic-sscg-empty');assert ebuild['valid'],ebuild
 el=read(Path(ebuild['lab'])/'static-mapping-audit.json');assert el.get('qualifiedEmptyGraph') is True and el.get('targets')==[],el
 erecovery=c.run('sscg-empty-recovery-check',[node,'-e','const assert=require("assert"),api=require(process.argv[1]);assert.equal(api.value(3),3);',ebuild['target']],c.work);assert erecovery['exitCode']==0
 rows.append(ebuild);write(c.out/'adapter-correctness.json',rows)
 c.record['stages'].append({'name':'synthetic-stubbifier-adapter-correctness','status':'passed','methods':2,'componentPipeline':True,'coldDeploymentAndRetentionValidated':True,'nonEmptySSCGGraphExercised':True,'emptyGraphCertificateProbed':True,'realLibraryExperimentsRerun':0});c.finish()
except Exception:c.record.update(status='failed',error=traceback.format_exc());c.save();raise
print(c.out)
