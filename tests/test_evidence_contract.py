import sys,unittest,tempfile
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from experiments.common import completed,same,signature
class EvidenceContract(unittest.TestCase):
 def test_empty_success_is_not_a_suite(self):
  self.assertFalse(completed({'exitCode':0,'signature':{'Tests':[{'passed':0,'total':0}]}}))
  self.assertFalse(completed({'exitCode':0,'signature':{'Test Suites':[{'passed':1,'total':1}],'Snapshots':[{'passed':8}],'Tests':[{'passed':0,'total':0}]}}))
 def test_partial_success_is_not_same_suite(self):
  a={'exitCode':0,'signature':{'mocha-passing':[81]}};b={'exitCode':0,'signature':{'mocha-passing':[80]}}
  self.assertFalse(same(a,b));self.assertTrue(same(a,a))
 def test_exit_zero_with_failures_is_invalid(self):
  self.assertFalse(completed({'exitCode':0,'signature':{'Tests':[{'passed':274,'failed':10}]}}))
 def test_timeout_is_never_success(self):
  self.assertFalse(completed({'exitCode':124,'signature':{'mocha-passing':[81]}}))
if __name__=='__main__':unittest.main()
