"""Test-only deterministic signer; production modules never import this file."""
import hashlib,json
class DeterministicTestSignatureProvider:
 def sign(self,payload): return {"authority_id":"rip-transaction-authority","key_id":"test-retired-key","algorithm":"TEST_SHA256","signature_version":1,"signature":hashlib.sha256(payload).hexdigest()}
 def verify(self,payload,binding): return binding==self.sign(payload)
