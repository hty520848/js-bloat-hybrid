#!/usr/bin/env python3
"""Build a private, checksum-bound Graal23.0.1/NodeProf candidate; no study workloads."""
import argparse,hashlib,json,os,shutil,subprocess,tarfile,time,traceback,zipfile
from pathlib import Path

def sha(p):
 h=hashlib.sha256()
 with Path(p).open('rb') as f:
  for chunk in iter(lambda:f.read(1048576),b''):h.update(chunk)
 return h.hexdigest()

def main():
 p=argparse.ArgumentParser(description=__doc__);p.add_argument('--input-dir',required=True);p.add_argument('--output-dir',required=True);a=p.parse_args()
 inputs=Path(a.input_dir).resolve();out=Path(a.output_dir).absolute();out.mkdir(exist_ok=False)
 home_private=out/'home';home_private.mkdir();tmp=out/'tmp';tmp.mkdir();env=dict(os.environ,HOME=str(home_private),TMPDIR=str(tmp),LANG='C.UTF-8')
 record={'status':'building','scientificWorkloadExecuted':False,'commands':[],'sourceScriptSha256':sha(__file__)}
 def save():
  temp=out/'build-status.json.tmp';temp.write_text(json.dumps(record,indent=2)+'\n');temp.replace(out/'build-status.json')
 def run(label,args,timeout=900):
  log=out/(label+'.log');start=time.time();print('START '+label,flush=True)
  with log.open('x') as f:r=subprocess.run([str(x) for x in args],cwd=str(out),env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
  row={'label':label,'command':[str(x) for x in args],'exitCode':r.returncode,'seconds':time.time()-start,'log':str(log),'logSha256':sha(log)};record['commands'].append(row);save();print('END '+label+' '+str(r.returncode),flush=True)
  if r.returncode:raise RuntimeError('Build stage failed: '+label+'; '+log.read_text(errors='replace')[-2500:])
  return log.read_text(errors='replace')
 save()
 try:
  hashes=json.loads((inputs/'input-checksums.json').read_text())
  for name,digest in hashes.items():
   if sha(inputs/name)!=digest:raise ValueError('Input hash mismatch: '+name)
  record['inputs']=hashes;save();unpack=out/'graal';unpack.mkdir()
  with tarfile.open(str(inputs/'graalvm-community-jdk-17.0.8_linux-x64_bin.tar.gz')) as tar:
   for member in tar.getmembers():
    dest=(unpack/member.name).resolve()
    if unpack not in dest.parents:raise ValueError('Unsafe tar member: '+member.name)
    if member.issym() or member.islnk():
     link=(dest.parent/member.linkname).resolve() if member.issym() else (unpack/member.linkname).resolve()
     if unpack not in link.parents:raise ValueError('Unsafe tar link: '+member.name)
   tar.extractall(str(unpack))
  homes=[x for x in unpack.iterdir() if x.is_dir()];assert len(homes)==1;home=homes[0]
  record['graalHome']=str(home);run('java-version',[home/'bin/java','-version'],30)
  # Offline gu must see prerequisite components already installed. The base
  # JDK does not contain ICU4J/TRegex and cannot fetch them on this server.
  for label,name in [('icu4j','icu4j-installable-ce-java17-linux-amd64-23.0.1.jar'),('regex','regex-installable-ce-java17-linux-amd64-23.0.1.jar'),('wasm','wasm-installable-svm-java17-linux-amd64-23.0.1.jar'),('js','js-installable-svm-java17-linux-amd64-23.0.1.jar'),('nodejs','nodejs-installable-svm-java17-linux-amd64-23.0.1.jar')]:
   require_path=inputs/name
   if not require_path.is_file():raise ValueError('Missing offline component: '+name)
   run('install-'+label,[home/'bin/gu','-L','install',require_path],180)
  run('node-version',[home/'bin/node','--jvm','--version'],30)
  source_dir=out/'source';source_dir.mkdir()
  with zipfile.ZipFile(str(inputs/'nodeprof-5cccefc.zip')) as archive:
   for name in archive.namelist():
    if source_dir not in (source_dir/name).resolve().parents:raise ValueError('Unsafe source ZIP member')
   archive.extractall(str(source_dir))
  source=next(source_dir.glob('nodeprof.js-*'));classes=out/'classes';classes.mkdir()
  names={'truffle-api.jar','truffle-runtime.jar','graaljs.jar','js.jar','trufflenode.jar','tregex.jar','icu4j.jar'}
  jars=[x for x in home.rglob('*.jar') if x.name in names and zipfile.is_zipfile(str(x))]
  if not any(x.name in ['graaljs.jar','js.jar'] for x in jars) or not any(x.name=='trufflenode.jar' for x in jars):raise ValueError('Missing JavaScript/Node compiler API jars')
  cp=os.pathsep.join(str(x) for x in jars+[inputs/'graal-sdk-23.0.1.jar']);processor=inputs/'truffle-dsl-processor-23.0.1.jar'
  java=sorted((source/'src/ch.usi.inf.nodeprof/src').rglob('*.java'));assert java
  run('compile-nodeprof',[home/'bin/javac','-source','11','-target','11','-classpath',cp,'-processorpath',cp+os.pathsep+str(processor),'-d',classes]+java)
  tool=home/'tools/nodeprof';tool.mkdir(parents=True);jar=tool/'nodeprof.jar';run('package-nodeprof',[home/'bin/jar','cf',jar,'-C',classes,'.'])
  loader=source/'src/ch.usi.inf.nodeprof/js/jalangi.js';bindir=out/'bin';bindir.mkdir();wrapper=bindir/'node'
  runtime_flags=['--jvm','--polyglot','--experimental-options','--js.webassembly=true','--openssl-legacy-provider','--vm.Dtruffle.class.path.append='+str(jar)]
  wrapper.write_text('#!/bin/sh\nexec '+__import__('shlex').quote(str(home/'bin/node'))+' '+' '.join(__import__('shlex').quote(flag) for flag in runtime_flags)+' "$@"\n');wrapper.chmod(0o755)
  run('wasm-smoke',[wrapper,'-e','if(typeof WebAssembly!=="object") throw Error("Missing WebAssembly"); new WebAssembly.Module(Buffer.from("0061736d01000000","hex")); console.log("WASM_SMOKE_OK");'],60)
  run('legacy-md4-smoke',[wrapper,'-e','const h=require("crypto").createHash("md4").update("abc").digest("hex"); if(h!=="a448017aaf21d8525fc10ae87aa6729d") throw Error("MD4 differs"); console.log("LEGACY_MD4_SMOKE_OK");'],60)
  probe=out/'smoke.js';probe.write_text('function sum(a,b){return a+b;} console.log("RUNTIME_SMOKE",sum(2,3));\n')
  analysis=out/'smoke-analysis.js';analysis.write_text('(function(){var n=0;J$.analysis={functionEnter:function(){n++;},endExecution:function(){console.log("NODEPROF_ENTRIES",n);}};})();\n')
  output=run('nodeprof-smoke',[wrapper,'--vm.classpath='+str(jar),'--experimental-options','--nodeprof',loader,'--analysis',analysis,probe],120)
  entries=__import__('re').search(r'NODEPROF_ENTRIES\s+(\d+)',output)
  if 'RUNTIME_SMOKE 5' not in output or not entries or int(entries.group(1))<1:raise ValueError('Instrumented smoke was not observed')
  record['runtime']={name:{'path':str(path),'sha256':sha(path)} for name,path in [('graalNode',wrapper),('nodeprofLoader',loader),('nodeprofJar',jar)]}
  record['runtimeDependencies']={'underlyingNode':{'path':str(home/'bin/node'),'sha256':sha(home/'bin/node')},'privateWrapperFlags':runtime_flags}
  record['status']='smoke-passed';save()
 except Exception:record.update(status='failed',error=traceback.format_exc());save();raise
 print(out/'build-status.json',flush=True)
if __name__=='__main__':main()
