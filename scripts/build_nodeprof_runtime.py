#!/usr/bin/env python3
"""Build a private Graal21.3/NodeProf candidate from hash-verified inputs.

Linux/Python 3.6+. This does not change machine.local.json or execute study
workloads. Every command, failure and build product remains in a new directory.
"""
import argparse,hashlib,json,os,re,shutil,subprocess,tarfile,traceback,zipfile,time
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 return h.hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__)
 p.add_argument('--input-dir',required=True);p.add_argument('--output-dir',required=True)
 a=p.parse_args();inputs=Path(a.input_dir).resolve();out=Path(a.output_dir).absolute()
 if out.exists():raise ValueError('A new output directory is required: '+str(out))
 out.mkdir(parents=True);record={'status':'running','scientificWorkloadExecuted':False,'commands':[]}
 def save():
  (out/'build-status.json').write_text(json.dumps(record,indent=2)+'\n')
 def run(name,args,cwd=None,timeout=900):
  log=out/(name+'.log');start=time.time()
  with log.open('w') as f:
   result=subprocess.run([str(x) for x in args],cwd=str(cwd or out),stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
  row={'name':name,'args':[str(x) for x in args],'exitCode':result.returncode,'seconds':time.time()-start,'log':str(log),'logSha256':sha(log)}
  record['commands'].append(row);save()
  if result.returncode:raise RuntimeError('Command failed: '+name)
  return log.read_text(errors='replace')
 save()
 try:
  refs=json.loads((inputs/'input-checksums.json').read_text())
  for name,expected in refs.items():
   if sha(inputs/name)!=expected:raise ValueError('Input hash mismatch: '+name)
  record['inputs']=refs;save()
  unpack=out/'graal';unpack.mkdir()
  with tarfile.open(str(inputs/'graalvm-ce-java11-linux-amd64-21.3.0.tar.gz')) as tar:
   for member in tar.getmembers():
    dest=(unpack/member.name).resolve()
    if unpack not in dest.parents:raise ValueError('Unsafe tar path '+member.name)
    if member.issym() or member.islnk():
     link=(dest.parent/member.linkname).resolve() if member.issym() else (unpack/member.linkname).resolve()
     if unpack not in link.parents:raise ValueError('Unsafe tar link '+member.name)
   tar.extractall(str(unpack))
  homes=list(unpack.glob('graalvm-*'))
  if len(homes)!=1:raise ValueError('Ambiguous Graal root')
  home=homes[0]
  run('install-node',[home/'bin/gu','-L','install',inputs/'nodejs-installable-svm-java11-linux-amd64-21.3.0.jar'])
  version=run('node-version',[home/'bin/node','--version']);record['nodeVersion']=version.strip()
  src=out/'source';src.mkdir()
  with zipfile.ZipFile(str(inputs/'nodeprof-652665b.zip')) as z:
   for name in z.namelist():
    if src not in (src/name).resolve().parents:raise ValueError('Unsafe zip path '+name)
   z.extractall(str(src))
  source=next(src.glob('nodeprof.js-*'))
  classes=out/'classes';classes.mkdir()
  java=sorted((source/'src/ch.usi.inf.nodeprof/src').rglob('*.java'))
  # Runtime distributions contain empty optional-SVM placeholder jars. Only
  # the public SDK, Truffle, JavaScript, Node and regex APIs are compilation inputs.
  names={'truffle-api.jar','graaljs.jar','trufflenode.jar','tregex.jar','icu4j.jar'}
  jars=sorted(x for x in home.rglob('*.jar') if x.name in names)
  if {x.name for x in jars}!=names or not all(zipfile.is_zipfile(str(x)) for x in jars):raise ValueError('Missing or invalid compiler API jars')
  sdk=inputs/'graal-sdk-21.3.0.jar'
  if sdk.name not in refs or not zipfile.is_zipfile(str(sdk)):raise ValueError('A verified standalone Graal SDK is required for javac')
  cp=os.pathsep.join(str(x) for x in jars+[sdk])
  proc=inputs/'truffle-dsl-processor-21.3.0.jar'
  run('javac',[home/'bin/javac','-source','8','-target','8','-classpath',cp,'-processorpath',cp+os.pathsep+str(proc),'-d',classes]+java)
  jar=out/'nodeprof.jar';run('jar',[home/'bin/jar','cf',jar,'-C',classes,'.'])
  # Graal's polyglot locator discovers instruments under tools/, separately
  # from the ordinary JVM application classpath.
  tool=home/'tools/nodeprof';tool.mkdir(parents=True)
  shutil.copy2(str(jar),str(tool/'nodeprof.jar'))
  jar=tool/'nodeprof.jar'
  loader=source/'src/ch.usi.inf.nodeprof/js/jalangi.js'
  probe=out/'smoke.js';probe.write_text('function sum(a,b){return a+b;}\nconsole.log("RUNTIME_SMOKE",sum(2,3));\n')
  analysis=out/'smoke-analysis.js';analysis.write_text('(function(){var n=0;J$.analysis={functionEnter:function(){n++;},endExecution:function(){console.log("NODEPROF_ENTRIES",n);}};})();\n')
  text=run('nodeprof-smoke',[home/'bin/node','--vm.classpath='+str(jar),'--experimental-options','--nodeprof',loader,'--analysis',analysis,probe],timeout=120)
  entries=re.search(r'NODEPROF_ENTRIES\s+(\d+)',text)
  if 'RUNTIME_SMOKE 5' not in text or not entries or int(entries.group(1))<1:raise ValueError('Missing instrumented smoke evidence')
  record['runtime']={key:{'path':str(path),'sha256':sha(path)} for key,path in [('graalNode',home/'bin/node'),('nodeprofLoader',loader),('nodeprofJar',jar)]}
  record['status']='smoke-passed';save()
 except Exception:
  record.update(status='failed',error=traceback.format_exc());save();raise
 print(out/'build-status.json')

if __name__=='__main__':main()
