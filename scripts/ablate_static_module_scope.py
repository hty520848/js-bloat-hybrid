#!/usr/bin/env python3
"""Reviewer 2.2.1: static ablation on material that can actually exercise it.

Why the historical benchmark cannot answer the question
-------------------------------------------------------
``static-benchmark.py`` runs 26 SunSpider programs. Each is a single file, and
the analysis is run with ``SQJ_SCOPE_FILES`` set to the whole program, so every
parsed file is inside the scope. Under those conditions ``full`` and
``no-module-filter`` agree on all 26 programs, and they agree for a structural
reason: the module-scope switch removes call sites that live outside the
production scope, and no such call site exists.

What this supplement does
-------------------------
It keeps the analysis input, scope manifest, Node version and transformer
fixed, and parses *additional* roots that sit outside the scope: the client tree
that owns the library (its own sources and, most importantly, its tests). The
module-scope switch now has real out-of-scope call sites to remove, so the 2x2
becomes estimable:

    arm                  index   module scope
    mcg-only               on       on
    mcg-no-index           off      on
    mcg-no-module-filter   on       off
    mcg-no-both            off      off

Reported per (library, material): edges by caller scope, edges by callee scope,
and the attributable effects with their signs. Counts only: scope membership is
a manifest property, not a truth judgement, so this file never claims precision
or recall. Pair it with ``adjudicate_edges.py`` before quoting accuracy.
"""
import argparse,sys,traceback,json
from pathlib import Path
from collections import Counter
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context,ROOT,read,write
from experiments.admission import units
from experiments.rq1.run import static
from experiments.rq1.static_benchmark import ARMS

# Four cells estimate the two runtime switches. `no-file-scope` estimates the
# step the paper actually claims (确定分析文件范围): it drops the scope manifest
# so the whole package, including tests and dev-only sources, is analysed.
ARMS_HERE=dict(ARMS);ARMS_HERE['no-file-scope']={}
from experiments.static_scope import classify

MATERIALS={
 'client':'the bound client tree: the consumer sources and tests that belong to the library, which is where out-of-scope call sites really come from',
 'client-node-modules':'the bound client node_modules: every installed module visible to the analysis, most expensive',
 'tarball':'published package only; documents the degenerate case where the switch cannot act',
}

p=argparse.ArgumentParser()
p.add_argument('--run-id',required=True)
p.add_argument('--material',choices=list(MATERIALS),default='client')
p.add_argument('--library',action='append',default=[])
p.add_argument('--clients',type=int,default=1)
p.add_argument('--clients-from',default=str(ROOT/'artifacts/revision-20261025b/consolidated-client-index-001.json'),help='consolidated client index used to reconstruct the frozen cohort')
a=p.parse_args()

c=Context(a.run_id);c.record['executionPolicy']='Supplement: static component ablation on multi-module material; edge counts by scope, no primary-table inference'
if a.library:c.manifest=[x for x in c.manifest if x['library'] in set(a.library)]
try:
 units(c)
 if a.material!='tarball' and not getattr(c,'clients',None):
  from experiments.clients import reuse
  reuse(c,a.clients_from)
  write(c.out/'client-reuse.json',{'source':a.clients_from,'rows':c.clientReuse})
 rows=[]
 for lib,q in sorted(c.qualified.items()):
  scope_files=set(read(q['scope'])['files'])
  materials=[]
  if a.material=='tarball':materials=[('tarball',[])]
  else:
   from experiments.clients import bind
   for i,client in enumerate([x for x in c.clients.get(lib,[]) if x.get('methodComparisonEligible',True)][:a.clients]):
    bound=bind(c,client['cfg'],q['deployment'],'ablate-'+lib+'-'+str(i))
    extra=[str(Path(bound)/'node_modules')] if a.material=='client-node-modules' else [str(bound)]
    materials.append((client['name'],extra))
  if not materials:
   rows.append({'library':lib,'material':a.material,'status':'no-material','reason':'No eligible client available for this material'});write(c.out/'rq1/static-ablation-scope.json',{'status':'running','rows':rows});continue
  for material_name,extra_dirs in materials:
   record={'library':lib,'material':a.material,'materialRoot':material_name,'parseExtraDirs':extra_dirs,'arms':{}}
   edge_sets={}
   for arm in ARMS_HERE:
    tag='ablate-'+lib+'-'+arm+'-'+str(len(rows))
    try:
     env={'MCG_PARSE_EXTRA_DIRS':json.dumps(extra_dirs)} if extra_dirs else None
     stage=static(c,lib,q,arm,tag,env,ablation=True)
     graph=read(stage['graph']) if Path(stage['graph']).is_file() else []
     edges=[e for e in graph if isinstance(e,str)]
     edge_sets[arm]=set(edges)
     record['arms'][arm]=dict(classify(edges,scope_files,lib,q['root']),valid=stage['valid'],profileStage=stage['stage'],ablation=stage.get('ablation'))
    except Exception:record['arms'][arm]={'valid':False,'error':traceback.format_exc()}
   good={k:v for k,v in record['arms'].items() if v.get('valid')}
   if len(good)==len(ARMS_HERE):
    # The switch is measured by what actually changes between two arms with
    # identical inputs. Counting partition sizes instead would be confounded by
    # the dependency sub-graphs, which are emitted separately from the scoped
    # forest and are not subject to the module filter at all.
    full,noidx,nofilt,noboth=(edge_sets['full'],edge_sets['no-index'],edge_sets['no-module-filter'],edge_sets['no-both'])
    removed_by_filter=sorted(nofilt-full);added_by_filter=sorted(full-nofilt)
    added_by_index=sorted(full-noidx);removed_by_index=sorted(noidx-full)
    def composition(edges):
     c2=classify(edges,scope_files,lib,q['root'])
     return {'edges':len(edges),'inScopeCallers':c2['inScopeCallerEdges'],'outOfScopeCallers':c2['outOfScopeCallerEdges'],'inScopeCallees':c2['inScopeCalleeEdges']}
    record['attribution']={
     'edgesPerArm':{k:len(v) for k,v in edge_sets.items()},
     'moduleFilterRemovedEdges':len(removed_by_filter),
     'moduleFilterAddedEdges':len(added_by_filter),
     'moduleFilterRemovedComposition':composition(removed_by_filter),
     'moduleFilterAddedComposition':composition(added_by_filter),
     'indexAddedEdges':len(added_by_index),
     'indexRemovedEdges':len(removed_by_index),
     'indexAddedComposition':composition(added_by_index),
     'indexRemovedComposition':composition(removed_by_index),
     'interactionEdges':len(full)-len(noboth)-((len(full)-len(noidx))+(len(full)-len(nofilt))),
     # A switch that is never reached and a switch that is reached but never
     # decisive produce the same graph. These counters separate the two.
     'switchReach':{arm:{k:v for k,v in (record['arms'][arm].get('ablation') or {}).items()
                         if k in ('candidateCallEvents','indexBearingCallEvents','rejectedByIndexSwitch',
                                  'rejectedByModuleScope','rejectedOutsideAnalysedFiles','nameBranchTaken',
                                  'indexBranchTaken','emittedEdges','analysedFiles','forestTrees')}
                    for arm in ARMS_HERE},
     'fileScopeAddedEdges':len(edge_sets['no-file-scope']-full),
     'fileScopeRemovedEdges':len(full-edge_sets['no-file-scope']),
     'fileScopeComposition':composition(edge_sets['no-file-scope']-full),
     'fileScopeReading':'no-file-scope drops the paper 2.1 file-range step, so tests and dev-only sources enter the forest. fileScopeRemovedEdges is the call relation the scope decision supplies; fileScopeAddedEdges is what it costs.',
     'samples':{'moduleFilterRemoved':removed_by_filter[:10],'moduleFilterAdded':added_by_filter[:10],'indexAdded':added_by_index[:10],'fileScopeRemoved':sorted(full-edge_sets['no-file-scope'])[:10]},
     'reading':'Edges are compared as sets between arms with identical inputs, so each count is an observed change rather than a partition assumption. moduleFilterRemovedEdges is the false-positive pool the scope switch removes; moduleFilterAddedEdges is what it costs. indexAddedEdges is the call relation the index mapping contributes. Counts only: accuracy still requires adjudicate_edges.py.'}
   else:record['status']='incomplete-arms'
   rows.append(record);write(c.out/'rq1/static-ablation-scope.json',{'status':'running','material':a.material,'materialBoundary':MATERIALS[a.material],'rows':rows})
 summary=[]
 for lib in sorted({r['library'] for r in rows}):
  cells=[r for r in rows if r['library']==lib and r.get('attribution')]
  for key in ['moduleFilterRemovedEdges','moduleFilterAddedEdges','indexAddedEdges','indexRemovedEdges','interactionEdges']:
   values=[x['attribution'][key] for x in cells]
   if values:summary.append({'library':lib,'metric':key,'materials':len(values),'median':sorted(values)[len(values)//2],'min':min(values),'max':max(values)})
 write(c.out/'rq1/static-ablation-scope.json',{'status':'completed','material':a.material,'materialBoundary':MATERIALS[a.material],'rows':rows,'summary':summary,
  'claimBoundary':'Observed set differences between arms sharing identical inputs, plus a scope partition of what changed. Supports or refutes that module scoping removes out-of-scope call sites and that index resolution adds call relations. Does not establish precision or recall on its own.'})
 c.record['stages'].append({'name':'static-ablation-scope','status':'completed' if summary else 'blocked','materials':len(rows),'libraries':len({r['library'] for r in rows})})
 c.finish()
except Exception:
 c.record.update(status='failed',error=traceback.format_exc());c.save();raise
print(c.out)
