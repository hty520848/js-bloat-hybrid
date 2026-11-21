#!/usr/bin/env python3
"""Reviewer 2.2.5: warmup/measurement adequacy on saved paired RQ3 rounds.

Reads an existing rq3/runtime.json (never reruns workloads) and reports, per
cell: residual-warmup check (first measured round vs the rest), alternation
order effect, lag-1 autocorrelation of the signed series, and bootstrap CI
stability when only the first k rounds are used. Descriptive only: rounds are
technical repeats, no population inference.
"""
import argparse,sys,traceback,statistics,random
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context,read,write
p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--runtime-json',required=True);p.add_argument('--bootstrap',type=int,default=5000);a=p.parse_args()
c=Context(a.run_id);c.record['executionPolicy']='Analysis of saved paired rounds; no workload rerun'
def autocorr(v):
 if len(v)<3 or statistics.pstdev(v)==0:return None
 m=statistics.mean(v);num=sum((v[i]-m)*(v[i+1]-m) for i in range(len(v)-1));den=sum((x-m)**2 for x in v)
 return num/den if den else None
def ci(vals,seed,samples):
 rng=random.Random(seed);boots=sorted(statistics.mean([rng.choice(vals) for _ in vals]) for _ in range(samples))
 return [boots[int(.025*len(boots))],boots[int(.975*len(boots))]]
try:
 data=read(a.runtime_json);rows=data.get('rows',[]);seed=data.get('seed',20261025)
 cells={}
 for r in rows:cells.setdefault((r['library'],r['arm'],r['client']),[]).append(r)
 out=[]
 for key,rs in sorted(cells.items()):
  measured=[r for r in rs if not r['warmup'] and r['valid']]
  if not measured:continue
  vals=[r['signedSlowdownPercent'] for r in measured]
  warm=[r for r in rs if r['warmup'] and r['valid']]
  firstOriginal=[r['signedSlowdownPercent'] for r in measured if r['order'][0]=='original']
  firstTransformed=[r['signedSlowdownPercent'] for r in measured if r['order'][0]=='transformed']
  rest=vals[1:]
  restCI=ci(rest,seed,a.bootstrap) if len(rest)>=3 else None
  cis={}
  for k in (3,5,10):
   v=vals[:k]
   if len(v)>=3:cis['first'+str(k)]=ci(v,seed,a.bootstrap)
  item={'library':key[0],'arm':key[1],'workload':key[2],'validMeasuredRounds':len(vals),'validWarmupRounds':len(warm),'plannedMeasuredRounds':data.get('planned') or len(vals),'firstRound':vals[0],'restMedian':statistics.median(rest) if rest else None,'firstRoundOutsideRestCI95':bool(restCI and (vals[0]<restCI[0] or vals[0]>restCI[1])),'restCI95':restCI,'orderFirstOriginalMean':statistics.mean(firstOriginal) if firstOriginal else None,'orderFirstTransformedMean':statistics.mean(firstTransformed) if firstTransformed else None,'orderPairCounts':[len(firstOriginal),len(firstTransformed)],'lag1AutocorrSignedSeries':autocorr(vals),'fullCI95':ci(vals,seed,a.bootstrap) if len(vals)>=3 else None,'bootstrapCIfirstK':cis,'sampleSD':statistics.stdev(vals) if len(vals)>1 else None}
  out.append(item)
 write(c.out/'runtime-stability.json',{'source':a.runtime_json,'cells':out,'seed':seed,'bootstrapSamples':a.bootstrap,'notes':'Rounds are technical repeats; descriptive only. firstRoundOutsideRestCI95 flags residual warmup; |lag1|>=0.5 flags serial dependence; CI-first-k vs fullCI95 shows whether fewer rounds would move the interval.'})
 flaggedWarm=sum(1 for x in out if x['firstRoundOutsideRestCI95']);flaggedSerial=sum(1 for x in out if x['lag1AutocorrSignedSeries'] is not None and abs(x['lag1AutocorrSignedSeries'])>=0.5)
 c.record['stages'].append({'name':'runtime-stability-analysis','status':'completed','cells':len(out),'residualWarmupFlagged':flaggedWarm,'serialDependenceFlagged':flaggedSerial});c.finish()
except Exception:c.record.update(status='failed',error=traceback.format_exc());c.save();raise
print(c.out)
