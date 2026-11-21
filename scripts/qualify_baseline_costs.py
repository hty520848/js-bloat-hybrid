#!/usr/bin/env python3
"""Reviewer 1.14: baseline transformation cost beside the own-method phases.

Reviewer 1.14 asks for RQ4 to compare transformation time with the baseline
methods. The first version of this supplement only covered DepPrune and
Mininode. Those are the external methods reviewer 2.2.4 asked about, but they
are *not* the baselines the manuscript compares against: table 6 sits next to
SSCG and SDCG. A table without those two columns cannot answer 1.14.

``--methods sscg sdcg`` adds both, with a fresh analysis *and* a fresh
transform per repetition, so the analysis cost is charged to the baseline that
actually pays it. The phase boundary is reported per method: SSCG and SDCG
expose one analysis stage plus one transform stage and no internal split, and
that is stated rather than hidden inside a single number.
"""
import argparse,sys,traceback,statistics,shutil
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context,ROOT,read,write,sha
from experiments.admission import units
from experiments.baselines import tool,depp,mininode
from experiments.stubbifier_baselines import sscg,sdcg,build
p=argparse.ArgumentParser()
p.add_argument('--run-id',required=True)
p.add_argument('--methods',nargs='+',choices=['depp','mininode-fine','mininode-coarse','sscg','sdcg'],default=['depp','mininode-fine','mininode-coarse'])
p.add_argument('--repetitions',type=int,default=3)
p.add_argument('--library')
p.add_argument('--own-rq4-run')
p.add_argument('--codeql-root')
p.add_argument('--coverage-node-modules')
p.add_argument('--keep-labs',action='store_true',help='keep baseline transform trees; default hashes then removes them')
a=p.parse_args()
c=Context(a.run_id);c.record['executionPolicy']='Supplement: baseline transformation cost; descriptive repetitions, no primary-table inference'
if a.library:c.manifest=[x for x in c.manifest if x['library']==a.library]
def ensure_cfg():
 if c.machine.get('stubbifierBaselines'):return c.machine['stubbifierBaselines']
 cfg={}
 if 'sscg' in a.methods:
  assert a.codeql_root,'--codeql-root is required when SSCG is requested and stubbifierBaselines is unconfigured'
  root=Path(a.codeql_root).resolve()
  assert (root/'codeql/codeql').is_file() and (root/'codeql-1.26.0').is_dir(),'codeql root must contain codeql/ and codeql-1.26.0/'
  cfg.update({'codeql':str(root/'codeql/codeql'),'searchPath':str(root/'codeql-1.26.0'),'querySha256':sha(ROOT/'src/baselines/stubbifier-recovery.ql')})
 cfg['coverageNodeModules']=a.coverage_node_modules or str(Path(c.machine['targets']['css-loader']['root'])/'node_modules')
 c.machine['stubbifierBaselines']=cfg;write(c.out/'stubbifier-baselines/config.json',cfg);return cfg
def clear_adapter_work(c,lib,method):
 # Adapters assert fresh destinations; each repetition gets a clean private
 # work area. Only this Context's own work paths are ever removed.
 paths=[]
 if method.startswith('mininode-'):
  mode=method.split('-',1)[1];paths=[c.work/'external-inputs'/('mininode-'+mode)/lib,c.work/'external-output'/('mininode-'+mode)/lib]
 elif method=='depp':paths=[c.work/'external-output/depp'/lib,c.work/'depp-metadata'/lib,c.work/'depp-adapted-metadata'/lib,c.work/'depp-projected-metadata'/lib,c.work/'external-validation'/('depp-trace-'+lib)]
 for path in paths:
  if path.exists():
   assert c.work.resolve() in path.resolve().parents and not path.is_symlink()
   shutil.rmtree(str(path))
def drop_lab(c,lab):
 lab=Path(lab)
 if a.keep_labs or not lab.exists():return
 assert c.work.resolve() in lab.resolve().parents and not lab.is_symlink()
 shutil.rmtree(str(lab))
try:
 if any(m in ('sscg','sdcg') for m in a.methods):ensure_cfg()
 units(c);rows=[];tools={}
 if any(m.startswith('mininode-') for m in a.methods):tools['mininode']=tool(c,'mininode')
 if 'depp' in a.methods:tools['DepPrune']=tool(c,'DepPrune')
 for lib,q in sorted(c.qualified.items()):
  for method in a.methods:
   for rep in range(a.repetitions):
    row={'library':lib,'method':method,'repetition':rep}
    try:
     if method in ('sscg','sdcg'):
      analysis=(sscg if method=='sscg' else sdcg)(c,lib,q)
      if not analysis.get('valid'):
       row.update(valid=False,status='analysis-failed',reason=analysis.get('reason'));rows.append(row);write(c.out/'baseline-costs.json',{'status':'running','rows':rows});continue
      out=build(c,lib,q,method,analysis,'cost-'+method+'-'+lib+'-'+str(rep),instrument=False)
      analysis_seconds=sum(float(s.get('seconds') or 0) for s in analysis.get('stages',[]))
      transform_seconds=out.get('transform',{}).get('seconds')
      row.update(valid=bool(out.get('valid')),analysisSeconds=analysis_seconds,transformSeconds=transform_seconds,
                 totalSeconds=(analysis_seconds+(transform_seconds or 0)) if transform_seconds is not None else None,
                 phaseBoundary='Base analysis stage (database creation + query for SSCG, independent Istanbul run for SDCG) plus the transformer stage. The two baselines expose no further internal split; analysis cost is charged to the baseline that pays it.',
                 transformLogSha256=out.get('transform',{}).get('logSha256'))
      drop_lab(c,out.get('lab'))
     else:
      clear_adapter_work(c,lib,method)
      if method=='depp':
       out=depp(c,lib,q,tools)
       lock=out.get('nativeLockStage') or out.get('adapterLockStage') or out.get('projectedLockStage') or {}
       detection=out.get('detection') or {};trace=out.get('trace') or {}
       row.update(valid=bool(out.get('validOutput')),traceSeconds=trace.get('seconds'),lockStageSeconds=lock.get('seconds'),detectionSeconds=detection.get('seconds'),removalSeconds=out.get('removalSeconds'),transformSeconds=(lock.get('seconds') or 0)+(detection.get('seconds') or 0)+(out.get('removalSeconds') or 0),phaseBoundary='DepPrune transform = lock identity + candidate extraction + removal; the strace profile is reported separately as its dynamic-analysis input')
       row['totalSeconds']=row['transformSeconds']+float(row.get('traceSeconds') or 0)
      else:
       out=mininode(c,lib,q,method.split('-',1)[1],tools)
       row.update(valid=bool(out.get('validOutput')),transformSeconds=out['transform'].get('seconds'),analysisSeconds=None,phaseBoundary='Mininode exposes one native analysis+transform stage; no separate phase split')
       row['totalSeconds']=row['transformSeconds']
    except Exception:row.update(valid=False,status='exception',error=traceback.format_exc())
    rows.append(row);write(c.out/'baseline-costs.json',{'status':'running','rows':rows})
 summary=[]
 for lib in sorted({r['library'] for r in rows}):
  for method in sorted({r['method'] for r in rows if r['library']==lib}):
   vals=[r['transformSeconds'] for r in rows if (r['library'],r['method'])==(lib,method) and r.get('transformSeconds') is not None]
   totals=[r['totalSeconds'] for r in rows if (r['library'],r['method'])==(lib,method) and r.get('totalSeconds') is not None]
   analysis=[r.get('analysisSeconds') for r in rows if (r['library'],r['method'])==(lib,method) and r.get('analysisSeconds') is not None]
   summary.append({'library':lib,'method':method,'validRepetitions':len(vals),'medianTransformSeconds':statistics.median(vals) if vals else None,'meanTransformSeconds':statistics.mean(vals) if vals else None,'sampleSD':statistics.stdev(vals) if len(vals)>1 else None,
                   'medianAnalysisSeconds':statistics.median(analysis) if analysis else None,'medianTotalSeconds':statistics.median(totals) if totals else None,'analysisIncluded':bool(analysis)})
 own=None
 if a.own_rq4_run:
  src=ROOT/'runs'/a.own_rq4_run/'rq4/preparation-cost.json'
  if src.is_file():
   r4=[r for r in read(src).get('rows',[]) if r.get('valid')]
   own={'sourceRun':a.own_rq4_run,'perLibraryArm':[{k:r.get(k) for k in ['library','arm','repetition','staticSeconds','dynamicSeconds','sourceMappingSeconds','targetExtractionSeconds','fusionAndTransformSeconds','phaseSumSeconds']} for r in r4]}
  else:own={'sourceRun':a.own_rq4_run,'missing':True}
 write(c.out/'baseline-costs.json',{'status':'completed','repetitions':a.repetitions,'methods':a.methods,'rows':rows,'summary':summary,'ownMethodJoin':own,
  'comparableColumn':'medianTotalSeconds is the column comparable to the own-method phaseSumSeconds; medianTransformSeconds alone understates baselines whose analysis is the expensive part.'})
 c.record['stages'].append({'name':'baseline-transformation-costs','status':'completed','rows':len(rows),'methods':a.methods});c.finish()
except Exception:c.record.update(status='failed',error=traceback.format_exc());c.save();raise
print(c.out)
