#!/usr/bin/env python3
"""Reviewer 2.3.4: reconcile this run against the published numbers.

The manuscript reports slightly different SSCG/SDCG values from the Stubbifier
paper. The honest answer needs a table with three columns - published, measured,
difference - and a reason per row, not a sentence in the response letter. This
script builds that table from whatever the run produced:

  * transformation size and reduction (table 3 of the manuscript)
  * MECS per library and arm (table 4)
  * per-client loading and execution time (tables 5 and 6)
  * the own-method phase split (table 7)

Cells listed in ``knownDiscrepancies`` of the manifest are reported but marked
``excluded``: the submitted manuscript is internally inconsistent there (a
zero row, copied columns, a 4x gap between two nearly identical stub sets), so
matching them is not a goal and pretending otherwise would be worse than
saying so. Averages are recomputed here instead of copied from the paper.
"""
import argparse,sys,json,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import ROOT,read,write

def pct(measured,published):
    if published in (None,0) or measured is None:return None
    return round(100.0*(measured-published)/published,3)

def band(value):
    if value is None:return 'not-comparable'
    a=abs(value)
    if a<=1:return 'within-1pct'
    if a<=5:return 'within-5pct'
    if a<=10:return 'within-10pct'
    if a<=15:return 'within-15pct'
    return 'beyond-15pct'

p=argparse.ArgumentParser()
p.add_argument('--run-id',required=True)
p.add_argument('--manifest',default=str(ROOT/'datasets/manifests/stubbifier-published.json'))
p.add_argument('--mecs-cells')
p.add_argument('--components')
p.add_argument('--costs')
p.add_argument('--runtime')
a=p.parse_args()
run=ROOT/'runs'/a.run_id
published=read(a.manifest)
apps=published['applications']

sources={
 'mecs':Path(a.mecs_cells) if a.mecs_cells else next((run/x for x in ['stubbifier-baselines/rq2-loading-cells.json','rq2/loading-cells.json'] if (run/x).is_file()),None),
 'components':Path(a.components) if a.components else (run/'rq1/components.json' if (run/'rq1/components.json').is_file() else None),
 'costs':Path(a.costs) if a.costs else (run/'rq4/preparation-cost.json' if (run/'rq4/preparation-cost.json').is_file() else None),
 'runtime':Path(a.runtime) if a.runtime else (run/'rq3/runtime.json' if (run/'rq3/runtime.json').is_file() else None),
}
excluded_scopes=[d['scope'] for d in published.get('knownDiscrepancies',[])]

def is_excluded(lib,arm,kind):
    for d in published.get('knownDiscrepancies',[]):
        scope=d['scope'].lower()
        if lib.lower() not in scope:continue
        arm_agnostic=any(token in scope for token in ('all three arms','all libraries','table 4','table 5'))
        if arm and not arm_agnostic and arm.lower() not in scope:continue
        return d['classification']
    return None

rows=[]

# --- MECS (manuscript table 4) ---
if sources['mecs']:
    cells=read(sources['mecs']).get('cells',[])
    for cell in cells:
        lib=cell.get('library');arm=cell.get('arm') or cell.get('method')
        pub=apps.get(lib,{}).get('mecs',{}).get(arm)
        measured=cell.get('meanMECS')
        delta=pct(measured,pub)
        rows.append({'kind':'mecs','library':lib,'arm':arm,'published':pub,'measured':measured,'deltaPercent':delta,'band':band(delta),
                     'publishedTable':'manuscript table 4','workloads':cell.get('eligibleWorkloads'),
                     'excludedReason':is_excluded(lib,arm,'mecs')})

# --- transformation size (manuscript table 3) ---
if sources['components']:
    for b in read(sources['components']):
        lib=b.get('library');arm=b.get('arm');size=b.get('size') or {}
        pub=apps.get(lib,{}).get('ts',{}).get(arm)
        measured=round(size.get('transformedJSBytes',0)/1024.0,2) if size else None
        delta=pct(measured,pub)
        rows.append({'kind':'transformationSize','library':lib,'arm':arm,'published':pub,'measured':measured,'deltaPercent':delta,'band':band(delta),
                     'publishedTable':'manuscript table 3','validation':b.get('valid'),'excludedReason':None})
        pred=apps.get(lib,{}).get('reductionPercent',{}).get(arm)
        mred=size.get('reductionPercent')
        rows.append({'kind':'reductionPercent','library':lib,'arm':arm,'published':pred,'measured':round(mred,2) if mred is not None else None,
                     'deltaPercent':round(mred-pred,2) if (mred is not None and pred is not None) else None,'band':None,
                     'publishedTable':'manuscript table 3','note':'percentage-point difference, not a relative change'})

# --- own-method phase split (manuscript table 7) ---
if sources['costs']:
    best={}
    for r in read(sources['costs']).get('rows',[]):
        if r.get('valid') and r.get('arm')=='hybrid':
            best.setdefault(r['library'],r)
    for lib,r in sorted(best.items()):
        pub=apps.get(lib,{}).get('ownPhasesSeconds')
        if not pub:continue
        for key,mkey in [('static','staticSeconds'),('dynamic','dynamicSeconds'),('fusionAndTransform','fusionAndTransformSeconds'),('total','phaseSumSeconds')]:
            m=r.get(mkey);q=pub.get(key)
            d=pct(m,q)
            rows.append({'kind':'ownPhase-'+key,'library':lib,'arm':'hybrid','published':q,'measured':round(m,3) if m is not None else None,'deltaPercent':d,'band':band(d),'publishedTable':'manuscript table 7','excludedReason':None})

# --- per-client loading (manuscript table 5) ---
if sources['mecs']:
    per=read(sources['mecs']).get('cells',[])
    bylib={}
    for cell in per:bylib.setdefault(cell.get('library'),{})[cell.get('arm') or cell.get('method')]=cell
    for item in published.get('libraryByClientLoading',[]):
        lib=item['library']
        for arm in ('sscg','sdcg','hybrid'):
            cell=bylib.get(lib,{}).get(arm)
            if not cell:continue
            detail={x.get('workload') or x.get('client'):x.get('MECS') for x in cell.get('workloads') or cell.get('clients') or []}
            measured=detail.get(item['client'])
            pub=item[arm]['LCS']
            d=pct(measured,pub)
            rows.append({'kind':'clientMECS','library':lib,'arm':arm,'client':item['client'],'published':pub,'measured':measured,'deltaPercent':d,'band':band(d),
                         'publishedTable':'manuscript table 5','excludedReason':is_excluded(lib,arm,'mecs')})

summary={}
for r in rows:
    k=r['kind'];summary.setdefault(k,{})
    b=r.get('band')
    if b:summary[k][b]=summary[k].get(b,0)+1
avg={}
for kind in ('mecs','transformationSize','clientMECS'):
    for arm in ('sscg','sdcg','hybrid'):
        vals=[r['measured'] for r in rows if r['kind']==kind and r['arm']==arm and r.get('measured') is not None and not r.get('excludedReason')]
        pv=[r['published'] for r in rows if r['kind']==kind and r['arm']==arm and r.get('published') is not None and not r.get('excludedReason')]
        if vals:avg.setdefault(kind,{})[arm]={'measuredMean':round(sum(vals)/len(vals),2),'publishedMean':round(sum(pv)/len(pv),2) if pv else None,'n':len(vals)}

payload={'status':'completed','runId':a.run_id,'sources':{k:(str(v) if v else None) for k,v in sources.items()},
         'rows':rows,'bandCounts':summary,'armMeans':avg,
         'knownDiscrepancies':published.get('knownDiscrepancies',[]),
         'reading':'deltaPercent is relative to the published value. Cells with excludedReason are reported but never counted as agreement or disagreement, because the manuscript is internally inconsistent there. Matching the published numbers is not the goal; explaining a difference is.'}
write(run/'reconciliation.json',payload)

lines=['# 与 Stubbifier 已发表数值的对账','','运行：`'+a.run_id+'`　口径：相对偏差，排除项不计入一致性统计。','']
for kind,label in [('mecs','库级 MECS（稿件表 4）'),('transformationSize','转换后体积（稿件表 3）'),('clientMECS','逐客户端 MECS（稿件表 5）')]:
    subset=[r for r in rows if r['kind']==kind]
    if not subset:continue
    lines+=['## '+label,'','| 库 | 臂 | 已发表 | 本次 | Δ% | 区间 | 说明 |','|---|---|---:|---:|---:|---|---|']
    for r in sorted(subset,key=lambda x:(x['library'],x['arm'])):
        lines.append('| {} | {} | {} | {} | {} | {} | {} |'.format(r['library'],r['arm'],r.get('published'),r.get('measured'),r.get('deltaPercent'),r.get('band') or '',r.get('excludedReason') or ''))
    lines.append('')
if summary:
    lines+=['## 一致性统计','','| 指标 | '+' | '.join(['within-1pct','within-5pct','within-10pct','within-15pct','beyond-15pct'])+' |','|---|'+'---|'*5]
    for kind,c in summary.items():
        lines.append('| {} | {} |'.format(kind,' | '.join(str(c.get(b,0)) for b in ['within-1pct','within-5pct','within-10pct','within-15pct','beyond-15pct'])))
    lines.append('')
lines+=['## 稿件内部的不一致（已知，不作为对账目标）','']
for d in published.get('knownDiscrepancies',[]):
    lines+=['- **'+d['scope']+'**：'+d['observation']+'　→ '+d['classification']]
(run/'reconciliation.md').write_text('\n'.join(lines)+'\n',encoding='utf-8')
print(json.dumps({'run':a.run_id,'rows':len(rows),'out':str(run/'reconciliation.json')},ensure_ascii=False))
