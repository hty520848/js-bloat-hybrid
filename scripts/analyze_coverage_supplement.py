#!/usr/bin/env python3
import argparse,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context
from experiments.rq1.client_saturation import run
p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);p.add_argument('--index',required=True);a=p.parse_args();c=Context(a.run_id)
try:run(c,a.index);c.finish()
except Exception:c.record.update(status='failed',error=traceback.format_exc());c.save();raise
print(c.out)
