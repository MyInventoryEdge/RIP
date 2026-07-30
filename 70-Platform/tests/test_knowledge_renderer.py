from __future__ import annotations
import json, tempfile, unittest
from pathlib import Path
from rip.interpretation.renderer import load_candidates, render_knowledge

def candidate(identifier='a', title='A <Decision>', evidence=None):
 return {'source_session':'s','candidates':[{'id':identifier,'type':'architectural_decision','status':'candidate','title':title,'summary':'Résumé & summary','confidence':.8,'reasoning':'Because','source_session':'s','evidence':evidence if evidence is not None else [{'message_id':'m','excerpt':'<exact> ✓','start_offset':0,'end_offset':7}]}]}
class RendererTests(unittest.TestCase):
 def write(self,d,p):
  x=d/'candidate-knowledge.json'; x.write_text(json.dumps(p),encoding='utf8'); return x
 def test_empty_and_one(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t); r=render_knowledge(self.write(d,{'source_session':'s','candidates':[]}),d); self.assertEqual(0,r['candidates'])
   r=render_knowledge(self.write(d,candidate()),d); self.assertIn('&lt;Decision&gt;',r['html'].read_text(encoding='utf8')); self.assertIn('> <exact> ✓',r['markdown'].read_text(encoding='utf8'))
 def test_validation(self):
  with tempfile.TemporaryDirectory() as t:
   d=Path(t)
   for p in ({'candidates':[{}]}, {'candidates':[candidate()['candidates'][0],candidate()['candidates'][0]]}):
    with self.assertRaises(ValueError): load_candidates(self.write(d,p))
 def test_production(self):
  p=Path(r'C:\Temp\rip-interpretation-production\candidate-knowledge.json')
  if not p.exists(): self.skipTest('fixture unavailable')
  payload=load_candidates(p)
  self.assertGreater(len(payload['candidates']),0)
  with tempfile.TemporaryDirectory() as t:
   result=render_knowledge(p,Path(t))
   self.assertEqual(len(payload['candidates']),result['candidates'])
