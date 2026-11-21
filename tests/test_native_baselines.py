import unittest,tempfile,tarfile,io,shutil,json,os,subprocess
from pathlib import Path
from types import SimpleNamespace
from experiments.common import ROOT,write,read
from experiments.baselines import harness
from release_test_support import release_machine

class NativeHarnessTests(unittest.TestCase):
 def test_graft_cannot_restore_removed_production_dependency_or_asset(self):
  machine=release_machine()
  base=ROOT/'artifacts/code-validation';base.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=str(base)) as td:
   p=Path(td);source=p/'source';source.mkdir();write(source/'package.json',{'name':'test-native'});(source/'index.js').write_text('module.exports=1;');(source/'asset.txt').write_text('published')
   (source/'test.js').write_text('require("assert").equal(require("./index.js"),1);')
   for name in ['production-dep','test-helper']:
    dest=source/'node_modules'/name;dest.mkdir(parents=True);(dest/'index.js').write_text('module.exports=7;')
   scope=p/'scope.json';write(scope,{'dependencies':[{'path':'node_modules/production-dep'}]});deployment=p/'native-output';deployment.mkdir();(deployment/'index.js').write_text('module.exports=1;');write(deployment/'package.json',{'name':'test-native'})
   npm=ROOT/'artifacts/npm';npm.mkdir(parents=True,exist_ok=True);archive=npm/(p.name+'-native-test.tgz')
   with tarfile.open(str(archive),'w:gz') as t:
    for name in ['package.json','index.js','asset.txt']:t.add(str(source/name),arcname='package/'+name)
   work=ROOT/'work'/('code-validation-'+p.name);work.mkdir(parents=True)
   try:
    c=SimpleNamespace(work=work,out=work/'results',manifest=[{'library':'test-native','archive':archive.name}],protocol={'testTimeoutSeconds':10})
    q={'root':source,'scope':scope,'dependencyBoundary':{'files':['index.js'],'packages':[{'path':'','dependencies':['production-dep']}]}}
    dest=harness(c,'test-native',q,deployment,'check')
    self.assertFalse((dest/'node_modules/production-dep').exists());self.assertFalse((dest/'asset.txt').exists());self.assertTrue((dest/'test.js').is_file());self.assertTrue((dest/'node_modules/test-helper').is_symlink());self.assertEqual((dest/'index.js').read_text(),'module.exports=1;')
    providers=Path(c.harnesses[str(dest)]['testProviderModules']);self.assertTrue((providers/'test-helper/index.js').is_file())
    (providers/'test-helper/index.js').write_text('module.exports=require("production-dep");')
    (dest/'index.js').write_text('module.exports=require("production-dep");')
    env=dict(os.environ,NODE_PATH=str(providers),NODE_OPTIONS='--require '+str(ROOT/'scripts/harness/module_guard.js'),HYBRID_ALLOWED_MODULE_ROOTS=json.dumps([str(work)]),HYBRID_DEPLOYMENT_BOUNDARIES=json.dumps(c.harnesses[str(dest)]['deploymentBoundaries']),HYBRID_RECOVERY_HELPERS='[]',HYBRID_RECOVERY_MODULE_ROOTS='[]')
    code='const assert=require("assert");assert.equal(require("test-helper"),7);assert.throws(()=>require(process.argv[1]),/HYBRID_REMOVED_PRODUCTION_DEPENDENCY_FALLBACK/);'
    subprocess.run([machine['nodeTest'],'-e',code,str(dest/'index.js')],env=env,cwd=str(dest),check=True)
   finally:shutil.rmtree(str(work));archive.unlink()
if __name__=='__main__':unittest.main()
