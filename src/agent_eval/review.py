"""Offline annotation page: no account, server, or remote data transfer."""

import json
from pathlib import Path


def export_review(bundle: dict, path: Path) -> None:
    payload = (
        json.dumps(bundle).replace("<", "\\u003c").replace(">", "\\u003e").replace("&", "\\u0026")
    )
    path.write_text(PAGE.replace("__BUNDLE__", payload), encoding="utf-8")


PAGE = """<!doctype html><html lang="en"><meta charset="utf-8">
<title>Agent evaluator review</title>
<style>body{font:16px system-ui;margin:30px auto;max-width:1200px;background:#f5f7fa;color:#172334}main{display:grid;grid-template-columns:1fr 1fr;gap:24px}section{background:white;padding:20px;border-radius:12px}pre{white-space:pre-wrap;overflow-wrap:anywhere}textarea{width:95%;min-height:65px}article{border-top:1px solid #ccc;padding:15px 0}button,input,select{padding:8px;margin:6px}label{display:block}small{display:block}</style>
<h1>Independent agent review</h1>
<p>Review the evidence independently. Model identity and other reviewers' judgments are hidden. Export your work before closing this page; it is not saved automatically.</p>
<label>Reviewer ID <input id="reviewer" required></label>
<label>Case <select id="cases"></select></label>
<button id="download">Export annotation JSON</button>
<label>Resume your own export <input id="resume" type="file" accept=".json"></label>
<p id="status" role="status"></p>
<main><section><h2>Input and evidence</h2><pre id="input"></pre><h2>Tool trace and final state</h2><pre id="trace"></pre></section>
<section><h2>Agent output</h2><pre id="output"></pre><label>Independent critique: what matters that the rubric misses?<textarea id="critique"></textarea></label><div id="questions"></div></section></main>
<script type="application/json" id="bundle">__BUNDLE__</script>
<script>
const b=JSON.parse(document.getElementById('bundle').textContent), records=new Map(), critiques={};
const el=id=>document.getElementById(id), key=(c,r)=>JSON.stringify([c,r]);
for(const c of b.cases){const o=document.createElement('option');o.value=c.id;o.textContent=c.id;el('cases').append(o)}
function render(){const c=b.cases.find(c=>c.id===el('cases').value);
el('critique').value=critiques[c.id]||'';el('critique').oninput=()=>{critiques[c.id]=el('critique').value};
el('input').textContent=JSON.stringify(c.input,null,2);el('output').textContent=JSON.stringify(c.output,null,2);
el('trace').textContent=JSON.stringify({tool_trace:c.tool_trace,final_state:c.final_state},null,2);
el('questions').replaceChildren();
for(const r of b.rubric.criteria){const a=document.createElement('article'), title=document.createElement('strong'), help=document.createElement('p'), s=document.createElement('select'), t=document.createElement('textarea'), e=document.createElement('textarea');
title.textContent=r.question;help.textContent='Pass: '+r.pass_condition+' | Fail: '+r.fail_condition;
for(const v of ['', 'pass','fail','insufficient_context','not_applicable']){const o=document.createElement('option');o.value=v;o.textContent=v||'Choose verdict';s.append(o)}
t.placeholder='Explain your judgment';e.placeholder='Evidence quotes or tool references (one per line)';
s.setAttribute('aria-label',r.id+' verdict');t.setAttribute('aria-label',r.id+' rationale');e.setAttribute('aria-label',r.id+' evidence');
const old=records.get(key(c.id,r.id));if(old){s.value=old.verdict;t.value=old.rationale;e.value=old.evidence.join('\\n')}
function save(){records.set(key(c.id,r.id),{case_id:c.id,criterion_id:r.id,verdict:s.value,rationale:t.value,evidence:e.value.split('\\n').filter(Boolean)})}
s.onchange=save;t.oninput=save;e.oninput=save;a.append(title,help,s,t,e);el('questions').append(a)}}
el('cases').onchange=render;
el('download').onclick=()=>{if(!el('reviewer').value.trim()){el('status').textContent='Enter your reviewer ID.';return}
const judgments=[...records.values()].filter(j=>j.verdict);
if(judgments.some(j=>!j.rationale.trim())){el('status').textContent='Explain every selected verdict before exporting.';return}
const data={schema_version:'1',dataset_hash:b.dataset_hash,rubric_hash:b.rubric_hash,rubric_id:b.rubric.id,rubric_version:b.rubric.version,evaluator_id:el('reviewer').value.trim(),kind:'human',created_at:new Date().toISOString(),judgments,metadata:{freeform_critiques:critiques}};
const url=URL.createObjectURL(new Blob([JSON.stringify(data,null,2)],{type:'application/json'})),a=document.createElement('a');a.href=url;a.download='annotations.json';a.click();setTimeout(()=>URL.revokeObjectURL(url),1000);el('status').textContent='Exported '+judgments.length+' judgments. Partial submissions are allowed.'};
el('resume').onchange=async()=>{try{const d=JSON.parse(await el('resume').files[0].text());
if(d.dataset_hash!==b.dataset_hash||d.rubric_hash!==b.rubric_hash||d.kind!=='human')throw Error('Dataset/rubric mismatch or nonhuman submission');
records.clear();for(const k of Object.keys(critiques))delete critiques[k];Object.assign(critiques,d.metadata?.freeform_critiques||{});for(const j of d.judgments)records.set(key(j.case_id,j.criterion_id),j);el('reviewer').value=d.evaluator_id;render();el('status').textContent='Resumed your export.'}catch(e){el('status').textContent=e.message}};render();
</script></html>"""
