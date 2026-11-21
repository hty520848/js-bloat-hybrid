import tempfile,unittest
from pathlib import Path
from experiments.common import signature,completed
class Reporters(unittest.TestCase):
 def parse(self,text):
  with tempfile.TemporaryDirectory() as t:
   p=Path(t)/'log';p.write_text(text);return {'exitCode':0,'signature':signature(p)}
 def test_ava_summary_is_a_positive_suite(self):
  self.assertTrue(completed(self.parse('  4 tests passed [16:14:30]\n')))
  self.assertFalse(completed(self.parse('  3 tests passed\n1 test failed\n')))
 def test_jasmine_declared_pending_is_preserved(self):
  r=self.parse('Executed 39 of 56 specs INCOMPLETE (17 PENDING) in 7 mins 51 secs.\n');self.assertTrue(completed(r));self.assertEqual(r['signature']['jasmine-completion'][0]['pending'],17)
  self.assertFalse(completed(self.parse('Executed 39 of 56 specs INCOMPLETE (2 PENDING)\n')))
  self.assertFalse(completed(self.parse('Failures:\n1) assertion failed\nExecuted 39 of 56 specs INCOMPLETE (17 PENDING)\n')))
 def test_nodeunit_assertion_summary(self):
  self.assertTrue(completed(self.parse('Testing connect_test.js...................OK\n>> 48 assertions passed (141ms)\nDone.\n')))
  self.assertFalse(completed(self.parse('>> 0 assertions passed (1ms)\n')))
 def test_expected_nested_mocha_failures_do_not_replace_outer_summary(self):
  r=self.parse('  0 passing (2ms)\n  4 failing\nExpected nested process failure\n  305 passing (1m)\n  11 pending\n');self.assertTrue(completed(r));self.assertEqual(r['signature']['mocha-passing'],[305])
  self.assertFalse(completed(self.parse('  82 passing (226ms)\n  1 failing\n')))
if __name__=='__main__':unittest.main()
