"""Offline trivial and leave-one-company-out metadata baselines on pilot48.

These baselines measure shortcuts against provisional labels, not accounting.
Only public metadata is used at prediction time; gold error/rule IDs are absent.
"""
import argparse
from collections import Counter, defaultdict
import json
from pathlib import Path
from .integrity import read_jsonl, sha256

ROOT=Path(__file__).resolve().parent
DEFAULT=ROOT/'artifacts/pilot'


def stable_majority(labels):
    counts=Counter(labels)
    return sorted(counts,key=lambda v:(-counts[v],str(v)))[0] if counts else None


def company_fold(records, gold, features):
    """Train paragraph priors on other companies; score only nominally citable cases."""
    hits=0;per_company=[];decisions=[]
    companies=sorted({r['metadata']['cik'] for r in records})
    for company in companies:
        train=[r for r in records if r['metadata']['cik']!=company and gold[r['case_id']]['ground_truth_citations'].get('citable')]
        test=[r for r in records if r['metadata']['cik']==company and gold[r['case_id']]['ground_truth_citations'].get('citable')]
        groups=defaultdict(list)
        global_labels=[]
        for row in train:
            label=gold[row['case_id']]['ground_truth_citations'].get('asc_full')
            groups[tuple(row['metadata'][k] for k in features)].append(label)
            global_labels.append(label)
        fold_hits=0
        for row in test:
            key=tuple(row['metadata'][k] for k in features)
            predicted=stable_majority(groups.get(key,global_labels))
            truth=gold[row['case_id']]['ground_truth_citations'].get('asc_full')
            correct=predicted==truth and truth is not None
            fold_hits+=correct
            decisions.append({'case_id':row['case_id'],'company':company,'predicted_citation':predicted,'provisional_target':truth,'agreement':bool(correct),'fallback':key not in groups})
        hits+=fold_hits
        per_company.append({'company':company,'training_companies':len(companies)-1,'hits':fold_hits,'cases':len(test)})
    n=len(decisions)
    return {'features':list(features),'hits':hits,'denominator':n,'agreement':hits/n if n else None,'per_company':per_company,'decisions':decisions,
            'information_boundary':'Citation-only conditional diagnostic: evaluator restricts scoring to citable items. Model inference uses metadata only, no gold error/type/row/rule. Not joint auditing accuracy.'}


def build(prepared=DEFAULT):
    records=read_jsonl(prepared/'public_inputs.jsonl')
    keys=read_jsonl(prepared/'scoring_only.jsonl')
    gold={r['case_id']:r['gold'] for r in keys}
    if len(gold)!=len(keys) or set(gold)!={r['case_id'] for r in records} or len(records)!=len(gold):
        raise ValueError('Cohort/key identity mismatch or duplicates')
    n=len(records);clean=sum(g['general_judgement']=='Correct' for g in gold.values());injected=n-clean
    return {'schema_version':1,'study_status':'Inspected developmental sample; provisional labels',
        'cases':n,'companies':len({r['metadata']['cik'] for r in records}),
        'source_sha256':{'public_inputs.jsonl':sha256(prepared/'public_inputs.jsonl'),'scoring_only.jsonl':sha256(prepared/'scoring_only.jsonl')},
        'judgement_baselines':{
            'always_incorrect':{'general_hits':injected,'general_denominator':n,'general_agreement':injected/n,'clean_hits':0,'clean_denominator':clean,'detection_hits':injected,'detection_denominator':injected},
            'always_correct':{'general_hits':clean,'general_denominator':n,'general_agreement':clean/n,'clean_hits':clean,'clean_denominator':clean,'detection_hits':0,'detection_denominator':injected}},
        'citation_baselines':{'global_prior':company_fold(records,gold,()),'statement_type':company_fold(records,gold,('statement_type',)),'statement_type_year':company_fold(records,gold,('statement_type','fiscal_year'))},
        'limitations':['Only eight selected companies and sixteen provisional citation targets; fold estimates are unstable.','Synthetic text/format shortcuts are not tested by these metadata baselines.','Citable-only evaluation uses an evaluator restriction, not a deployed citable detector.','No baseline reads the held-out company labels while predicting its citations.','No paid model calls or new empirical accounting labels.']}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--prepared',type=Path,default=DEFAULT);p.add_argument('--output',type=Path,default=ROOT/'results/shortcut_baselines.json');a=p.parse_args()
    if a.output.exists() or a.output.with_suffix('.md').exists():
        p.error('Output already exists; use a fresh JSON and Markdown path')
    result=build(a.prepared);a.output.parent.mkdir(parents=True,exist_ok=True);a.output.write_text(json.dumps(result,indent=2)+'\n')
    lines=['# Offline shortcut baselines','',result['study_status'],'','| Baseline | Exact agreement |','|---|---:|']
    for name,r in result['judgement_baselines'].items():lines.append(f'| Judgment: {name} | {r["general_hits"]}/{r["general_denominator"]} ({100*r["general_agreement"]:.1f}%) |')
    for name,r in result['citation_baselines'].items():lines.append(f'| Citation: other-company {name} | {r["hits"]}/{r["denominator"]} ({100*r["agreement"]:.1f}%) |')
    lines+=['','Always-incorrect clean specificity is 0/16. Citation priors are conditional, evaluator-restricted diagnostics; they do not locate errors or decide whether a citation is needed.','',*['- '+s for s in result['limitations']]]
    a.output.with_suffix('.md').write_text('\n'.join(lines)+'\n');print(json.dumps({'output':str(a.output),'cases':result['cases'],'model_calls':0}))


if __name__=='__main__':main()
