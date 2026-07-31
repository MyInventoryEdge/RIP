from __future__ import annotations
import hashlib, mimetypes
from pathlib import Path
from typing import Any

def load_primary_evidence(root: Path, observations, paths: list[str]) -> list[dict[str, Any]]:
    observed={item.relative_path:item for item in observations.observations}
    loaded=[]
    for requested in paths:
        relative=Path(requested)
        if relative.is_absolute() or '..' in relative.parts: raise ValueError(f"Primary evidence path is not repository-relative: {requested}")
        target=(root/relative).resolve()
        if root not in target.parents or not target.is_file(): raise ValueError(f"Primary evidence is not a repository file: {requested}")
        raw=target.read_bytes()
        try: content=raw.decode('utf-8')
        except UnicodeDecodeError as exc: raise ValueError(f"Primary evidence is not UTF-8: {requested}") from exc
        key=target.relative_to(root).as_posix(); observation=observed.get(key)
        digest=hashlib.sha256(raw).hexdigest()
        if observation and observation.metadata.get('sha256') and observation.metadata['sha256'] != digest: raise ValueError(f"Primary evidence changed after observation: {key}")
        loaded.append({'repository_relative_path':key,'source_observation_id':observation.observation_id if observation else None,'media_type':mimetypes.guess_type(target.name)[0] or 'application/octet-stream','encoding':'utf-8','byte_size':len(raw),'content_hash':digest,'load_status':'loaded','truncated':False,'chunked':False,'content':content})
    return loaded
