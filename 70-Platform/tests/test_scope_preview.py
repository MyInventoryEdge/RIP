import unittest
from rip.onboarding import ClassificationScope,preview_scope,validate_preview
class ScopePreviewTests(unittest.TestCase):
 def test_preview_is_deterministic_bounded_and_stale_checked(self):
  m={'manifest_fingerprint':'a'*64,'entries':[{'path':f'dir/{i}.txt','kind':'file','value':str(i),'size':i} for i in range(101)]}
  p=preview_scope(m,target='dir/*.txt',scope=ClassificationScope.PATH_GLOB);self.assertEqual(101,p.total_matches);self.assertEqual(100,len(p.example_paths));self.assertEqual(p,preview_scope(m,target='dir/*.txt',scope=ClassificationScope.PATH_GLOB));validate_preview(p,m)
  with self.assertRaisesRegex(ValueError,'stale'): validate_preview(p,dict(m,manifest_fingerprint='b'*64))
 def test_exact_and_empty_patterns(self):
  m={'manifest_fingerprint':'a'*64,'entries':[{'path':'a.txt','kind':'file','value':'x','size':1}]}
  self.assertEqual(1,preview_scope(m,target='a.txt',scope=ClassificationScope.EXACT_PATH).total_matches)
  with self.assertRaisesRegex(ValueError,'empty'): preview_scope(m,target='none',scope=ClassificationScope.EXACT_PATH)
