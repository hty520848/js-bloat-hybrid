"""Reject success-only or unmatched deadline qualifications."""
import copy,tempfile,unittest
from pathlib import Path
from experiments.recovery_repair import require_matched_deadline_controls,function_ast,deadline_command,reconcile_payload_events

def stage():
 return {'exitCode':0,'signature':{'Tests':[{'passed':222,'skipped':5,'total':227}],'Snapshots':[{'passed':523,'total':523}]},'command':deadline_command('node14')}

class DeadlineQualification(unittest.TestCase):
 def test_payload_byte_repair_preserves_raw_counters_and_deduplicates(self):
  with tempfile.TemporaryDirectory() as directory:
   payload=Path(directory)/'module.js.BIGG';payload.write_bytes(b'abcdefgh')
   raw=[{'kind':'file','path':str(payload),'bytes':3}]*2
   fixed,audit=reconcile_payload_events(raw,directory)
   self.assertEqual(raw[0]['bytes'],3);self.assertEqual(fixed[0]['bytes'],8)
   self.assertEqual(audit['actualUniquePayloadBytes'],8);self.assertEqual(audit['rawUniquePayloadBytes'],3)
   self.assertEqual(audit['reportedByteCountMismatches'],2)

 def test_operand_outside_certified_artifact_cannot_supply_a_result(self):
  with tempfile.TemporaryDirectory() as directory:
   payload=Path(directory)/'module.js.BIGG';payload.write_bytes(b'abcdefgh');artifact=Path(directory)/'artifact';artifact.mkdir()
   with self.assertRaises(ValueError):reconcile_payload_events([{'kind':'file','path':str(payload),'bytes':8}],artifact)

 def test_missing_baseline_arm_never_qualifies(self):
  with self.assertRaises(ValueError):require_matched_deadline_controls(stage(),{'sdcg':stage(),'hybrid':stage()})

 def test_failure_is_not_replaced_by_the_other_two_successes(self):
  controls={name:stage() for name in ['sscg','sdcg','hybrid']};controls['sdcg']['exitCode']=1
  with self.assertRaises(ValueError):require_matched_deadline_controls(stage(),controls)

 def test_different_discovery_is_not_accepted(self):
  controls={name:stage() for name in ['sscg','sdcg','hybrid']};controls['sscg']['signature']['Tests'][0]['passed']=221
  with self.assertRaises(ValueError):require_matched_deadline_controls(stage(),controls)

 def test_one_method_cannot_keep_a_different_timeout(self):
  controls={name:stage() for name in ['sscg','sdcg','hybrid']};controls['sdcg']['command'][-1]='--timeout-ms=5000'
  with self.assertRaises(ValueError):require_matched_deadline_controls(stage(),controls)

 def test_four_matching_full_controls_qualify(self):
  require_matched_deadline_controls(stage(),{name:stage() for name in ['sscg','sdcg','hybrid']})

 def test_source_comparison_ignores_line_numbers_but_detects_computation_change(self):
  with tempfile.TemporaryDirectory() as directory:
   a=Path(directory)/'a.py';b=Path(directory)/'b.py';a.write_text('def f(x):\n return x+1\n');b.write_text('\n\ndef f(x):\n return x+1\n')
   self.assertEqual(function_ast(a,'f'),function_ast(b,'f'))
   b.write_text('def f(x):\n return x+2\n');self.assertNotEqual(function_ast(a,'f'),function_ast(b,'f'))
