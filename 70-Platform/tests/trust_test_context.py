from pathlib import Path
from rip.journal_authority import JournalAuthority
from rip.producer_policy import ProducerPolicyAuthority
from tests.journal_test_signer import DeterministicTestSignatureProvider
from tests.journal_test_storage import TemporaryJournalStorage

def trust_context(root):
    storage=TemporaryJournalStorage(Path(root)/'journal'); signer=DeterministicTestSignatureProvider(); policy=ProducerPolicyAuthority(signer=signer,storage=storage)
    certificate=policy.admit_producer(producer_authority_type='trust-authority',producer_authority_id='trust-v1',permitted_record_types=('trust-decision-envelope',),producer_key_reference='test')
    return {'platform_key_provider':signer,'producer_policy_authority':policy,'producer_admission_certificate':certificate,'journal_authority':JournalAuthority(key_provider=signer,policy_authority=policy,storage=storage),'journal_storage':storage}
