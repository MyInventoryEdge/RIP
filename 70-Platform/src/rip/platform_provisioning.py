"""Production composition root for authenticated platform authorities."""
from __future__ import annotations

from dataclasses import dataclass
from types import MappingProxyType
from typing import Mapping

from .journal_authority import JournalAuthority
from .journal_storage import PlatformJournalStorage
from .platform_keys import PlatformKeyProvider
from .producer_policy import ProducerPolicyAuthority
from .producer_policy_storage import PlatformProducerPolicyStorage


@dataclass(frozen=True, slots=True)
class TrustAuthorityContext:
    """The complete, externally provisioned dependency set for Trust actions."""

    platform_key_provider: object
    producer_policy_authority: ProducerPolicyAuthority
    producer_admission_certificate: Mapping[str, object]
    journal_authority: JournalAuthority
    journal_storage: PlatformJournalStorage

    def journal_context(self) -> dict[str, object]:
        return {
            "platform_key_provider": self.platform_key_provider,
            "producer_policy_authority": self.producer_policy_authority,
            "producer_admission_certificate": self.producer_admission_certificate,
            "journal_authority": self.journal_authority,
            "journal_storage": self.journal_storage,
        }


def provision_trust_authority_context() -> TrustAuthorityContext:
    """Provision and validate the sole production Trust publication path.

    This is deliberately the only production location that creates a Trust
    producer admission certificate.  Trust receives the finished immutable
    evidence and never constructs authorities or storage itself.
    """
    key_provider = PlatformKeyProvider()
    key_provider.provision()
    return _trust_authority_context(key_provider, permit_certificate_issuance=True)


def load_trust_authority_context() -> TrustAuthorityContext:
    """Compose runtime dependencies from already-provisioned platform state."""
    key_provider = PlatformKeyProvider()
    key_provider.startup_validate()
    return _trust_authority_context(key_provider, permit_certificate_issuance=False)


def _trust_authority_context(key_provider: PlatformKeyProvider, *, permit_certificate_issuance: bool) -> TrustAuthorityContext:
    policy = ProducerPolicyAuthority(signer=key_provider, storage=PlatformProducerPolicyStorage())
    policy.validate_policy_history()
    certificate = _trust_certificate(policy, permit_issuance=permit_certificate_issuance)
    storage = PlatformJournalStorage()
    journal = JournalAuthority(key_provider=key_provider, policy_authority=policy, storage=storage)
    journal.validate()
    return TrustAuthorityContext(
        platform_key_provider=key_provider,
        producer_policy_authority=policy,
        producer_admission_certificate=MappingProxyType(dict(certificate)),
        journal_authority=journal,
        journal_storage=storage,
    )


def _trust_certificate(policy: ProducerPolicyAuthority, *, permit_issuance: bool) -> dict[str, object]:
    for certificate_id in reversed(_certificate_ids(policy)):
        certificate = policy.resolve_admission_certificate(certificate_id)
        if (certificate.get("producer_authority_type") == "trust-authority"
                and certificate.get("producer_authority_id") == "trust-v1"
                and "trust-decision-envelope" in certificate.get("permitted_record_types", ())):
            policy.validate_admission_certificate(certificate, producer_authority_type="trust-authority",
                                                  producer_authority_id="trust-v1",
                                                  producer_record_type="trust-decision-envelope")
            return certificate
    if not permit_issuance:
        raise RuntimeError("Trust producer admission certificate is not provisioned")
    return policy.issue_admission_certificate(
        producer_authority_type="trust-authority", producer_authority_id="trust-v1",
        permitted_record_types=("trust-decision-envelope",), producer_key_reference="platform-key:active",
    )


def _certificate_ids(policy: ProducerPolicyAuthority) -> tuple[str, ...]:
    path = policy._storage.certificate_path()  # Authority-owned immutable evidence, read only here.
    if not path.exists():
        return ()
    import json
    return tuple(json.loads(line)["certificate_id"] for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
