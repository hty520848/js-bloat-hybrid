#!/usr/bin/env python3
"""Reviewer 2.1 / 2.2.1: close the static-edge adjudication loop.

The benchmark writes every predicted edge that the annotation archive does not
label into ``adjudication-queue.json`` and stops there. Until those edges are
judged, precision is only an interval: lower bound assumes they are all wrong,
upper bound assumes they are all right. A interval cannot support a claim that
the static component improved accuracy.

This script closes the loop:

  1. ``--template`` writes an empty verdict sheet for the queue (CSV, so it can
     be filled in a spreadsheet or two annotators can work in parallel).
  2. ``--verdicts`` reads a filled sheet, validates that every queued edge has
     exactly one verdict and no verdict refers to an edge outside the queue,
     and then recomputes the per-(file, arm) table with adjudicated edges folded
     into TP / FP.
  3. With two sheets it reports Cohen's kappa on the overlapping edges, so the
     label quality is reported rather than asserted.

Nothing is silently accepted: a verdict outside {TRUE, FALSE} or a missing edge
fails the run instead of being dropped.
"""
import argparse,csv,sys,json,traceback
from pathlib import Path
from collections import defaultdict
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import ROOT,read,write

VALID={'TRUE','FALSE','UNJUDGED'}

def load_queue(path):
    rows=read(path)
    return {(r['file'],r['arm'],r['edge']):r for r in rows}

def read_sheet(path):
    verdicts={}
    with open(path,newline='',encoding='utf-8') as f:
        for i,row in enumerate(csv.DictReader(f),start=2):
            key=(row.get('file','').strip(),row.get('arm','').strip(),row.get('edge','').strip())
            verdict=(row.get('verdict') or '').strip().upper()
            if not any(key):continue
            if verdict not in VALID:raise ValueError('Row {}: verdict must be TRUE/FALSE/UNJUDGED, got {!r}'.format(i,row.get('verdict')))
            if key in verdicts and verdicts[key]['verdict']!=verdict:raise ValueError('Conflicting verdicts for {}'.format(key))
            verdicts[key]={'verdict':verdict,'note':(row.get('note') or '').strip(),'adjudicator':(row.get('adjudicator') or '').strip()}
    return verdicts

def kappa(a,b):
    keys={k for k in a if k in b and a[k]['verdict']!='UNJUDGED' and b[k]['verdict']!='UNJUDGED'}
    if not keys:return None,0
    n=len(keys);agree=sum(1 for k in keys if a[k]['verdict']==b[k]['verdict'])
    po=agree/n
    pa=sum(1 for k in keys if a[k]['verdict']=='TRUE')/n;pb=sum(1 for k in keys if b[k]['verdict']=='TRUE')/n
    pe=pa*pb+(1-pa)*(1-pb)
    return (None if pe==1 else round((po-pe)/(1-pe),4)),n

p=argparse.ArgumentParser()
p.add_argument('--run-id',required=True)
p.add_argument('--queue',help='defaults to runs/<id>/rq1/adjudication-queue.json')
p.add_argument('--benchmark',help='defaults to runs/<id>/rq1/static-benchmark.json')
p.add_argument('--template')
p.add_argument('--verdicts')
p.add_argument('--second-verdicts')
p.add_argument('--output',help='defaults to runs/<id>/rq1/adjudicated-static-benchmark.json')
a=p.parse_args()

queue_path=Path(a.queue) if a.queue else ROOT/'runs'/a.run_id/'rq1/adjudication-queue.json'
bench_path=Path(a.benchmark) if a.benchmark else ROOT/'runs'/a.run_id/'rq1/static-benchmark.json'
queue=load_queue(queue_path)

if a.template:
    out=Path(a.template);out.parent.mkdir(parents=True,exist_ok=True)
    with open(out,'w',newline='',encoding='utf-8') as f:
        w=csv.writer(f);w.writerow(['file','arm','edge','verdict','note','adjudicator'])
        for (fname,arm,edge) in sorted(queue):
            w.writerow([fname,arm,edge,'UNJUDGED','',''])
    print('template',out,'edges',len(queue));sys.exit(0)

if not a.verdicts:raise SystemExit('--verdicts or --template is required')

try:
    verdicts=read_sheet(a.verdicts)
    missing=[k for k in queue if k not in verdicts or verdicts[k]['verdict']=='UNJUDGED']
    extra=[k for k in verdicts if k not in queue]
    if extra:raise ValueError('{} verdicts refer to edges outside the queue, e.g. {}'.format(len(extra),extra[:3]))
    bench=read(bench_path)
    rows=bench['rows']
    # Fold adjudicated edges into the known-confusion counts. A TRUE verdict
    # means the annotation archive missed a real edge, so it enters TP and is
    # added to the recall denominator; a FALSE verdict enters the known FP set.
    delta=defaultdict(lambda:{'TP':0,'FP':0})
    for key,item in verdicts.items():
        if item['verdict']=='UNJUDGED':continue
        fname,arm,_=key
        delta[(fname,arm)]['TP' if item['verdict']=='TRUE' else 'FP']+=1
    adjudicated=[]
    for row in rows:
        d=delta.get((row['file'],row['arm']),{'TP':0,'FP':0})
        predicted=row['predicted'];unjudged=row['unjudged']
        known_tp=row['TP'];known_fp=row['knownFP']
        tp=known_tp+d['TP'];fp=known_fp+d['FP']
        # Edges still unjudged after folding in the sheet. Precision is exact
        # only when nothing is left over, which is what closes the interval.
        remaining=unjudged-d['TP']-d['FP']
        exact=remaining==0
        denom_recall=row['knownPositiveCount']+d['TP']
        adjudicated.append(dict(row,adjudicatedTP=d['TP'],adjudicatedFP=d['FP'],TP=tp,knownFP=fp,remainingUnjudged=remaining,
            precisionExact=(tp/predicted) if predicted and exact else None,
            precisionLowerBound=tp/predicted if predicted else None,
            precisionUpperBound=(tp+remaining)/predicted if predicted else None,
            recallVsAnnotation=tp/denom_recall if denom_recall else None,
            recallDenominator='annotation positives plus adjudicated-true edges not in the annotation',
            adjudicationComplete=exact))
    k,n=None,0
    if a.second_verdicts:
        k,n=kappa(verdicts,read_sheet(a.second_verdicts))
    cells=[]
    for fname in sorted({r['file'] for r in adjudicated}):
        for arm in sorted({r['arm'] for r in adjudicated if r['file']==fname}):
            group=[r for r in adjudicated if r['file']==fname and r['arm']==arm]
            if len(group)!=1:continue
            cells.append(group[0])
    payload={'status':'completed' if not missing else 'incomplete','queueEdges':len(queue),
             'judgedEdges':len(queue)-len(missing),'missingVerdicts':len(missing),'missingExamples':[list(x) for x in missing[:10]],
             'cohensKappa':k,'kappaOverlapEdges':n,
             'cells':cells,'benchmark':str(bench_path),'verdictSheet':str(a.verdicts),
             'boundary':'Precision is exact only for cells whose whole prediction set is adjudicated (adjudicationComplete true). Recall uses annotation positives plus adjudicated-true edges; it is not comparable to a recall computed against the annotation alone.'}
    out=Path(a.output) if a.output else ROOT/'runs'/a.run_id/'rq1/adjudicated-static-benchmark.json'
    write(out,payload)
    print(json.dumps({'out':str(out),'judged':payload['judgedEdges'],'queue':payload['queueEdges'],'kappa':k},ensure_ascii=False))
    if missing:sys.exit(2)
except Exception:
    traceback.print_exc();sys.exit(1)
