"""Adversarial split/payload checks and company-held-out shortcut boundaries."""
import copy
import json
from pathlib import Path
import tempfile
import unittest
from research.integrity import PILOT, audit, read_jsonl, validate_public_cases, validate_payload, validate_group_splits
from research.shortcut_baselines import company_fold


def payload(cid='a'*20,company='0000000001',statement='IncomeStatement'):
    return {'case_id':'case_'+cid,'metadata':{'cik':company,'company':'Company '+company,'period':'2024-12-31','fiscal_year':2024,'statement_type':statement,'unit':'USD millions'},'statement_text':'[row 0]: Revenue | $100','transaction_data':'Evidence incomplete.'}


def grouped(cid='a',company='0001',split='development',filing='f1',event='e1',variant='v1'):
    return {'case_id':cid,'company_id':company,'split':split,'filing_ids':[filing],'event_ids':[event],'variant_group_ids':[variant]}


class IntegrityTests(unittest.TestCase):
    def test_hidden_fields_and_labels_rejected(self):
        self.assertEqual(validate_payload(payload()),[])
        for field in ['gold','rule_id','error_type','corrected_statement_text']:
            row=payload();row[field]='secret'
            self.assertTrue(validate_payload(row))
        row=payload();row['metadata']['citation_tier']='linkbase'
        self.assertTrue(validate_payload(row))
        row=payload();row['transaction_data']='ground_truth_citations = ASC 606-10-25-23'
        self.assertTrue(validate_payload(row))
        row=payload();row['case_id']='IA-COMPANY-R09-fault'
        self.assertTrue(validate_payload(row))

    def test_missing_metadata_and_duplicate_ids_fail_closed(self):
        row=payload();row['metadata'].pop('unit')
        self.assertTrue(validate_payload(row))
        self.assertFalse(validate_public_cases([payload(),payload()])['passed'])
        self.assertFalse(validate_public_cases([])['passed'])
        row=payload();row['metadata']['fiscal_year']=True
        self.assertTrue(validate_payload(row))

    def test_company_alias_padding_cannot_cross_splits(self):
        rows=[grouped(),grouped('b','1','test','f2','e2','v2')]
        r=validate_group_splits(rows)
        self.assertFalse(r['passed']);self.assertEqual(r['overlapping_identities'][0]['identity_type'],'company_id')

    def test_filing_event_variant_overlap_and_transitive_components(self):
        for field in ['filing_ids','event_ids','variant_group_ids']:
            rows=[grouped(),grouped('b','2','test','f2','e2','v2')]
            rows[1][field]=rows[0][field]
            self.assertFalse(validate_group_splits(rows)['passed'])
        rows=[grouped(),grouped('b','2','development','f1','e2','v2'),grouped('c','3','test','f3','e2','v3')]
        r=validate_group_splits(rows)
        self.assertFalse(r['passed']);self.assertEqual(len(r['mixed_components'][0]['case_ids']),3)

    def test_complete_disjoint_manifest_passes_only_supplied_identity_check(self):
        rows=[grouped(),grouped('b','2','test','f2','e2','v2')]
        self.assertTrue(validate_group_splits(rows,['a','b'])['passed'])
        self.assertFalse(validate_group_splits(rows,['a','c'])['passed'])
        rows[1]['event_ids']=[]
        self.assertFalse(validate_group_splits(rows)['passed'])
        self.assertFalse(validate_group_splits([grouped()])['passed'])

    def test_company_held_out_prior_ignores_its_own_target(self):
        records=[payload('a'*20,'0000000001'),payload('b'*20,'0000000002')]
        def gold(code):return {'ground_truth_citations':{'citable':True,'asc_full':code}}
        keys={records[0]['case_id']:gold('ASC 606-10-25-23'),records[1]['case_id']:gold('ASC 330-10-35-1B')}
        original=company_fold(records,keys,('statement_type',))
        changed=copy.deepcopy(keys);changed[records[0]['case_id']]=gold('ASC 740-10-30-5')
        rerun=company_fold(records,changed,('statement_type',))
        old=next(d for d in original['decisions'] if d['case_id']==records[0]['case_id'])
        new=next(d for d in rerun['decisions'] if d['case_id']==records[0]['case_id'])
        self.assertEqual(old['predicted_citation'],new['predicted_citation'])
        self.assertEqual(old['predicted_citation'],'ASC 330-10-35-1B')

    def test_invented_company_groups_cannot_override_public_ciks(self):
        public=read_jsonl(PILOT/'public_inputs.jsonl')
        groups=[grouped(r['case_id'],str(i+9000000),'test' if i%2 else 'development',f'f{i}',f'e{i}',f'v{i}')
                for i,r in enumerate(public)]
        self.assertTrue(validate_group_splits(groups,[r['case_id'] for r in public])['passed'])
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'groups.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in groups))
            result=audit(groups_path=path)
        self.assertFalse(result['integrity_release_gate_passed'])
        self.assertTrue(any('public CIK' in e['error'] for e in result['partition_validation']['errors']))

    def test_known_inspected_cases_cannot_be_relabelled_as_fresh_test(self):
        public=read_jsonl(PILOT/'public_inputs.jsonl')
        companies=sorted({r['metadata']['cik'] for r in public})
        groups=[grouped(r['case_id'],r['metadata']['cik'],'test' if r['metadata']['cik'] in companies[:4] else 'development',f'f{i}',f'e{i}',f'v{i}')
                for i,r in enumerate(public)]
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'groups.jsonl';path.write_text(''.join(json.dumps(r)+'\n' for r in groups))
            result=audit(groups_path=path)
        self.assertTrue(result['partition_validation']['passed'])
        self.assertTrue(result['development_history']['known_inspected_cohort'])
        self.assertFalse(result['integrity_release_gate_passed'])
