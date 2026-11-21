#!/usr/bin/env python3
"""Run ten-library runtime admission, then RQ1 only if every library qualifies.

No manuscript writes, global runtime replacement, RQ2/RQ3/RQ4 runs, or retries
that replace old observations. Invoke only after manuscript/code review.
"""
import argparse,hashlib,json,re,subprocess,sys,traceback,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]

def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def require(ok,message):
 if not ok:raise ValueError(message)
def sources():
 return {str(p.relative_to(ROOT)):sha(p) for folder in ['src','experiments','scripts','config','tests','datasets'] for p in (ROOT/folder).rglob('*') if p.is_file() and p.suffix in ['.py','.js','.cjs','.json'] and not any(s in p.parts for s in ['node_modules','__pycache__'])}

def main():
 p=argparse.ArgumentParser(description=__doc__)
 for name in ['chain-id','qualification-run','rq1-run','build-status','code-check']:p.add_argument('--'+name,required=True)
 a=p.parse_args()
 for value in [a.chain_id,a.qualification_run,a.rq1_run]:require(bool(re.fullmatch(r'[A-Za-z0-9_.-]+',value)),'Unsafe run ID')
 require(len({a.chain_id,a.qualification_run,a.rq1_run})==3,'Run IDs must be distinct')
 for value in [a.chain_id,a.qualification_run,a.rq1_run]:require(not (ROOT/'runs'/value).exists(),'Run already exists: '+value)
 build=json.loads(Path(a.build_status).read_text());check=json.loads(Path(a.code_check).read_text())
 require(build.get('status')=='smoke-passed','Runtime build/smoke is not qualified')
 require(check.get('status')=='passed' and check.get('checks'),'Server code checks are incomplete')
 for item in check['checks']:require(item['exitCode']==0 and sha(item['log'])==item['logSha256'],'Code-check evidence changed')
 pinned=check['sourceHashes'];require(sources()==pinned,'Source changed after server code checks')
 runtime={k:v['path'] for k,v in build['runtime'].items()}
 for k,v in build['runtime'].items():require(sha(v['path'])==v['sha256'],'Runtime identity changed: '+k)
 installed=Path(runtime['graalNode']).parents[1]/'tools/nodeprof/nodeprof.jar'
 require(installed.is_file() and sha(installed)==sha(runtime['nodeprofJar']),'Discovered NodeProf differs from compiled jar')
 runtime['nodeprofJar']=str(installed)
 out=ROOT/'runs'/a.chain_id;out.mkdir(parents=True)
 record={'status':'running','phase':'runtime-admission','runtime':runtime,'sourceHashes':pinned,'buildStatus':str(Path(a.build_status).resolve()),'buildStatusSha256':sha(a.build_status),'codeCheck':str(Path(a.code_check).resolve()),'codeCheckSha256':sha(a.code_check),'qualificationRun':a.qualification_run,'rq1Run':a.rq1_run,'formalRQ1Started':False,'manuscriptWrites':False}
 def save():
  temp=out/'status.json.tmp';temp.write_text(json.dumps(record,indent=2)+'\n');temp.replace(out/'status.json')
 def run(name,args):
  log=out/(name+'.log');start=time.time()
  with log.open('x') as f:rc=subprocess.call([str(x) for x in args],cwd=str(ROOT),stdout=f,stderr=subprocess.STDOUT)
  record[name]={'command':[str(x) for x in args],'exitCode':rc,'seconds':time.time()-start,'log':str(log),'logSha256':sha(log)};save()
  require(rc==0,'Phase failed: '+name)
 save()
 try:
  args=[sys.executable,ROOT/'scripts/qualify_rq1_runtime.py','--run-id',a.qualification_run]
  for flag,key in [('graal-node','graalNode'),('nodeprof-loader','nodeprofLoader'),('nodeprof-jar','nodeprofJar')]:args+=['--'+flag,runtime[key]]
  run('qualification',args)
  require(sources()==pinned,'Source changed during runtime admission')
  admission=ROOT/'runs'/a.qualification_run/'runtime-admission.json'
  from run_rq1_only import admit
  plan=json.loads((ROOT/'experiments/rq1/ablation-plan-20261102.json').read_text())
  admit(admission,plan)
  record.update(phase='rq1',formalRQ1Started=True);save()
  run('rq1',[sys.executable,ROOT/'scripts/run_rq1_only.py','--run-id',a.rq1_run,'--runtime-qualification',admission])
  result=json.loads((ROOT/'runs'/a.rq1_run/'status.json').read_text())
  record.update(status=result['status'],phase='finished',rq1Status=result['status']);save()
 except Exception:
  record.update(status='blocked',error=traceback.format_exc());save();raise
 print(out/'status.json')

if __name__=='__main__':main()
