from __future__ import annotations

import html
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def render_knowledge(input_path: Path, output_directory: Path) -> dict[str, object]:
    data = load_candidates(input_path)
    candidates = data["candidates"]
    run = load_manifest(input_path.parent)
    output_directory.mkdir(parents=True, exist_ok=True)
    html_path, markdown_path = output_directory / "candidate-review.html", output_directory / "candidate-review.md"
    html_path.write_text(render_html(data, run), encoding="utf-8")
    markdown_path.write_text(render_markdown(data), encoding="utf-8")
    return {"candidates": len(candidates), "html": html_path, "markdown": markdown_path}


def load_candidates(path: Path) -> dict[str, Any]:
    try: data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc: raise ValueError(f"Candidate knowledge is not valid JSON: {path}") from exc
    if not isinstance(data, dict) or not isinstance(data.get("candidates"), list): raise ValueError("Candidate knowledge must contain a candidates array.")
    seen=set()
    for n, c in enumerate(data["candidates"], 1):
        if not isinstance(c, dict): raise ValueError(f"Candidate {n} is not an object.")
        for key in ("id","type","status","title","summary","reasoning","source_session"):
            if not isinstance(c.get(key), str) or not c[key]: raise ValueError(f"Candidate {n} has missing {key}.")
        if c["id"] in seen: raise ValueError(f"Duplicate candidate ID: {c['id']}")
        seen.add(c["id"]); confidence=c.get("confidence")
        if isinstance(confidence, bool) or not isinstance(confidence,(int,float)) or not 0<=confidence<=1: raise ValueError(f"Candidate {n} has invalid confidence.")
        if not isinstance(c.get("evidence"),list): raise ValueError(f"Candidate {n} has invalid evidence.")
        for e in c["evidence"]:
            if not isinstance(e,dict) or not isinstance(e.get("message_id"),str) or not isinstance(e.get("excerpt"),str): raise ValueError(f"Candidate {n} has malformed evidence.")
    return data


def load_manifest(directory: Path) -> dict[str, Any]:
    path=directory/'interpretation-manifest.json'
    if not path.exists(): return {}
    try: return json.loads(path.read_text(encoding='utf-8'))
    except json.JSONDecodeError: return {}


def render_markdown(data: dict[str, Any]) -> str:
    lines=['# Candidate Knowledge Review','',f"Source session: {data.get('source_session','Unknown')}",'']
    for n,c in enumerate(data['candidates'],1):
        lines += [f"## Candidate {n} — {c['title']}",'',f"**ID:** {c['id']}",f"**Type:** {c['type']}",f"**Status:** {c['status']}",f"**Confidence:** {c['confidence']}",'','### Summary','',c['summary'],'','### Reasoning','',c['reasoning'],'','### Evidence','']
        for i,e in enumerate(c['evidence'],1): lines += [f"#### Evidence {i} — {e['message_id']}",'',f"> {e['excerpt']}",'',f"Offsets: {e.get('start_offset','?')}–{e.get('end_offset','?')}",'']
    return '\n'.join(lines)


def render_html(data: dict[str, Any], manifest: dict[str, Any]) -> str:
    candidates=data['candidates']; avg=sum(c['confidence'] for c in candidates)/len(candidates) if candidates else 0
    cards=[]
    for original,c in enumerate(candidates,1):
        evidence=''.join(f"<details><summary>{html.escape(e['message_id'])}</summary><pre>{html.escape(e['excerpt'])}</pre><small>Offsets: {e.get('start_offset','?')}–{e.get('end_offset','?')}</small></details>" for e in c['evidence'])
        cards.append(f'<article class="card" data-original="{original}" data-confidence="{c["confidence"]}"><h2>{original}. {html.escape(c["title"])}</h2><dl><dt>ID</dt><dd>{html.escape(c["id"])}</dd><dt>Type</dt><dd>{html.escape(c["type"])}</dd><dt>Status</dt><dd>{html.escape(c["status"])}</dd><dt>Confidence</dt><dd>{c["confidence"]:.2f}</dd></dl><h3>Summary</h3><p>{html.escape(c["summary"])}</p><h3>Reasoning</h3><p>{html.escape(c["reasoning"])}</p><h3>Evidence ({len(c["evidence"])})</h3>{evidence}</article>')
    meta=f"Source session: {html.escape(str(data.get('source_session','Unknown')))} | Run: {html.escape(str(manifest.get('input','Unknown')))} | Model: {html.escape(str(manifest.get('model','Unknown')))} | Prompt: {html.escape(str(manifest.get('prompt_version','Unknown')))} | Candidates: {len(candidates)} | Average confidence: {avg:.2f} | Evidence messages: {manifest.get('messages_with_evidence','Unknown')} | Validation: {manifest.get('validation','Unknown')} | Generated: {datetime.now(timezone.utc).isoformat()}"
    return f'''<!doctype html><html><head><meta charset="utf-8"><title>Candidate Knowledge Review</title><style>body{{font:16px system-ui;margin:2rem;max-width:1000px}}.card{{border:1px solid #bbb;padding:1rem;margin:1rem 0}}pre{{white-space:pre-wrap}}dt{{font-weight:bold}}dd{{margin:0 0 .5rem}}</style></head><body><h1>Candidate Knowledge Review</h1><p>{meta}</p><input id="search" placeholder="Search"><input id="minimum" type="number" min="0" max="1" step=".01" value="0"><select id="sort"><option value="confidence">Highest confidence</option><option value="original">Original order</option><option value="low">Lowest confidence</option><option value="title">Title</option></select><button onclick="document.querySelectorAll('details').forEach(x=>x.open=true)">Expand evidence</button><button onclick="document.querySelectorAll('details').forEach(x=>x.open=false)">Collapse evidence</button><nav id="toc"></nav><main id="cards">{''.join(cards)}</main><script>const cards=[...document.querySelectorAll('.card')],q=document.querySelector('#search'),m=document.querySelector('#minimum'),s=document.querySelector('#sort');function go(){{let a=cards.filter(x=>x.innerText.toLowerCase().includes(q.value.toLowerCase())&&+x.dataset.confidence>=+m.value);a.sort((x,y)=>s.value=='original'?x.dataset.original-y.dataset.original:s.value=='low'?x.dataset.confidence-y.dataset.confidence:s.value=='title'?x.querySelector('h2').innerText.localeCompare(y.querySelector('h2').innerText):y.dataset.confidence-x.dataset.confidence||x.querySelector('dd').innerText.localeCompare(y.querySelector('dd').innerText));let box=document.querySelector('#cards');a.forEach(x=>box.append(x));cards.filter(x=>!a.includes(x)).forEach(x=>x.hidden=true);a.forEach(x=>x.hidden=false);document.querySelector('#toc').innerHTML=a.map(x=>'<a href="#">'+x.querySelector('h2').innerText+'</a> ').join('')}}[q,m,s].forEach(x=>x.oninput=go);go()</script></body></html>'''
