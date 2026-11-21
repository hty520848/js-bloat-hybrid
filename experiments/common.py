"""Python 3.6+, Linux execution; stdlib only. Immutable inputs, isolated writes."""
import hashlib,json,os,re,shutil,signal,subprocess,time,stat
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def read(p):return json.loads(Path(p).read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,x):
 p=Path(p);p.parent.mkdir(parents=True,exist_ok=True)
 q=p.with_suffix(p.suffix+'.tmp');q.write_text(json.dumps(x,ensure_ascii=False,indent=2)+'\n',encoding='utf-8');q.replace(p)
def signature(p):
 text=re.sub(r'\x1b\[[0-9;]*m','',Path(p).read_text(errors='replace'));out={}
 for k in ['Test Suites','Tests','Snapshots']:
  vals=re.findall(r'^\s*'+k+r':\s*(.*)$',text,re.M)
  if vals:out[k]=[{v:int(n) for n,v in re.findall(r'(\d+)\s+(passed|failed|skipped|pending|todo|total)',a)} for a in vals]
 # Integration suites can print the output of deliberately failing nested
 # test processes. Only the final outer Mocha summary controls admission.
 summaries=list(re.finditer(r'^[ \t]*(\d+) (passing|failing|pending)(?:[ \t]+\([^\n]*\))?[ \t]*$',text,re.M))
 passing=[m for m in summaries if m.group(2)=='passing']
 if passing:
  last=passing[-1]
  for m in summaries:
   if m.start()>=last.start():out.setdefault('mocha-'+m.group(2),[]).append(int(m.group(1)))
 for k in ['tests','pass','fail','skip','todo']:
  vals=re.findall(r'^#\s*'+k+r'\s+(\d+)\s*$',text,re.M)
  if vals:out['tap-'+k]=[int(n) for n in vals]
 vals=re.findall(r'(\d+) specs?, (\d+) failures?(?:, (\d+) pending specs?)?',text)
 if vals:out['jasmine']=[{'total':int(n),'failed':int(f),'passed':int(n)-int(f)-int(p or 0),'pending':int(p or 0)} for n,f,p in vals]
 vals=re.findall(r'(\d+) tests?, (\d+) assertions?, (\d+) failures?',text)
 if vals:out['jasmine-node']=[{'total':int(n),'assertions':int(a),'failed':int(f),'passed':int(n)-int(f)} for n,a,f in vals]
 vals=re.findall(r'Executed (\d+) of (\d+)(?:\s*\(skipped (\d+)\))?\s+(SUCCESS|FAILED)',text)
 if vals:
  n,total,skipped,status=vals[-1];out['karma']=[{'passed':int(n) if status=='SUCCESS' else 0,'failed':0 if status=='SUCCESS' else 1,'total':int(total),'skipped':int(skipped or 0)}]
 vals=re.findall(r'\b(\d+) tests? (passed|failed|skipped|todo)\b',text)
 if vals:out['ava']=[{kind:int(n) for n,kind in vals}]
 vals=re.findall(r'^\s*(?:>>\s*)?(\d+) assertions? passed(?:\s|$)',text,re.M)
 if vals:out['nodeunit-assertions']=[int(n) for n in vals]
 vals=re.findall(r'Executed (\d+) of (\d+) specs\s+(SUCCESS|INCOMPLETE)(?:\s+\((\d+) PENDING\))?',text)
 if vals:
  n,total,status,pending=vals[-1];n,total,pending=int(n),int(total),int(pending or 0)
  if n+pending==total:out['jasmine-completion']=[{'passed':n,'total':total,'pending':pending,'failed':1 if re.search(r'^Failures:\s*$',text,re.M) else 0}]
 return out
def completed(a):
 if not a or a.get('exitCode')!=0:return False
 sig=a.get('signature',{})
 positives=[];failures=[]
 for k,v in sig.items():
  if k.startswith('mocha-'):
   if k=='mocha-passing':positives+=v
   if k=='mocha-failing':failures+=v
  elif k in ['tap-pass']:positives+=v
  elif k=='nodeunit-assertions':positives+=v
  elif k in ['tap-fail']:failures+=v
  elif isinstance(v,list):
   for item in v:
    if isinstance(item,dict):
     if k not in ['Test Suites','Snapshots']:positives.append(item.get('passed',0))
     failures.append(item.get('failed',0))
 return any(n>0 for n in positives) and not any(failures)
def same(a,b):return completed(a) and completed(b) and a['signature']==b.get('signature')
def snapshot(root,include_all=False):
 root=Path(root);out={}
 for dp,dn,fn in os.walk(str(root),followlinks=False):
  dn[:]=[d for d in dn if d not in ['.git','coverage','.nyc_output','__pycache__']]
  for n in fn:
   p=Path(dp)/n
   if p.is_symlink():continue
   if include_all or n.endswith(('.js','.mjs','.cjs','.json','.ts')):out[str(p.relative_to(root))]=sha(p)
  for n in dn+fn:
   p=Path(dp)/n
   if not p.is_symlink():continue
   target=p.resolve()
   if os.path.isabs(os.readlink(str(p))) or not (target==root or root in target.parents):raise ValueError('Input link leaves private root: '+str(p))
   out['@link:'+str(p.relative_to(root))]=hashlib.sha256(str(target.relative_to(root)).encode()).hexdigest()
 return out

def output_snapshot(root):
 """Hash generated output without following links or opening sockets/FIFOs."""
 root=Path(root);out={}
 for dp,dn,fn in os.walk(str(root),followlinks=False):
  dn[:]=[d for d in dn if d!='.git']
  for name in dn+fn:
   p=Path(dp)/name;relative=str(p.relative_to(root));mode=p.lstat().st_mode
   if stat.S_ISLNK(mode):out[relative]={'link':os.readlink(str(p))}
   elif stat.S_ISREG(mode):out[relative]={'sha256':sha(p)}
   elif not stat.S_ISDIR(mode):out[relative]={'specialMode':mode}
 return out
def clone(src,dst):
 src,dst=Path(src).resolve(),Path(dst).absolute()
 assert not dst.exists() and not dst.is_symlink(),str(dst)
 assert ROOT/'work' in dst.parents,'Clone must be inside package/work'
 dst.parent.mkdir(parents=True,exist_ok=True)
 subprocess.run(['cp','--reflink=auto','-a',str(src),str(dst)],check=True)
 snapshot(dst)  # no shared dependency links may survive a private clone
 return dst

def variant_directory(c,tag):
 # Legacy stub identifiers encode their full path. Equal-length hashed tags
 # prevent arm names from changing measured generated-code byte counts.
 return c.work/'variants'/hashlib.sha256(tag.encode('utf-8')).hexdigest()[:16]

def register_recovery(c,target,lab):
 helper=Path(lab)/'stubbifier_cjs.cjs';assert c.work in helper.resolve().parents
 assert sha(helper)==sha(ROOT/'src/transformer/stubbifier_cjs.cjs')
 if not hasattr(c,'recovery_helpers'):c.recovery_helpers={}
 c.recovery_helpers[str(Path(target))]=[{'file':str(helper),'sha256':sha(helper)}]

def retained_paths(c,lib,target):
 return [str(Path(target)/p) for p in c.protocol.get('deploymentRetention',{}).get(lib,[])]

def completion_gate(protocol,qualified,completed,invalid=()):
 """Single definition of "this stage is finished".

 A stage used to be called ``core-pilot-completed`` whenever every cell it
 happened to produce was valid, so a two-library pilot and a ten-library matrix
 carried the same label. The label now also depends on coverage: a run is
 ``completed`` only when every qualified library produced every arm and every
 one of those cells is valid. Anything less is ``partial``, and a run with no
 valid cell at all is ``blocked``. Nothing is ever rounded up.
 """
 arms=list(protocol['arms']);libraries=sorted(qualified)
 expected=[(l,a) for l in libraries for a in arms]
 done={tuple(x) for x in completed};bad={tuple(x) for x in invalid}
 missing=[cell for cell in expected if cell not in done and cell not in bad]
 libraries_covered=sorted({l for l,_ in done&set(expected)})
 expected_libraries=int(protocol.get('formalLibraries') or len(libraries))
 status='blocked' if not done else ('completed' if not missing and not bad and len(libraries_covered)==expected_libraries else 'partial')
 return {'status':status,'expectedCells':len(expected),'completedCells':len(done&set(expected)),'invalidCells':len(bad&set(expected)),'missingCells':len(missing),'librariesCovered':len(libraries_covered),'librariesExpected':expected_libraries,'arms':arms,'missingCellList':[list(x) for x in missing[:80]],'boundary':'A partial matrix is reported as partial; no successful-subset headline.'}
def implementation_snapshot():
 return {str(p.relative_to(ROOT)):sha(p) for folder in ['src','config','experiments','scripts','datasets/manifests'] for p in (ROOT/folder).rglob('*') if p.is_file() and 'node_modules' not in p.parts and '__pycache__' not in p.parts and p.name!='machine.local.json'}
class Context:
 def __init__(self,run_id,machine_path=None):
  if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.-]{0,100}',run_id):raise ValueError('Invalid run id')
  self.machine=read(machine_path or ROOT/'config/machine.local.json');self.protocol=read(ROOT/'config/protocol.json')
  self.out=ROOT/'runs'/run_id;self.work=ROOT/'work'/run_id
  self.out.mkdir(parents=True,exist_ok=False);self.work.mkdir(parents=True,exist_ok=False)
  self.manifest=read(ROOT/'datasets/manifests/libraries.json')
  self.inputSnapshots={}
  self.inputSnapshotAlgorithms={}
  self.harnesses={}
  self.recovery_helpers={}
  self.record={'status':'running','runId':run_id,'stages':[],'startedUnix':time.time()}
  self.frozen=implementation_snapshot()
  write(self.out/'executed-source-sha256.json',self.frozen);write(self.out/'protocol.json',self.protocol)
  for relative,expected in self.frozen.items():
   source=ROOT/relative;assert sha(source)==expected,'Source changed during snapshot'
   dest=self.out/'executed-source'/relative;dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(str(source),str(dest))
  write(self.out/'machine.json',self.machine);self.save()
 def save(self):write(self.out/'status.json',self.record)
 def env(self,tag,extra=None):
  e=os.environ.copy();temp=self.work/'tmp'/tag;temp.mkdir(parents=True,exist_ok=True)
  e.update(CI='1',NO_UPDATE_NOTIFIER='1',TMPDIR=str(temp),TMP=str(temp),TEMP=str(temp),HOME=str(self.work/'home'),JEST_JOBS='1',npm_config_update_notifier='false',npm_config_audit='false',npm_config_fund='false',npm_config_prefix=str(self.work/'npm-global'),npm_config_cache=str(self.work/'npm-cache'),HYBRID_PACKAGE_ROOT=str(ROOT))
  provision=getattr(self,'npmOfflineProvision',None)
  if provision:
   # A client suite that creates its own fixture project and installs into it
   # (PowerBI-visuals-tools runs `npm install` inside every `pbiviz new`) cannot
   # fall back to the cache unless npm is told the cache is all there is; left
   # online it instead retries a blocked registry until the per-client timeout
   # fires. The recorded registry is the key namespace the cache was populated
   # under, so it has to match for entries to hit at all.
   e.update(npm_config_offline='true',npm_config_registry=provision['registry'])
  e['NODE_PATH']=os.pathsep.join([self.machine['transformerNodeModules'],self.machine['staticNodeModules']])
  e['PATH']=str(Path(self.machine['nodeTest']).parent)+os.pathsep+e.get('PATH','')
  if extra:e.update({k:str(v) for k,v in extra.items()})
  return e
 def seed_client_cache(self,e,names):
  """Provision offline dependency caches into the private client HOME.

  dtslint installs typescript on demand into $HOME/.dts/typescript-installs and
  skips a version only when that directory already exists. On a host without
  outbound network that install dies with a certificate error, so any client
  whose `npm test` chains `dtslint types` can never complete even though its own
  sources are intact. The cache is copied from the harness runtime and hashed
  into the input snapshot, so it is recorded evidence rather than an untracked
  side channel that silently changes what the client can reach.
  """
  if not self.machine.get('harnessRoot'):return
  home=Path(e['HOME']);assert self.work in home.parents,'Client HOME must be private';home.mkdir(parents=True,exist_ok=True)
  for name in names:
   source=Path(self.machine['harnessRoot'])/'environment/client-cache'/name;dest=home/name
   if source.is_dir() and not dest.exists():
    self.inputSnapshots[str(source)]=snapshot(source,include_all=True);self.inputSnapshotAlgorithms[str(source)]=True
    subprocess.run(['cp','--reflink=auto','-a',str(source),str(dest)],check=True)
 def seed_npm_cache(self):
  """Provision the private npm cache for client suites that install fixtures.

  Some client workloads shell out to `npm install` while running their own
  tests. That is their test design, not something this harness may remove, so
  the packages have to be reachable. This image has no route to a registry, and
  an install that is left online does not fail fast: it retries until the
  per-client budget expires, which reads as "the client is broken" rather than
  "the registry is unreachable". The cache recorded by a run that did complete
  is copied in, hashed as an input, and described by PROVISION.json so the
  registry namespace it was populated under travels with it.
  """
  if not self.machine.get('harnessRoot'):return
  source=Path(self.machine['harnessRoot'])/'environment/client-cache'/'npm-cache'
  dest=self.work/'npm-cache'
  if not source.is_dir() or dest.exists():return
  provision=source/'PROVISION.json'
  if not provision.is_file():return
  self.npmOfflineProvision=read(provision)
  self.inputSnapshots[str(source)]=snapshot(source,include_all=True);self.inputSnapshotAlgorithms[str(source)]=True
  subprocess.run(['cp','--reflink=auto','-a',str(source),str(dest)],check=True)
 def run(self,label,args,cwd,extra=None,timeout=None):
  if implementation_snapshot()!=self.frozen:raise RuntimeError('Implementation changed during run; start a new run id')
  log=self.out/'logs'/(label+'.log');log.parent.mkdir(parents=True,exist_ok=True)
  assert not log.exists(),'Observation already exists: '+label
  if not getattr(self,'npmCacheSeeded',False):self.seed_npm_cache();self.npmCacheSeeded=True
  e=self.env(label,extra);e['PATH']=str(Path(cwd)/'node_modules/.bin')+os.pathsep+e['PATH']
  if not getattr(self,'offlineHomeSeeded',False):self.seed_client_cache(e,['.dts']);self.offlineHomeSeeded=True
  harness=Path(cwd)/'.hybrid-harness.json'
  config=self.harnesses.get(str(cwd)) or (read(harness) if harness.is_file() else None)
  if config:
   configured=config.get('environment',{})
   def expand(value):
    return str(value).replace('{PACKAGE}',str(ROOT)).replace('{CLIENT}',str(cwd)).replace('{RUN_WORK}',str(self.work)).replace('{HARNESS}',self.machine.get('harnessRoot',''))
   old_options=e.get('NODE_OPTIONS','');e.update({k:expand(v) for k,v in configured.items()})
   if configured.get('HOME') and self.machine.get('harnessRoot'):self.seed_client_cache(e,['.cache','.dts'])
   if old_options and configured.get('NODE_OPTIONS'):e['NODE_OPTIONS']=expand(configured['NODE_OPTIONS'])+' '+old_options
   requested_args=[str(x) for x in args]
   if config.get('testProviderModules'):
    providers=Path(config['testProviderModules']);assert self.work in providers.resolve().parents
    e['NODE_PATH']=str(providers);e['PATH']=str(providers/'.bin')+os.pathsep+e['PATH']
    # Only explicit unit-tool argv entries are redirected. Measured source
    # imports still pass through the production-dependency boundary guard.
    args=[str(providers/str(x)[len('node_modules/'):]) if str(x).startswith('node_modules/') and (providers/str(x)[len('node_modules/'):]).is_file() else x for x in args]
   if e.get('BLOAT_GIT_WRAPPER'):e['PATH']=e['BLOAT_GIT_WRAPPER']+os.pathsep+e['PATH']
   e['HYBRID_PROTECTED_ROOTS']=json.dumps([str(ROOT/p) for p in ['artifacts','src','scripts','config','datasets']]+self.machine.get('protectedLegacyRoots',[]))
   runtime=Path(self.machine['nodeTest']).resolve().parent.parent
   module_roots=[str(self.work),str(ROOT/'scripts/harness'),str(ROOT/'src/metrics'),str(runtime)]
   if self.machine.get('harnessRoot'):module_roots.append(self.machine['harnessRoot'])
   e['HYBRID_ALLOWED_MODULE_ROOTS']=json.dumps(module_roots)
   e['HYBRID_RECOVERY_HELPERS']=json.dumps(config.get('recoveryHelpers',[]))
   e['HYBRID_RECOVERY_MODULE_ROOTS']=json.dumps([self.machine['transformerNodeModules']])
   live=Path(cwd)/'.hybrid-live-bindings.json'
   if live.is_file():e['HYBRID_DEPLOYMENT_BOUNDARIES']=json.dumps(read(live))
   if config.get('deploymentBoundaries'):e['HYBRID_DEPLOYMENT_BOUNDARIES']=json.dumps(config['deploymentBoundaries'])
   e['NODE_OPTIONS']='--require '+str(ROOT/'scripts/harness/fs_guard.js')+' --require '+str(ROOT/'scripts/harness/module_guard.js')+' '+e.get('NODE_OPTIONS','')
   if self.machine.get('packageManagerBin'):e['PATH']=self.machine['packageManagerBin']+os.pathsep+e['PATH']
  start=time.monotonic();load=list(os.getloadavg());expired=False
  print('START '+label,flush=True)
  with log.open('wb') as f:
   p=subprocess.Popen([str(x) for x in args],cwd=str(cwd),env=e,stdout=f,stderr=subprocess.STDOUT,start_new_session=True)
   # A blocking waitpid observes process completion without the polling delay
   # in Popen.wait(timeout=...). SIGALRM supplies the separate hard deadline.
   limit=timeout or (config.get('timeoutSeconds') if config else None) or self.protocol['testTimeoutSeconds']
   def deadline(signum,frame):raise subprocess.TimeoutExpired(args,limit)
   previous=signal.signal(signal.SIGALRM,deadline);signal.setitimer(signal.ITIMER_REAL,limit)
   try:rc=p.wait()
   except subprocess.TimeoutExpired:
    signal.setitimer(signal.ITIMER_REAL,0);expired=True;os.killpg(p.pid,signal.SIGTERM)
    try:p.wait(timeout=5)
    except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);p.wait()
    rc=124
   finally:signal.setitimer(signal.ITIMER_REAL,0);signal.signal(signal.SIGALRM,previous)
  try:os.killpg(p.pid,signal.SIGTERM)
  except ProcessLookupError:pass
  row={'label':label,'command':[str(x) for x in args],'cwd':str(cwd),'exitCode':rc,'timeout':expired,'seconds':time.monotonic()-start,'measurementVersion':'blocking-waitpid-sigalrm-v1','log':str(log),'logSha256':sha(log),'signature':signature(log),'loadBefore':load,'loadAfter':list(os.getloadavg())}
  if config and config.get('testProviderModules'):row['requestedCommand']=requested_args;row['testProviderModules']=config['testProviderModules']
  write(self.out/'commands'/(label+'.json'),row);print('END {} {} {:.3f}'.format(label,rc,row['seconds']),flush=True)
  return row
 def finish(self):
  current=implementation_snapshot();changed=sorted(p for p in set(current)|set(self.frozen) if current.get(p)!=self.frozen.get(p))
  changed_inputs=[p for p,h in self.inputSnapshots.items() if snapshot(p,include_all=self.inputSnapshotAlgorithms.get(p,False))!=h]
  self.record.update(status='completed-with-gates' if any(s.get('status')=='blocked' for s in self.record['stages']) else 'completed',changedImplementation=changed,finishedUnix=time.time())
  self.record['changedInputTrees']=changed_inputs
  if changed or changed_inputs:self.record['status']='invalid-input-or-implementation-changed'
  self.save()
