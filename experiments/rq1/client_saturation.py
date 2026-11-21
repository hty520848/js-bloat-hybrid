"""Exact five-client order/leave-one-out analysis of saved independent truth.

No tests or primary result measurements are rerun. Function observations are
workload conditioned; these are not branch coverage or semantic reachability.
"""
import itertools
from pathlib import Path
from ..common import ROOT,read,write,sha,same

def run(c,index):
 index=Path(index);data=read(index);assert data['status']=='completed','Client qualification batch is incomplete'
 rows=[];libraries=read(ROOT/'datasets/manifests/clients.json')['libraries']
 for lib,candidates in sorted(libraries.items()):
  cfg=c.machine['targets'][lib];prior=ROOT/'runs'/cfg.get('unitEvidenceRun','formal-readiness-20261025-004');manifest=read(prior/'inputs'/(lib+'-functions.json'))
  scopes={'production':{f['id'] for f in manifest['functions']},'own':{f['id'] for f in manifest['functions'] if f['scope']=='library'}}
  unit=set(read(prior/'truth'/(lib+'-core-hits.json')));clients={};excluded=[];evidence=[]
  for candidate in candidates:
   name=candidate['directory'];ref=next(x for x in data['rows'] if x['library']==lib and x['client']==name);directory=Path(ref.get('runDirectory',str(ROOT/'runs'/ref['runId'])));status=read(directory/'status.json')
   records=read(directory/'client-qualification.json') if (directory/'client-qualification.json').is_file() else []
   record=next((x for x in records if x['library']==lib and x['client']==name),{})
   valid_truth=same(record.get('baseline'),record.get('truth')) and record.get('boundOriginalSourceUnchanged') and record.get('boundInstrumentedSourceUnchanged') and not record.get('unknownFunctionIds') and status['status'] in ['completed','completed-with-gates'] and not status.get('changedInputTrees') and not status.get('changedImplementation')
   if not valid_truth:excluded.append({'client':name,'runId':ref['runId'],'status':ref.get('clientStatus',ref['status'])});continue
   for command in [record['baseline'],record['truth']]:assert sha(command['log'])==command['logSha256']
   frozen=read(directory/'executed-source-sha256.json')
   for helper in ['src/metrics/truth_manifest.js','src/metrics/truth_preload.cjs','src/metrics/scope.js']:assert sha(ROOT/helper)==frozen[helper]
   reuse=next(x for x in read(directory/'unit-evidence-reuse.json') if x['library']==lib);assert reuse['reused'] and reuse['sourceRun']==prior.name
   hitfile=directory/'client-truth'/lib/(name+'-hits.json');hits=set(read(hitfile));assert not {x for x in hits-scopes['production'] if not x.startswith('@file:')};clients[name]=hits
   evidence.append({'client':name,'runId':ref['runId'],'qualificationSha256':sha(directory/'client-qualification.json'),'hitsSha256':sha(hitfile),'targetExercised':record.get('ownFunctionsExercised',0)>0})
  row={'library':lib,'requiredClients':5,'clientsWithValidTruth':len(clients),'qualifiedClients':sum(x['targetExercised'] for x in evidence),'excludedClients':excluded,'evidence':evidence,'functionManifestSha256':sha(prior/'inputs'/(lib+'-functions.json')),'scopes':{}}
  for scope,universe in scopes.items():
   names=sorted(clients);union=set().union(*(clients[n]&universe for n in names)) if names else set();permutations=list(itertools.permutations(names)) if names else [()];curves=[];curves_with_unit=[]
   for order in permutations:
    seen=set();with_unit=unit&universe;a=[0];b=[len(with_unit)]
    for n in order:seen|=clients[n]&universe;with_unit|=clients[n]&universe;a.append(len(seen));b.append(len(with_unit))
    curves.append(a);curves_with_unit.append(b)
   def summarize(curves):return [{'k':k,'minimumObservedFunctions':min(a[k] for a in curves),'meanObservedFunctions':sum(a[k] for a in curves)/len(curves),'maximumObservedFunctions':max(a[k] for a in curves)} for k in range(len(names)+1)]
   row['scopes'][scope]={'universeFunctions':len(universe),'unitObservedFunctions':len(unit&universe),'clientsUnionObservedFunctions':len(union),'unobservedByFiveCandidates':len(universe-union) if len(clients)==5 else None,'additionalBeyondUnit':len(union-unit),'orderPermutations':len(permutations),'clientOnlyCurve':summarize(curves),'unitPlusClientCurve':summarize(curves_with_unit),'leaveOneOut':[{'client':n,'uniqueObservedFunctions':len((clients[n]&universe)-set().union(*(clients[x]&universe for x in names if x!=n)))} for n in names]}
  row['fiveClientEvaluation']='complete-function-observation-matrix' if len(clients)==5 else 'blocked-incomplete-truth';rows.append(row)
 out={'schemaVersion':1,'sourceIndex':str(index),'sourceIndexSha256':sha(index),'rows':rows,'workloadExecutionsRerun':0,'metric':'Independent function-entry observations; no branch-coverage or semantic-unreachability claim','aggregation':'Zero-hit valid workloads remain in coverage curves; incomplete truth is excluded explicitly; target-unexercised clients remain ineligible for method comparison'}
 write(c.out/'rq1/client-coverage-sensitivity.json',out);c.record['stages'].append({'name':'rq1-supplement-client-coverage-sensitivity','status':'passed' if all(r['clientsWithValidTruth']==5 for r in rows) else 'completed-with-gates','completeLibraries':sum(r['clientsWithValidTruth']==5 for r in rows),'workloadExecutionsRerun':0});c.save();return out
