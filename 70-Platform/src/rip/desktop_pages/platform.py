"""Operator health projection over existing validation boundaries."""
from __future__ import annotations
from dataclasses import dataclass
from ..foundation.loader import load_foundation
from ..platform_provisioning import load_trust_authority_context
from ..build_identity import runtime_identity

@dataclass(frozen=True, slots=True)
class PlatformHealth:
    components: tuple[tuple[str,str,str],...]

def verify_platform() -> PlatformHealth:
    components=list(runtime_identity())
    try:
        load_foundation(); components.append(("Foundation","Healthy","Foundation evidence is available."))
    except Exception:
        components.append(("Foundation","Attention Required","Foundation evidence needs attention."))
    try:
        load_trust_authority_context()
        components.extend((
            ("Provisioning","Healthy","Platform provisioning is available."),("Journal","Healthy","Journal verification is available."),
            ("Producer Policy","Healthy","Policy verification is available."),("Trust","Healthy","Trust runtime is available."),
            ("Platform Key","Healthy","Platform key is available."),("Storage","Healthy","Platform storage is available."),))
    except Exception:
        components.extend((
            ("Provisioning","Attention Required","Platform provisioning requires attention."),("Journal","Unavailable","Journal verification is unavailable."),
            ("Producer Policy","Unavailable","Policy verification is unavailable."),("Trust","Unavailable","Trust runtime is unavailable."),
            ("Platform Key","Unavailable","Platform key unavailable."),("Storage","Attention Required","Platform storage requires attention."),))
    return PlatformHealth(tuple(components))
