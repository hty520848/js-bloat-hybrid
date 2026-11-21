"""Regression checks for scientific cache loss and silent data corruption."""
import tempfile,unittest
from pathlib import Path
from experiments.ordered_revision import payload_map,dynamic_cache_paths,runtime_for,ROOT

class PayloadReuseContract(unittest.TestCase):
 def test_runtime_override_is_confined_to_qualified_library(self):
  old={'graalNode':{'path':'node14','sha256':'old'}};new={'graalNode':{'path':'node18','sha256':'new'}}
  proof={'runtime':old,'runtimeByLibrary':{'css-loader':new}}
  self.assertEqual(runtime_for(proof,'body-parser'),old)
  self.assertEqual(runtime_for(proof,'css-loader'),new)

 def test_legacy_admission_keeps_its_original_runtime(self):
  original={'graalNode':{'path':'node14','sha256':'old'}}
  self.assertEqual(runtime_for({'runtime':original},'css-loader'),original)

 def test_cache_uses_actual_producer_instead_of_current_run(self):
  producing=ROOT/'runs'/'older-qualified-run'
  mapped,meta=dynamic_cache_paths({'label':'runtime-profile-body-parser','log':str(producing/'logs/runtime-profile-body-parser.log')})
  self.assertEqual(mapped,producing/'rq1/dynamic/runtime-profile-body-parser-mapped.json')
  self.assertEqual(meta,producing/'rq1/dynamic/runtime-profile-body-parser.json.meta.json')

 def test_missing_tree_is_unavailable_not_zero(self):
  with tempfile.TemporaryDirectory() as directory:
   with self.assertRaises(ValueError):payload_map(Path(directory)/'missing')

 def test_changed_bytes_cannot_match_even_at_same_size(self):
  with tempfile.TemporaryDirectory() as directory:
   a=Path(directory)/'old';b=Path(directory)/'new';a.mkdir();b.mkdir()
   (a/'lib.js.BIGG').write_bytes(b'AAAA');(b/'lib.js.BIGG').write_bytes(b'AAAB')
   self.assertNotEqual(payload_map(a),payload_map(b))

 def test_relocation_keeps_identical_payload_identity(self):
  with tempfile.TemporaryDirectory() as directory:
   a=Path(directory)/'old';b=Path(directory)/'new';a.mkdir();b.mkdir()
   for root in [a,b]:
    (root/'nested').mkdir();(root/'nested/function.BIGG').write_bytes(b'let f = function () { return 42; }; f;')
   self.assertEqual(payload_map(a),payload_map(b))

if __name__=='__main__':unittest.main()
