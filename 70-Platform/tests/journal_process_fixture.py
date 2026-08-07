"""Test-only independent-process coordinator for Journal Authority seams."""
from __future__ import annotations
import multiprocessing,os,time
from pathlib import Path
class JournalProcessFixture:
 def __init__(self,root):self.root=Path(root);self.ready=multiprocessing.Event();self.process=None
 def launch(self,target,*args):
  self.process=multiprocessing.Process(target=target,args=(str(self.root),self.ready,*args));self.process.start();return self.process
 def wait_until_ready(self,timeout=5):return self.ready.wait(timeout)
 def terminate(self):
  if self.process and self.process.is_alive():self.process.terminate()
  if self.process:self.process.join(5)
 def evidence(self):return {"pid":self.process.pid if self.process else None,"exitcode":self.process.exitcode if self.process else None,"journal_exists":(self.root/"journal.ndjson").exists(),"head_exists":(self.root/"head.json").exists()}
def terminate_at_seam(root,ready,seam):
 """Worker protocol: signal after persisted seam; coordinator terminates it."""
 ready.set()
 while True:time.sleep(.1)
