#!/usr/bin/env python3
"""Validate the current transformer/timer with an explicitly identified prior profile."""
import argparse,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import ROOT,Context,read,write,sha,snapshot
from experiments.rq1.run import build
p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--evidence-run',required=True);p.add_argument('--graph-run',required=True);p.add_argument('--library',required=True);a=p.parse_args()
c=Context(a.run_id);prior=(ROOT/'runs'/a.evidence_run).resolve();graphroot=(ROOT/'runs'/a.graph_run).resolve()
assert ROOT/'runs' in prior.parents and ROOT/'runs' in graphroot.parents
cfg=c.machine['targets'][a.library];lib=a.library;root=Path(cfg['root']);scope=prior/'inputs'/(lib+'-scope.json')
sc=read(scope);assert all(sha(root/n)==h for n,h in sc['hashes'].items())
row=next(r for r in read(prior/'preparation.json')['rows'] if r['library']==lib);assert row['status']=='qualified-for-core-pilot'
q={'root':root,'scope':scope,'allow':prior/'inputs'/(lib+'-published.json'),'functions':prior/'inputs'/(lib+'-functions.json'),'coreHits':str(prior/'truth'/(lib+'-core-hits.json')),'original':row['originalCore'],'command':cfg['command']}
mapped=graphroot/'rq1/dynamic'/('rq1-profile-'+lib+'-mapped.json');assert mapped.is_file()
write(c.out/'reused-profile.json',{'graph':str(mapped),'sha256':sha(mapped),'sourceScope':str(scope),'scopeSha256':sha(scope),'scope':'Cached-profile code smoke test only; no new dynamic-analysis or primary timing claim'})
c.inputSnapshots[str(root)]=snapshot(root)
result=build(c,lib,q,'nodeprof-only',None,{'mapped':str(mapped)},'current-nodeprof-smoke')
assert result['valid'] and result['targetExtraction']['exitCode']==0
write(c.out/'smoke.json',result);c.record['stages'].append({'name':'cached-profile-transformer-smoke','status':'passed'});c.finish();print(c.out)
