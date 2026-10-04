"""Build the meeting brief from frozen predictions and reports, without API calls.

Run from the repository root: python -m research.build_professor_brief
Matplotlib is required only to render the shareable PNG/SVG table.
Existing predictions, protocols and primary reports are never rewritten.
"""
import hashlib
import html
import json
import os
import tempfile
from pathlib import Path

from .comparison_table import make_row
from .metrics import aggregate, outcomes
from .select_pilot import read_jsonl

ROOT = Path(__file__).resolve().parent
PILOT = ROOT / 'artifacts/pilot'
OUT = ROOT / 'results/professor_brief'
ARMS = [('opus_direct', 'Claude Opus 5.5', 'Direct'),
        ('qwen8_direct', 'Qwen3-8B', 'Direct'),
        ('qwen30_direct', 'Qwen3-30B-A3B', 'Direct'),
        ('qwen30_evidence', 'Qwen3-30B-A3B', 'Evidence → decision')]
COLS = [('model','Model'),('method','Setup'),('valid','Valid / 48'),
        ('general','General / 48'),('clean','Clean / 16'),
        ('error_type','Error type / 32'),('error_entry','Error entry / 32'),
        ('topic','Topic / 16'),('subtopic','Subtopic / 16'),
        ('full_citation','Full citation / 16'),('input_tokens','Input tokens'),
        ('output_tokens','Output tokens'),('latency','API latency')]


def load(path):
    return json.loads(path.read_text())


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def metric_text(m):
    return f'{100*m["value"]:.1f}% ({m["numerator"]}/{m["denominator"]})'


def verify_and_collect():
    manifest = load(PILOT / 'manifest.json')
    report = load(PILOT / 'report.json')
    saved = load(ROOT / 'results/comparison_table.json')
    paths = [PILOT/'manifest.json', PILOT/'report.json', PILOT/'public_inputs.jsonl',
             PILOT/'scoring_only.jsonl', ROOT/'results/comparison_table.json']
    assert digest(PILOT/'public_inputs.jsonl') == manifest['public_input_sha256']
    assert digest(PILOT/'scoring_only.jsonl') == manifest['scoring_key_sha256']
    inputs = list(read_jsonl(PILOT/'public_inputs.jsonl'))
    gold = {r['case_id']:r['gold'] for r in read_jsonl(PILOT/'scoring_only.jsonl')}
    ids = {r['case_id'] for r in inputs}
    assert len(inputs) == len(ids) == 48 and set(gold) == ids
    assert len({c['metadata']['company'] for c in inputs}) == 8
    assert sum(g['general_judgement']=='Correct' for g in gold.values()) == 16
    rows = []
    for condition, model, method in ARMS:
        pred_path = PILOT/'predictions'/f'{condition}.jsonl'
        paths.append(pred_path)
        preds = list(read_jsonl(pred_path))
        assert len(preds) == 48 and {p['case_id'] for p in preds} == ids
        recomputed = aggregate([{'outcomes':outcomes(gold[p['case_id']],p)} for p in preds])
        recorded = report['conditions'][condition]
        for metric, value in recomputed.items():
            for key in ('value','numerator','denominator'):
                assert recorded['metrics'][metric][key] == value[key], (condition,metric,key)
        row = make_row(report,condition,model,method,pred_path,PILOT/'responses')
        assert row == next(r for r in saved['primary_rows'] if r['condition']==condition)
        for pred in preds:
            paths.extend(PILOT/'responses'/f'{cid}.json' for cid in pred['trace'])
        row.update(method=method,valid=f'{recorded["statuses"].get("ok",0)}/48',
                   clean=metric_text(recomputed['clean_specificity']),
                   clean_count=recomputed['clean_specificity'],
                   joint_full=metric_text(recomputed['joint_detection_type_row_full_citation']))
        for key in ('general','error_type','error_entry','topic','subtopic','full_citation'):
            count=row['counts'][key]
            row[key] += f' ({count["numerator"]}/{count["denominator"]})'
        rows.append(row)
    offline=[]
    for name in ('legacy_local_offline','legacy_local_adapted_verified_citation'):
        path=PILOT/f'{name}_metrics.json';paths.append(path)
        offline.append(load(path)['conditions'][name]['metrics'])
    audit_path=ROOT/'artifacts/phase2/candidate_audit_v3/candidate_audit.json'
    audit=load(audit_path);paths.append(audit_path)
    assert audit['manifest']['public_input_sha256'] == manifest['public_input_sha256']
    assert audit['scoring_key_sha256'] == manifest['scoring_key_sha256']
    for filename,field in [('candidate_cache.jsonl','candidate_cache_sha256'),('taxonomy_inventory.json','taxonomy_inventory_sha256')]:
        path=audit_path.parent/filename
        assert digest(path)==audit['manifest'][field];paths.append(path)
    paths.extend([Path(__file__),ROOT/'metrics.py',ROOT/'comparison_table.py'])
    return rows,offline,audit,report['cost_summary'],{
        'scope':'Complete recorded development snapshot; accounting labels remain provisional',
        'n_cases':48,'n_companies':8,'model_calls_for_brief':0,
        'verification':'All primary metric counts rederived from saved predictions; resource table rederived from request traces; frozen public/key and candidate hashes matched.',
        'source_sha256':{str(p.relative_to(ROOT)):digest(p) for p in sorted(set(paths))}}


def table_html(rows,cols):
    return '<table><thead><tr>'+''.join('<th>'+html.escape(v)+'</th>' for _,v in cols)+'</tr></thead><tbody>'+''.join('<tr>'+''.join('<td>'+html.escape(str(r[k]))+'</td>' for k,_ in cols)+'</tr>' for r in rows)+'</tbody></table>'


def main():
    rows,offline,audit,cost,verification=verify_and_collect()
    OUT.mkdir(exist_ok=True,parents=True)
    lines=['# Professor briefing: verified development results','',
    '**Meeting message:** We completed a reproducible development audit and identified concrete evaluation, retrieval and evidence-validity bottlenecks. We have not demonstrated cheap-model superiority or completed accountant validation.','',
    '## 1. Main results table','',
    'All four primary conditions attempted the same 48 cases from eight companies (FY2020–2024): 16 clean, 16 detection-only and 16 provisionally citable. Figures use the original strict scoring contract and a 900-completion-token cap per call. Direct conditions are closed-book for standards; the two-call evidence condition extracts supplied evidence before deciding and adds no standards corpus.','',
    '| '+' | '.join(v for _,v in COLS)+' |','| '+' | '.join('---' for _ in COLS)+' |']
    lines += ['| '+' | '.join(str(r[k]) for k,_ in COLS)+' |' for r in rows]
    lines += ['',
    '**Definitions:** General = correct overall judgment on all 48 cases. Clean = valid correct judgments on the 16 clean controls. Error type and error entry each require an incorrect judgment and the matching field, on 32 injected cases. Topic/subtopic/full citation require a schema-valid prediction and a full-code prediction matching the respective key level, on 16 citable cases. Full-citation agreement alone does not require joint judgment/type/row correctness. Joint judgment/type/row/full-citation scores are Opus 11/16, Qwen8 0/16, Qwen30 direct 2/16 and Qwen30 evidence 0/16.','',
    '**All errors remain visible:** Opus has 29 valid, 18 format-invalid and one empty response. Qwen8 has 47 valid and one invalid. Qwen30 direct has 16 valid, 31 API errors and one invalid. Qwen30 evidence has three valid, 33 API errors and twelve invalid. All 48 cases were attempted in each primary condition; completed data collection includes recorded failures.','',
    '**Do not rank model capability from the General column:** an always-incorrect rule gets 32/48 = 66.7% general agreement and 0/16 clean specificity. Qwen8 flags all clean controls; its 64.6% general score is not evidence that it outperforms Opus. Opus primary scores are also depressed by format failures. The Qwen30 rows describe a heavily service-limited run.','',
    '**Resource definitions:** tokens are mean summed usage over requested stages per case with complete usage; n is the measured-case count. API latency is summed request duration per attempted case, including fast failures; it excludes pacing/local processing. Do not interpret Qwen30 rate-limit failures as a speed advantage. No resource value is imputed as zero.','',
    '**Scientific scope:** scores measure agreement with provisional author labels on synthetic supporting evidence. They do not establish standards applicability, real audit performance or a population ranking. With 16 citation cases, one case changes the displayed score by 6.25 percentage points. Eight company clusters provide limited uncertainty evidence. The old screenshot has different unverified provenance and cannot serve as a before/after comparison.','',
    '## 2. Completed engineering result','',
    '| Same offline 48-case diagnostic | Original interface | Parser repair + applicability safeguard |','|---|---:|---:|']
    for key,label in [('detection_sensitivity','Injected errors detected'),('joint_detection_type_row','Joint judgment + type + row'),('unvalidated_full_citation_agreement','Full citation agreement'),('decision_abstention_rate','Decision abstention'),('citation_abstention_rate','Citation abstention')]:
        lines.append('| '+label+' | '+metric_text(offline[0][key])+' | '+metric_text(offline[1][key])+' |')
    lines += ['',
    'This verifies a parser/interface repair at zero API cost. It uses synthetic component evidence, offline taxonomy and no Stage 2 LLM. It is not an end-to-end model-versus-pipeline comparison. All sixteen clean cases remain decision abstentions; zero emitted false alarms here is not a clean-specificity success. The final citation safeguard withholds every unverified citation; paragraph agreement remains zero.','',
    '## 3. Completed retrieval diagnosis','',
    '| Candidate source | Provisional target labels present |','|---|---:|']
    for name,label in [('oracle_gold_row_top8','Gold-row top-eight candidates (oracle diagnostic)'),('public_union_displayed','Displayed candidate union across all observable rows'),('public_union_unbounded','Unbounded candidate union across all observable rows'),('anywhere_in_taxonomy','Anywhere in the complete downloaded 2023 reference linkbase')]:
        m=audit['coverage'][name];lines.append(f'| {label} | {m["hits"]}/{m["denominator"]} ({100*m["rate"]:.1f}%) |')
    lines += ['',
    'The observable-row candidate cache was saved before joining the answer key. Gold-row analysis is explicitly an oracle diagnostic. Broadening top-k alone did not improve coverage in this sample. Ten of sixteen targets are absent from this specific reference metadata; they are not thereby absent from the Codification or invalid. Linkbase presence also does not prove paragraph applicability. This motivates an issue-conditioned, dated authority corpus and evidence applicability checks; the proposed method remains to be tested.','',
    '## 4. Demonstration and next measurable milestone','',
    'Demo the IntelliAudit blind dashboard: initial judgment → preserved submission → explicit proposal reveal → separate reconciliation. A deterministic twenty-case/five-company revenue-cutoff review pilot is prepared, including ten evidence-withheld variants. Zero accountant reviews are claimed. Source clean/fault pairs are not validated minimal counterfactuals; missing one fact does not prove undecidability.','',
    'For actual review, collect all initial judgments and a preselected delayed repeat of 2–4 cases before any proposal reveal. One accountant supports single-expert review and intra-rater repeat consistency. Source accession/unit/period, authority dates/applicability, acceptable proof alternatives and ambiguity must be resolved before freezing gold. The current publication gate correctly blocks all twenty cases.','',
    'Next acceptance criterion: every proposed release item has a documented review and disposition; source and authority issues are resolved or explicitly excluded before seeing final model performance. Then freeze a fresh grouped test and compare one frontier family with cheap models under matched evidence/tool access. Keep this inspected 48-case sample as development data.','',
    '## Suggested 60-second explanation','',
    '> We now have a reproducible 48-case development study with strict metrics and all failures accounted for. Opus agrees with 11 of 16 provisional paragraph labels; the small Qwen model agrees with none and fails every clean control. We repaired an interface defect that now detects six errors in a separate offline diagnostic, but citation performance has not improved. We also found that the entire downloaded reference linkbase contains only six of the sixteen target labels, so candidate reranking alone cannot resolve the current mismatch. We have built a blind, versioned review workflow and twenty narrow review cases. The next milestone is to validate evidence sufficiency and dated accounting applicability with our accountant, then run a frozen matched comparison.','',
    '## Questions to expect','',
    '- **Have we beaten Opus?** No. No recorded experiment establishes that claim.',
    '- **Is 68.8% an improvement over the old 12.2% pipeline result?** No. It is an Opus direct score on a different verified cohort and metric contract.',
    '- **Why is General so low?** It includes format/API failures, and clean controls expose overcalling. Validity and delivery reliability both affect these system scores.',
    '- **Can we show the 81.25% Opus figure?** Only as an explicitly post-hoc field-level format diagnostic, alongside its original 11/16 strict result. It is not a new pipeline gain.',
    '- **Why not use the structured Opus and Qwen8 follow-ups as headline rows?** Both stopped early after provider errors and changed settings/method. They remain in the existing comparison appendix with missing cases counted.',
    '- **What is novel?** The candidate contribution is evidence sufficiency, alternative acceptable proofs and dated authority under a cost budget. Novelty and effectiveness are still hypotheses; graphs/tools/budgets alone are already in prior work.',
    '- **What can be finished by December?** A defensible narrow reviewed release, reproducible experiments and submission-ready preprint are goals; review completion and venue acceptance remain external dependencies.','',
    '## Reproduction and budget','',
    'Run `python -m research.build_professor_brief` from the repository root. The builder checks frozen input/key hashes, recomputes every primary metric count from saved predictions, checks table/resource equivalence against recorded traces, and verifies candidate-cache hashes. Matplotlib renders PNG/SVG; no API calls are made. `verification.json` lists exact source hashes. Existing raw outputs and primary reports are preserved.','',
    f'The recorded ledger subtotal is ${cost["reported_actual_usd"]}, with {cost["unpriced_response_count"]} unpriced responses and ${cost["reserved_upper_bound_usd"]} conservatively booked against the $5 development ceiling. The reported subtotal is incomplete and is not an exact account debit. No new model spending was required for this briefing.','',
    'Software verification previously recorded: capstone 95 tests; IntelliAudit 85 tests; deterministic pilot rebuild and live desktop/mobile review workflow pass. These are engineering checks. Accountant validation remains pending.','',
    'Source map: `../comparison_table.json`; `../../artifacts/pilot/report.json` and predictions/responses; `../../artifacts/phase2/candidate_audit_v3/`. For current IntelliAudit delivery, see `../../handoff/README.md`; its exact review commit is bundled because direct upstream push was rejected.']
    (OUT/'brief.md').write_text('\n'.join(lines)+'\n')
    (OUT/'verification.json').write_text(json.dumps(verification,indent=2)+'\n')
    data={'rows':rows,'verification':verification,'always_incorrect_general':{'numerator':32,'denominator':48},'coverage':audit['coverage']}
    (OUT/'table.json').write_text(json.dumps(data,indent=2)+'\n')
    note='48 development cases · 8 companies · 16 clean / 16 detection-only / 16 provisionally citable · 900 completion tokens per call'
    page='''<!doctype html><html lang="en"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><meta http-equiv="Content-Security-Policy" content="default-src 'none'; style-src 'unsafe-inline'; img-src 'self'; base-uri 'none'"><title>Verified development results</title><style>
body{background:#0b111b;color:#edf2f9;font:15px/1.5 system-ui;margin:0;padding:30px}main{max-width:1880px;margin:auto}h1{font-size:30px;margin:8px 0}h2{font-size:20px;margin-top:30px}.kicker{color:#87c7ed;letter-spacing:.12em;font-size:12px}p{max-width:1250px;color:#bcc9da}.notice{border-left:4px solid #f2ca7d;background:#1b2230;padding:12px 18px;color:#f4d49d}.scroll{overflow:auto}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:16px 10px;border-bottom:1px solid #344054;text-align:center}th{background:#192638}td:first-child,td:nth-child(2){text-align:left}tr:nth-child(even){background:#111d2b}th{white-space:nowrap}a{color:#90cef4}.foot{font-size:13px}img{max-width:100%}@media print{body{background:white;color:black}p{color:#222}table{font-size:9px}th,tr:nth-child(even){background:#eee}.notice{color:black;background:#eee}@page{size:landscape;margin:10mm}}</style><main><div class="kicker">PROFESSOR BRIEFING · VERIFIED SAVED RESULTS</div><h1>Financial audit: development results and bottlenecks</h1>'''
    page+='<p>'+note+'</p><div class="notice">Provisional-label agreement. No validated accounting benchmark or cheap-model superiority claim.</div><div class="scroll">'+table_html(rows,COLS)+'</div>'
    page+='<p><strong>Critical control:</strong> always predicting “incorrect” gives 66.7% General and 0% Clean. Qwen8’s 64.6% General does not establish a frontier win. Opus has 19 format/empty failures; Qwen30 has 31 / 33 API errors.</p>'
    page+='<p class="foot">Failed/invalid outputs get zero credit in their eligible denominators. Tokens average cases with complete usage (n shown). Latency is API request time including failures, excluding pacing/local processing; rate-limit failures are not a speed advantage. Full citation is strict paragraph-label agreement; joint judgment/type/row/full-citation results are 11/16, 0/16, 2/16 and 0/16, respectively.</p>'
    page+='<h2>What is completed</h2><p>Reproducible 48-case study; offline parser repair raises detection from 0/32 to 6/32 and joint type/row detection from 0/32 to 4/32. Full citation stays 0/16. All 16 clean cases remain abstentions in that offline diagnostic.</p><h2>What the retrieval audit explains</h2><p>The displayed all-row candidate union contains 3/16 provisional targets; the entire downloaded 2023 reference linkbase contains 6/16. An unbounded row-candidate union still contains 3/16. This is reference coverage, not paragraph validity or an overall model-accuracy ceiling.</p><h2>Next milestone</h2><p>Complete the twenty-case/five-company blind accountant pilot and delayed repeated subset, reconcile evidence/provenance and dated authority, then freeze a fresh evaluation. Zero completed accountant reviews are claimed.</p><p><a href="brief.md">Detailed talk track, definitions, caveats and Q&amp;A</a> · <a href="table.png">Shareable table PNG</a> · <a href="table.svg">Vector table SVG</a> · <a href="verification.json">Source verification</a></p></main></html>'
    (OUT/'index.html').write_text(page+'\n')
    render(rows,note)
    print(json.dumps({'output':str(OUT),'primary_conditions':len(rows),'cases_per_condition':48,'all_primary_counts_verified':True,'model_calls':0},indent=2))


def render(rows,note):
    os.environ.setdefault("MPLCONFIGDIR", str(Path(tempfile.gettempdir())/"audit-professor-matplotlib"))
    os.environ.setdefault("XDG_CACHE_HOME", str(Path(tempfile.gettempdir())/"audit-professor-cache"))
    import matplotlib
    matplotlib.use('Agg')
    matplotlib.rcParams['svg.hashsalt'] = 'audit-professor-brief-v1'
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(figsize=(23,8.4));fig.patch.set_facecolor('#0b111b');ax.axis('off')
    fig.text(.026,.95,'FINANCIAL AUDIT  |  VERIFIED DEVELOPMENT RESULTS',color='#edf2f9',fontsize=24,weight='bold')
    fig.text(.026,.901,note,color='#b8c6d8',fontsize=13)
    fig.text(.026,.862,'PROVISIONAL LABEL AGREEMENT  •  FAILURES INCLUDED  •  ACCOUNTANT REVIEW PENDING',color='#f2cb84',fontsize=12,weight='bold')
    vals=[]
    for row in rows:
        vals.append([str(row[k]).replace(' (','\n(') for k,_ in COLS])
    labels=[v.replace(' / ','\n/ ') for _,v in COLS]
    widths=[.112,.115,.060,.071,.071,.071,.071,.065,.069,.080,.073,.073,.069]
    widths=[w/sum(widths) for w in widths]
    t=ax.table(cellText=vals,colLabels=labels,cellLoc='center',colWidths=widths,bbox=[0,.32,1,.50])
    t.auto_set_font_size(False);t.set_fontsize(10)
    for (r,c),cell in t.get_celld().items():
        cell.set_facecolor('#192638' if r==0 else ('#111d2b' if r%2==0 else '#0b111b'))
        cell.set_edgecolor('#344054');cell.set_linewidth(.6);cell.get_text().set_color('#edf2f9')
        if r==0 or c==0:cell.get_text().set_weight('bold')
        if c in (0,1):cell.get_text().set_ha('left');cell.PAD=.08
    foot=[
      'Always-incorrect control: 32/48 = 66.7% General; 0/16 Clean. Qwen8’s General score does not establish a frontier win.',
      'Valid output is a strict schema check. Opus: 18 invalid + 1 empty. Qwen30: 31 direct / 33 evidence-condition API errors.',
      'Tokens: mean per case with complete usage (n shown), summing requested stages. API latency includes errors and excludes pacing/local work.',
      'Full citation matches the provisional paragraph key. Joint judgment/type/row/citation: Opus 11/16; Qwen8 0/16; Qwen30 direct 2/16; evidence 0/16.',
      'Same 48 cases in all primary arms. Citation sample n=16; eight company clusters. The earlier screenshot is not a comparable before/after result.',
      'Source: frozen primary predictions + request traces; every count rederived. See brief.md and verification.json. No new model calls.'
    ]
    for i,line in enumerate(foot):fig.text(.026,.268-i*.037,line,color='#b8c6d8',fontsize=11)
    fig.subplots_adjust(left=.025,right=.975,bottom=.02,top=.95)
    fig.savefig(OUT/'table.png',dpi=150,facecolor=fig.get_facecolor())
    fig.savefig(OUT/'table.svg',facecolor=fig.get_facecolor(),metadata={'Date': None})
    svg = OUT/'table.svg'
    svg.write_text('\n'.join(line.rstrip() for line in svg.read_text().splitlines())+'\n')
    plt.close(fig)


if __name__=='__main__':
    main()
