import unittest,tempfile,subprocess,os,json,hashlib
from pathlib import Path
from experiments.common import ROOT,read,write,sha
from release_test_support import release_machine

class EmptyStaticCertificate(unittest.TestCase):
 def test_empty_static_predictions_require_matching_index_and_source(self):
  m=release_machine();base=ROOT/'artifacts/code-validation';base.mkdir(parents=True,exist_ok=True)
  with tempfile.TemporaryDirectory(dir=str(base)) as td:
   p=Path(td);(p/'lib.js').write_text('module.exports=function(x){return x;};');scope=p/'scope.json';write(scope,{'files':['lib.js'],'hashes':{'lib.js':sha(p/'lib.js')}});cert=p/'certificate.json';write(cert,{'databaseQualified':True,'queryAndInventoryCompleted':True,'qualifiedEmptyGraph':True,'rows':0,'indexedMeasuredFiles':1,'indexedMeasuredFunctionFiles':['lib.js'],'scopeSha256':sha(scope)})
   code='const fn=require(process.argv[1]).getCodeQLTargets;let rejected=false;try{fn([],process.argv[2],"Data/test",process.argv[2])}catch(e){rejected=true}if(!rejected)throw Error("Uncertified empty graph accepted");process.env.STUBBIFIER_EMPTY_SSCG_CERTIFICATE=process.argv[3];if(fn([],process.argv[2],"Data/test",process.argv[2]).length)throw Error("Invented targets");require("fs").appendFileSync(process.argv[2]+"/lib.js","// changed");rejected=false;try{fn([],process.argv[2],"Data/test",process.argv[2])}catch(e){rejected=true}if(!rejected)throw Error("Changed source accepted");'
   env=dict(os.environ,NODE_PATH=os.pathsep.join([m['transformerNodeModules'],m['staticNodeModules']]),STUBBIFIER_EMPTY_SSCG_CERTIFICATE='',SQJ_SCOPE_FILES=str(scope),NODE_OPTIONS='')
   subprocess.run([m['nodeTest'],'-e',code,str(ROOT/'src/transformer/codeqlTargets.js'),str(p),str(cert)],env=env,check=True)
if __name__=='__main__':unittest.main()
