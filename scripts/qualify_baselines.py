#!/usr/bin/env python3
"""Server-only native adapter qualifications; preserve each run independently."""
import argparse,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context
from experiments.admission import units
from experiments.baselines import run
p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--library');p.add_argument('--methods',nargs='+',choices=['depp','mininode-fine','mininode-coarse'],default=['depp','mininode-fine','mininode-coarse']);a=p.parse_args()
c=Context(a.run_id);c.record['executionPolicy']='supplement-only: native adapter qualification; no historical primary table resampling'
if a.library:c.manifest=[r for r in c.manifest if r['library']==a.library]
try:units(c);run(c,a.methods);c.finish()
except Exception:c.record.update(status='failed',error=traceback.format_exc());c.save();raise
print(c.out)
