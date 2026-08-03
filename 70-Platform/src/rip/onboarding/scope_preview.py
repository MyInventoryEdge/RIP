"""Deterministic, retained-manifest scope previews for future decision acceptance."""
from __future__ import annotations
from dataclasses import dataclass
from .classification import ClassificationScope, EvidenceClass, EvidenceClassification, IntegrityTreatment
from .classification_engine import _matches
from .models import fingerprint

@dataclass(frozen=True, slots=True)
class ScopePreview:
    target: str; scope: ClassificationScope; manifest_fingerprint: str; total_matches: int
    counts_by_kind: tuple[tuple[str,int],...]; example_paths: tuple[str,...]; matched_set_fingerprint: str; fingerprint: str
    @property
    def requires_large_scope_acknowledgment(self) -> bool: return self.total_matches > 10000

def preview_scope(manifest: dict[str,object], *, target: str, scope: ClassificationScope) -> ScopePreview:
    mf=manifest.get('manifest_fingerprint'); entries=manifest.get('entries')
    if not isinstance(mf,str) or not isinstance(entries,list): raise ValueError('retained manifest is required')
    probe=EvidenceClassification('preview','preview-org','preview-run',target,scope,EvidenceClass.UNKNOWN,IntegrityTreatment.BLOCKING,mf,'preview','0'*64,None,'0'*64)
    matched=tuple(item for item in entries if _matches(probe,item['path']))
    if not matched: raise ValueError('scope preview is empty')
    kinds=tuple(sorted((kind,sum(item.get('kind')==kind for item in matched)) for kind in sorted({item.get('kind') for item in matched})))
    matched_fp=fingerprint(tuple((item.get('path'),item.get('kind'),item.get('value'),item.get('size')) for item in matched))
    payload={'target':target,'scope':scope.value,'manifest_fingerprint':mf,'total_matches':len(matched),'counts_by_kind':kinds,'example_paths':tuple(item['path'] for item in matched[:100]),'matched_set_fingerprint':matched_fp}
    return ScopePreview(target,scope,mf,len(matched),kinds,payload['example_paths'],matched_fp,fingerprint(payload))

def validate_preview(preview: ScopePreview, manifest: dict[str,object]) -> None:
    current=preview_scope(manifest,target=preview.target,scope=preview.scope)
    if current.manifest_fingerprint != preview.manifest_fingerprint or current.matched_set_fingerprint != preview.matched_set_fingerprint: raise ValueError('scope preview is stale')
