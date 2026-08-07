"""Deterministic governed memory: retained history, bounded context, no AI promotion."""
from __future__ import annotations
import hashlib, json, os, re, uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from .paths import storage_directory

SCHEMA="rip.governed-memory.v1"; CONTEXT_SCHEMA="rip.context-package.v1"
VALID_STATUS=frozenset({"Candidate","Observed","Confirmed","Authoritative","Superseded","Historical"})
_WORDS=re.compile(r"[a-z0-9][a-z0-9_-]*")
def _now(): return datetime.now(timezone.utc).isoformat()
def _hash(value): return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(",",":"),default=str).encode()).hexdigest()
def _tokens(text): return frozenset(_WORDS.findall(text.casefold()))

@dataclass(frozen=True, slots=True)
class MemoryRecord:
    memory_id:str; organization_id:str; repository_id:str; project_scope:str; memory_type:str; statement:str; status:str; confidence:str; created_at:str; effective_at:str; last_validated_at:str; authority:str; source_records:tuple[str,...]; supporting_evidence:tuple[str,...]; contradicts:tuple[str,...]=(); supersedes:tuple[str,...]=(); superseded_by:tuple[str,...]=(); tags:tuple[str,...]=(); schema:str=SCHEMA; content_hash:str=""
    def __post_init__(self):
        if self.status not in VALID_STATUS or not all((self.organization_id,self.repository_id,self.memory_type,self.statement,self.authority)): raise ValueError("invalid governed memory record")
        if self.content_hash and self.content_hash != _hash({k:v for k,v in asdict(self).items() if k!="content_hash"}): raise ValueError("memory content hash mismatch")
    @classmethod
    def create(cls, *, organization_id, repository_id, project_scope, memory_type, statement, status, confidence, authority, source_records=(), supporting_evidence=(), tags=(), **relations):
        if status in {"Confirmed","Authoritative"} and authority == "model-inference": raise ValueError("model inference cannot become governed truth")
        now=_now(); base=dict(memory_id="mem-"+uuid.uuid4().hex,organization_id=organization_id,repository_id=repository_id,project_scope=project_scope,memory_type=memory_type,statement=statement,status=status,confidence=confidence,created_at=now,effective_at=now,last_validated_at=now,authority=authority,source_records=tuple(source_records),supporting_evidence=tuple(supporting_evidence),contradicts=tuple(relations.get("contradicts",())),supersedes=tuple(relations.get("supersedes",())),superseded_by=(),tags=tuple(tags),schema=SCHEMA)
        return cls(**base,content_hash=_hash(base))

@dataclass(frozen=True, slots=True)
class ContextPackage:
    objective:str; organization_id:str; repository_id:str; scope:str; authority_context:str; selected:tuple[MemoryRecord,...]; excluded_count:int; context_budget:int; estimated_size:int; coverage_statement:str; schema:str=CONTEXT_SCHEMA; strategy:str="metadata-lexical-relationships"; version:str="v1"

class MemoryStore:
    def __init__(self, root:Path|None=None): self.root=root or storage_directory("State") / "governed-memory"
    def _path(self, org, repo): return self.root / org / (repo+".ndjson")
    def load(self, org, repo):
        path=self._path(org,repo)
        if not path.exists(): return ()
        try: return tuple(MemoryRecord(**json.loads(line)) for line in path.read_text(encoding="utf-8").splitlines() if line.strip())
        except Exception as exc: raise ValueError("governed memory evidence is unreadable") from exc
    def save(self, record:MemoryRecord):
        existing=self.load(record.organization_id,record.repository_id)
        if any(item.memory_id==record.memory_id for item in existing): return record
        path=self._path(record.organization_id,record.repository_id); path.parent.mkdir(parents=True,exist_ok=True)
        temporary=path.with_suffix(".tmp"); temporary.write_text("\n".join(json.dumps(asdict(x),sort_keys=True) for x in (*existing,record))+"\n",encoding="utf-8"); os.replace(temporary,path); return record
    def promote(self, record:MemoryRecord):
        existing=self.load(record.organization_id,record.repository_id); matches=[x for x in existing if _tokens(x.statement)==_tokens(record.statement) and x.status!="Superseded"]
        if matches: return "matching",matches[0]
        conflicts=[x for x in existing if _tokens(x.statement)&_tokens(record.statement) and x.memory_type==record.memory_type and x.status in {"Confirmed","Authoritative"}]
        if record.supersedes:
            return "superseding",self.save(record)
        if conflicts: return "contradicting",self.save(record)
        return "new",self.save(record)

def retrieve(records:Iterable[MemoryRecord], *, organization_id:str, repository_id:str, scope:str, query:str, budget:int=4000)->ContextPackage:
    scoped=[r for r in records if r.organization_id==organization_id and r.repository_id==repository_id and (not scope or r.project_scope in {scope,"platform"}) and r.status not in {"Superseded","Historical"}]
    q=_tokens(query); ranked=sorted(scoped,key=lambda r:(-len(q&_tokens(r.statement+" "+" ".join(r.tags))), 0 if r.status=="Authoritative" else 1, r.memory_id))
    selected=[]; size=len(query); selected_ids=set()
    for r in ranked:
        cost=max(1,len(r.statement)//4)
        if size+cost>budget: continue
        selected.append(r); selected_ids.add(r.memory_id); size+=cost
    # direct relationship expansion only when it fits.
    related={link for r in selected for link in (*r.contradicts,*r.supersedes,*r.superseded_by)}
    for r in ranked:
        if r.memory_id in related and r.memory_id not in selected_ids and size+len(r.statement)//4<=budget: selected.append(r); size+=len(r.statement)//4
    if scoped and not selected: raise ValueError("insufficient context budget for applicable governed memory")
    coverage="Complete applicable memory selected." if len(selected)==len(scoped) else f"Partial coverage: {len(scoped)-len(selected)} applicable record(s) excluded by context budget."
    return ContextPackage(query,organization_id,repository_id,scope,"governed-memory",tuple(selected),len(scoped)-len(selected),budget,size,coverage)

def checkpoint(*, store:MemoryStore, organization_id:str, repository_id:str, project_scope:str, historical_record:str, promotions:Iterable[MemoryRecord]=()):
    # History is append-only operational evidence; no promotion is inferred here.
    path=store.root / organization_id / (repository_id+"-history.ndjson"); path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("a",encoding="utf-8") as handle: handle.write(json.dumps({"record":historical_record,"retained_at":_now()},sort_keys=True)+"\n")
    return tuple(store.promote(record) for record in promotions)

def seed_observed_projection(*, store:MemoryStore, organization_id:str, repository_id:str, repository_memory) -> tuple[MemoryRecord,...]:
    """Promote only deterministic Repository Memory observations, never inference."""
    statements=(
        ("repository", f"Observed repository identity: {repository_memory.repository}.", ("context.json",)),
        ("architecture", "Observed architecture areas: " + ", ".join(repository_memory.observed_areas) + ".", ("final-source-manifest.json",)),
        ("capability", "Observed capabilities: " + ", ".join(repository_memory.capabilities) + ".", ("retained observation evidence",)),
    )
    output=[]
    for memory_type,statement,evidence in statements:
        record=MemoryRecord.create(organization_id=organization_id,repository_id=repository_id,project_scope="platform",memory_type=memory_type,statement=statement,status="Observed",confidence="High",authority="deterministic-observation",source_records=evidence,supporting_evidence=evidence,tags=(organization_id,repository_id,memory_type))
        output.append(store.promote(record)[1])
    return tuple(output)
