import tempfile,unittest,multiprocessing,os
import json
from types import MappingProxyType
from tests.journal_test_signer import DeterministicTestSignatureProvider
from tests.journal_test_storage import TemporaryJournalStorage
from rip.journal_authority import publish as _publish,validate,disposition_publication
from rip.producer_policy import ProducerPolicyAuthority

def create_producer_registry(entries, *, signer, storage):
 """Test setup only: produces immutable PPA admission evidence."""
 authority=ProducerPolicyAuthority(signer=signer,storage=storage)
 entry=next((item for item in entries if item.get("status")=="active"),None)
 if entry:
  storage._policy_authority=authority;storage._certificate=authority.admit_producer(producer_authority_type=entry["authority_type"],producer_authority_id=entry["authority_id"],permitted_record_types=entry["record_types"],producer_key_reference="test-key")
 else: storage._policy_authority=authority;storage._certificate=None
def publish(**kwargs):
 storage=kwargs["storage"]
 if not hasattr(storage,"_policy_authority"):
  storage._policy_authority=ProducerPolicyAuthority(signer=kwargs.get("signer"),storage=storage)
  rows=[json.loads(line) for line in storage.certificate_path().read_text().splitlines() if line.strip()] if storage.certificate_path().exists() else []
  storage._certificate=rows[-1] if rows else None
 kwargs.setdefault("policy_authority",getattr(storage,"_policy_authority",None));kwargs.setdefault("producer_admission_certificate",getattr(storage,"_certificate",None))
 return _publish(**kwargs)
def _publish_then_exit(root,ready):
 s=DeterministicTestSignatureProvider();st=TemporaryJournalStorage(root)
 publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="one",canonical_payload={"n":1},signer=s,storage=st);ready.set();os._exit(0)
def _stress_publish(root,worker,count,queue):
 s=DeterministicTestSignatureProvider();st=TemporaryJournalStorage(root)
 try:
  for number in range(count):publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id=f"{worker}-{number}",canonical_payload={"worker":worker,"number":number},signer=s,storage=st)
  queue.put("ok")
 except Exception as exc:queue.put(type(exc).__name__)
class CEJA001(unittest.TestCase):
 def setUp(self):self.s=DeterministicTestSignatureProvider()
 def rejected(self,st,**kwargs):
  before=tuple(path.read_bytes() if path.exists() else b"" for path in (st.journal_path(),st.head_history_path(),st.head_path()))
  with self.assertRaises(ValueError):publish(signer=self.s,storage=st,**kwargs)
  after=tuple(path.read_bytes() if path.exists() else b"" for path in (st.journal_path(),st.head_history_path(),st.head_path()))
  self.assertEqual(before,after);validate(signer=self.s,storage=st)
 def test_global_publication_and_head_history(self):
  with tempfile.TemporaryDirectory() as d:
   st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st)
   publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="1",canonical_payload={"v":1},signer=self.s,storage=st);publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="2",canonical_payload={"v":2},signer=self.s,storage=st);self.assertEqual(validate(signer=self.s,storage=st)["commit_sequence"],2)
 def test_publication_accepts_immutable_admission_snapshot(self):
  with tempfile.TemporaryDirectory() as d:
   st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st)
   snapshot=MappingProxyType(st._certificate)
   _publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="immutable",canonical_payload={"v":1},signer=self.s,storage=st,policy_authority=st._policy_authority,producer_admission_certificate=snapshot)
   self.assertEqual(validate(signer=self.s,storage=st)["commit_sequence"],1)
 def test_validation_derives_one_policy_snapshot_per_journal_pass(self):
  with tempfile.TemporaryDirectory() as d:
   st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st)
   for number in range(4): publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id=str(number),canonical_payload={"n":number},signer=self.s,storage=st)
   policy=st._policy_authority; original=policy.validate_policy_history; calls=[]
   def counted(): calls.append(True); return original()
   policy.validate_policy_history=counted
   validate(signer=self.s,storage=st)
   self.assertEqual(1,len(calls))
 def test_unadmitted_producer_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   st=TemporaryJournalStorage(d);create_producer_registry([],signer=self.s,storage=st)
   self.rejected(st,producer_authority_type="a",producer_authority_id="no",producer_record_type="x",producer_record_id="1",canonical_payload={})
 def test_invalid_admission_certificate_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st);st._certificate["signature"]["signature"]="bad";self.rejected(st,producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="1",canonical_payload={})
 def test_global_publication_owner_loss_advances_once(self):
  with tempfile.TemporaryDirectory() as d:
   st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st);ready=multiprocessing.Event();p=multiprocessing.Process(target=_publish_then_exit,args=(d,ready));p.start();self.assertTrue(ready.wait(2));p.join();self.assertEqual(p.exitcode,0)
   publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="two",canonical_payload={"n":2},signer=self.s,storage=st);head=validate(signer=self.s,storage=st);self.assertEqual(head["commit_sequence"],2);records=[json.loads(line) for line in st.journal_path().read_text().splitlines()];self.assertEqual([record["publication_sequence"] for record in records],[1,2]);self.assertEqual(len({record["record_hash"] for record in records}),2)
 def test_ja_2a_each_crash_seam_is_selectable(self):
  seams=("before temporary record creation","after temporary record creation","after record flush","after final record publication","before temporary head creation","after temporary head creation","after head flush","after head replacement","before final publication verification")
  for seam in seams:
   with self.subTest(seam=seam),tempfile.TemporaryDirectory() as d:
    st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st)
    def crash(name):
     if name==seam:raise RuntimeError(name)
    with self.assertRaisesRegex(RuntimeError,seam):publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="1",canonical_payload={},signer=self.s,storage=st,_test_seam=crash)
    try:validate(signer=self.s,storage=st)
    except ValueError:pass
 def test_ja_2b_record_temporary_seams_recover_to_last_head(self):
  for seam in ("before temporary record creation","after temporary record creation","after record flush"):
   with self.subTest(seam=seam),tempfile.TemporaryDirectory() as d:
    st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st)
    def crash(name):
     if name==seam:raise RuntimeError(name)
    with self.assertRaises(RuntimeError):publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="crashed",canonical_payload={},signer=self.s,storage=st,_test_seam=crash)
    self.assertEqual(validate(signer=self.s,storage=st),{});publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="recovered",canonical_payload={},signer=self.s,storage=st);self.assertEqual(validate(signer=self.s,storage=st)["commit_sequence"],1)
 def test_ja_2b_orphan_record_seams_fail_closed(self):
  for seam in ("after final record publication",):
   with self.subTest(seam=seam),tempfile.TemporaryDirectory() as d:
    st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st);publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="base",canonical_payload={},signer=self.s,storage=st);before=st.head_history_path().read_bytes()
    def crash(name):
     if name==seam:raise RuntimeError(name)
    with self.assertRaises(RuntimeError):publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="orphan",canonical_payload={},signer=self.s,storage=st,_test_seam=crash)
    self.assertEqual(st.head_history_path().read_bytes(),before)
    with self.assertRaises(ValueError):validate(signer=self.s,storage=st)
    with self.assertRaises(ValueError):publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="blocked",canonical_payload={},signer=self.s,storage=st)
 def test_ja_2b_after_head_flush_is_uncommitted_and_blocked(self):
  with tempfile.TemporaryDirectory() as d:
   st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st);publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="base",canonical_payload={},signer=self.s,storage=st);before=st.head_history_path().read_bytes()
   def crash(name):
    if name=="after head flush":raise RuntimeError(name)
   with self.assertRaises(RuntimeError):publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="orphan",canonical_payload={},signer=self.s,storage=st,_test_seam=crash)
   self.assertNotEqual(st.head_history_path().read_bytes(),before);self.assertTrue(st.journal_path().exists());self.assertTrue(st.head_path().exists())
   self.assertEqual(validate(signer=self.s,storage=st)["commit_sequence"],2);publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="next",canonical_payload={},signer=self.s,storage=st);self.assertEqual(validate(signer=self.s,storage=st)["commit_sequence"],3)
 def test_ja_2b_after_head_history_publication_is_committed(self):
  with tempfile.TemporaryDirectory() as d:
   st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st)
   def crash(name):
    if name=="after authenticated head-history publication":raise RuntimeError(name)
   with self.assertRaises(RuntimeError):publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="one",canonical_payload={},signer=self.s,storage=st,_test_seam=crash)
   self.assertEqual(validate(signer=self.s,storage=st)["commit_sequence"],1);publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="two",canonical_payload={},signer=self.s,storage=st);self.assertEqual(validate(signer=self.s,storage=st)["commit_sequence"],2)
 def test_ja_2b_before_final_verification_is_already_committed(self):
  with tempfile.TemporaryDirectory() as d:
   st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st)
   def crash(name):
    if name=="before final publication verification":raise RuntimeError(name)
   with self.assertRaises(RuntimeError):publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="one",canonical_payload={},signer=self.s,storage=st,_test_seam=crash)
   self.assertEqual(validate(signer=self.s,storage=st)["commit_sequence"],1);publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="two",canonical_payload={},signer=self.s,storage=st);self.assertEqual(validate(signer=self.s,storage=st)["commit_sequence"],2)
 def test_ja_2c_orphan_disposition_preserves_ledger_and_head_history(self):
  with tempfile.TemporaryDirectory() as d:
   st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st);publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="base",canonical_payload={},signer=self.s,storage=st);before=(st.journal_path().read_bytes(),st.head_history_path().read_bytes())
   def crash(name):
    if name=="after final record publication":raise RuntimeError(name)
   with self.assertRaises(RuntimeError):publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="orphan",canonical_payload={},signer=self.s,storage=st,_test_seam=crash)
   orphan=json.loads(st.journal_path().read_text().splitlines()[-1])["record_hash"];receipt=disposition_publication(record_hash=orphan,disposition="quarantined",reason="interrupted",signer=self.s,storage=st)
   self.assertEqual(receipt["record_hash"],orphan);self.assertEqual(st.head_history_path().read_bytes(),before[1]);self.assertTrue(st.journal_path().read_bytes().startswith(before[0]));self.assertEqual(len(st.quarantine_directory().joinpath("dispositions.ndjson").read_text().splitlines()),1)
 def test_ja_r_disposition_then_restart_can_publish_next(self):
  with tempfile.TemporaryDirectory() as d:
   st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st);publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="base",canonical_payload={},signer=self.s,storage=st)
   def crash(name):
    if name=="after final record publication":raise RuntimeError(name)
   with self.assertRaises(RuntimeError):publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="orphan",canonical_payload={},signer=self.s,storage=st,_test_seam=crash)
   orphan=json.loads(st.journal_path().read_text().splitlines()[-1])["record_hash"];disposition_publication(record_hash=orphan,disposition="quarantined",reason="interrupted",signer=self.s,storage=st)
   next_record=publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="next",canonical_payload={},signer=self.s,storage=st);head=validate(signer=self.s,storage=st);self.assertEqual(next_record["publication_sequence"],3);self.assertEqual(head["commit_sequence"],2);self.assertEqual(head["referenced_publication_sequence"],3)
 @unittest.skipUnless(os.environ.get("RIP_JOURNAL_STRESS")=="1","stress suite only")
 def test_ja_2d_process_stress_has_one_committed_history(self):
  for workers,total in ((2,100),(4,100),(8,100),(16,100),(32,100),(2,1000)):
   with self.subTest(workers=workers),tempfile.TemporaryDirectory() as d:
    st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st);queue=multiprocessing.Queue();count=total//workers;processes=[multiprocessing.Process(target=_stress_publish,args=(d,index,count,queue)) for index in range(workers)]
    for process in processes:process.start()
    for process in processes:process.join()
    self.assertEqual([queue.get() for _ in processes],["ok"]*workers);self.assertEqual(validate(signer=self.s,storage=st)["commit_sequence"],count*workers)
 def test_altered_payload_fails_closed(self):
  with tempfile.TemporaryDirectory() as d:
   st=TemporaryJournalStorage(d);create_producer_registry([{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"active"}],signer=self.s,storage=st);publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="1",canonical_payload={"v":1},signer=self.s,storage=st)
   record=json.loads(st.journal_path().read_text());record["canonical_payload"]={"v":2};st.journal_path().write_text(json.dumps(record)+"\n")
   with self.assertRaises(ValueError):validate(signer=self.s,storage=st)
 def test_global_contract_tamper_matrix(self):
  cases=("record","signature","key","retired","type","previous","duplicate","skipped","reordered","orphan","head")
  for case in cases:
   with self.subTest(case=case),tempfile.TemporaryDirectory() as d:
    st=TemporaryJournalStorage(d);entries=[{"authority_type":"a","authority_id":"one","record_types":["x"],"status":"retired" if case=="retired" else "active"}];create_producer_registry(entries,signer=self.s,storage=st)
    if case == "retired":
     self.rejected(st,producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="1",canonical_payload={})
     continue
    publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="1",canonical_payload={},signer=self.s,storage=st)
    if case=="type":
     self.rejected(st,producer_authority_type="a",producer_authority_id="one",producer_record_type="bad",producer_record_id="2",canonical_payload={});continue
    records=st.journal_path().read_text().splitlines();heads=st.head_history_path().read_text().splitlines();r=json.loads(records[0]);h=json.loads(heads[0])
    if case=="record":r["producer_record_id"]="bad";records=[json.dumps(r)]
    elif case=="signature":r["signature"]["signature"]="bad";records=[json.dumps(r)]
    elif case=="key":r["signature"]["key_id"]="bad";records=[json.dumps(r)]
    elif case=="previous":r["previous_record_hash"]="bad";records=[json.dumps(r)]
    elif case=="duplicate":r["publication_sequence"]=1;records+=[json.dumps(r)];heads+=[json.dumps(h)]
    elif case=="skipped":r["publication_sequence"]=2;records=[json.dumps(r)]
    elif case=="reordered":publish(producer_authority_type="a",producer_authority_id="one",producer_record_type="x",producer_record_id="2",canonical_payload={},signer=self.s,storage=st);records=list(reversed(st.journal_path().read_text().splitlines()))
    elif case=="orphan":records+=[records[0]]
    elif case=="head":h["record_hash"]="bad";heads=[json.dumps(h)]
    st.journal_path().write_text("\n".join(records)+"\n");st.head_history_path().write_text("\n".join(heads)+"\n")
    with self.assertRaises(ValueError):validate(signer=self.s,storage=st)
