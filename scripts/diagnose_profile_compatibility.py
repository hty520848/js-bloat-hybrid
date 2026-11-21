#!/usr/bin/env python3
"""Non-formal runtime diagnostic. Never changes a target or weakens assertions."""
import argparse,json,sys,traceback
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import Context,clone,write,sha,same

def main():
 p=argparse.ArgumentParser();p.add_argument('--run-id',required=True);a=p.parse_args()
 c=Context(a.run_id);rows=[]
 try:
  for lib in ['body-parser','redux','css-loader']:
   q=c.machine['targets'][lib]
   source=Path(q['root']);target=clone(source,c.work/'controls'/lib)
   scope_path=Path('{{ROOT}}/js-bloat-hybrid/runs/formal-20261027-001/inputs')/(lib+'-scope.json')
   scope=json.loads(scope_path.read_text())
   before={f:sha(target/f) for f in scope['files']}
   args=list(q['command']);timeout=360
   # listTests is a startup diagnosis only, never accepted as a full-suite result.
   if lib=='css-loader':args+=['--listTests'];timeout=180
   normal=c.run('normal-'+lib,args,target,timeout=timeout)
   other=[c.machine['graalNode']]+args[1:]
   graal=c.run('plain-graal-'+lib,other,target,timeout=timeout)
   after={f:sha(target/f) for f in scope['files']}
   rows.append({'library':lib,'diagnosticOnly':True,'fullSuite':lib!='css-loader','normal':normal,'plainGraal':graal,'sameCompleteSignature':same(normal,graal),'productionUnchanged':before==after,'sourceHashes':before})
   write(c.out/'compatibility.json',rows)
  c.record.update(status='diagnostics-completed',scientificExperiment=False);c.save()
 except Exception:
  c.record.update(status='failed',error=traceback.format_exc());c.save();raise
 print(c.out)
if __name__=='__main__':main()
