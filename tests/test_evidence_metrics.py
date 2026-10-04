"""Fictional unit examples only: no completed expert review is represented."""
import copy
import unittest
from research.evidence_metrics import evaluate_case, summarize, replay_acquisition


def fixture(case_id='fictional-test'):
    names=['journal','contract','confirmation','register','authority']
    sources=[{'document_id':n,'initially_visible':n=='journal','obtainable':True,'available_at':'2024-12-31'} for n in names]
    facts=[{'fact_id':f,'document_id':d} for f,d in [('booked','journal'),('term','contract'),('confirmed','confirmation'),('registered','register')]]
    edges=lambda last:[{'from_fact_id':'booked','to_fact_id':'term','relation':'same_entry'},{'from_fact_id':'term','to_fact_id':last,'relation':'timing'}]
    proofs=[{'proof_id':'p1','fact_ids':['booked','term','confirmed'],'authority_ids':['A'],'edges':edges('confirmed'),'conclusion':'supported_misstatement'},
            {'proof_id':'p2','fact_ids':['booked','term','registered'],'authority_ids':['A'],'edges':edges('registered'),'conclusion':'supported_misstatement'}]
    authority={'authority_id':'A','source_kind':'canonical_standard','framework':'us_gaap','assertion_family':'revenue_cutoff','jurisdiction':['US'],'entity_scope':['nonfinancial'],'effective_from':'2020-01-01','effective_to':None,'applicability':'supported','scope_decision':'in_scope','required_fact_ids':['term'],'refutation_fact_ids':[]}
    annotation={'case_id':case_id,'status':'expert_reviewed','release_status':'eligible',
        'scope':{'framework':'us_gaap','assertion_family':'revenue_cutoff','jurisdiction':['US'],'entity_type':'nonfinancial','reporting_period_start':'2024-01-01','reporting_period_end':'2024-12-31','investigation_cutoff':'2025-01-31'},
        'sources':sources,'facts':facts,'authorities':[authority],'proof_sets':proofs,
        'gold':{'conclusion':'supported_misstatement','decision_sufficiency':'sufficient','authority_disposition':'governing_paragraph','accepted_proof_ids':['p1','p2'],'acceptable_citation_sets':[['A']]}}
    pred={'status':'ok','conclusion':'supported_misstatement','cited_fact_ids':['booked','term','confirmed'],'cited_authority_ids':['A'],'edges':edges('confirmed')}
    trace=[{'document_id':d,'status':'acquired','charged_cost':1} for d in ['contract','confirmation','authority']]
    kwargs={'budget':3,'document_costs':{n:1 for n in names},'authority_document_ids':{'A':'authority'}}
    return annotation,pred,trace,kwargs


class EvidenceMetricsTests(unittest.TestCase):
    def test_initial_observations_need_not_be_obtainable_again(self):
        a,p,t,k=fixture();a['sources'][0]['obtainable']=False
        r=evaluate_case(a,p,t,**k)
        self.assertTrue(r['supported_decision']);self.assertIn('booked',r['acquisition']['observed_fact_ids'])
        cached=[{'document_id':'journal','status':'cached','charged_cost':0}]
        self.assertTrue(evaluate_case(a,p,cached+t,**k)['supported_decision'])
        a['sources'][0]['initially_visible']=False
        denied=[{'document_id':'journal','status':'unavailable','charged_cost':0}]
        r=evaluate_case(a,p,denied+t,**k)
        self.assertTrue(r['acquisition']['valid']);self.assertFalse(r['supported_decision'])
        self.assertNotIn('booked',r['acquisition']['observed_fact_ids'])

    def test_alternative_sufficient_proof_is_accepted(self):
        a,p,t,k=fixture()
        self.assertTrue(evaluate_case(a,p,t,**k)['supported_decision'])
        p['cited_fact_ids']=['booked','term','registered'];p['edges']=a['proof_sets'][1]['edges'];t[1]['document_id']='register'
        r=evaluate_case(a,p,t,**k)
        self.assertTrue(r['supported_decision']);self.assertEqual(r['completed_proof_ids'],['p2'])

    def test_no_governing_paragraph_requires_citation_abstention(self):
        a,p,t,k=fixture()
        a['gold']['authority_disposition']='no_governing_paragraph'
        a['gold']['acceptable_citation_sets']=[]
        for proof in a['proof_sets']:proof['authority_ids']=[]
        r=evaluate_case(a,p,t,**k)
        self.assertFalse(r['supported_decision']);self.assertFalse(r['citation_abstention_correct'])
        p['cited_authority_ids']=[]
        r=evaluate_case(a,p,t,**k)
        self.assertTrue(r['supported_decision']);self.assertTrue(r['citation_abstention_correct'])
        self.assertFalse(r['citation_set_correct'])

    def test_unacquired_fact_or_authority_cannot_support_decision(self):
        a,p,t,k=fixture()
        r=evaluate_case(a,p,t[:1],**k)
        self.assertFalse(r['supported_decision']);self.assertIn('confirmed',r['unsupported_fact_ids']);self.assertIn('A',r['unsupported_authority_ids'])

    def test_missing_required_evidence_warrants_abstention_but_no_diagnosis_credit(self):
        a,p,t,k=fixture();p.update(conclusion='insufficient_evidence',cited_fact_ids=['booked'],cited_authority_ids=[],edges=[])
        r=evaluate_case(a,p,[],**k)
        self.assertTrue(r['warranted_abstention']);self.assertFalse(r['label_correct']);self.assertFalse(r['supported_decision'])

    def test_unresolved_gold_does_not_become_scored_expert_case(self):
        a,p,t,k=fixture();a['status']='draft';a['release_status']='development_only'
        r=evaluate_case(a,p,t,**k)
        self.assertFalse(r['gold_eligible']);self.assertFalse(r['supported_decision'])
        summary=summarize([r],expected_case_ids=[a['case_id']])
        self.assertEqual(summary['eligible_cases'],0);self.assertIsNone(summary['rates']['label_correct'])

    def test_post_cutoff_evidence_and_wrong_authority_dates_denied(self):
        a,p,t,k=fixture();a['sources'][2]['available_at']='2025-02-01'
        r=evaluate_case(a,p,t,**k)
        self.assertFalse(r['acquisition']['valid']);self.assertFalse(r['supported_decision'])
        a,p,t,k=fixture();a['authorities'][0]['effective_from']='2025-01-01'
        r=evaluate_case(a,p,t,**k)
        self.assertFalse(r['supported_decision']);self.assertIn('authority_not_effective_for_entire_period',r['authority_predicate_failures']['A'])

    def test_pair_that_flips_wrong_answers_gets_zero_both_correct_credit(self):
        a,p,t,k=fixture('left');p['conclusion']='supported_compliance';left=evaluate_case(a,p,t,**k)
        a,p,t,k=fixture('right');a['gold']['conclusion']='supported_compliance'
        for proof in a['proof_sets']:proof['conclusion']='supported_compliance'
        right=evaluate_case(a,p,t,**k)
        r=summarize([left,right],expected_case_ids=['left','right'],pairs=[{'pair_id':'pair','case_ids':['left','right']}])
        self.assertTrue(r['pairs'][0]['label_changed']);self.assertEqual(r['pair_both_correct'],0)

    def test_failed_or_missing_predictions_remain_in_denominator(self):
        scores=[]
        for name,pred in [('ok','original'),('missing',None),('failure',{'status':'failure'})]:
            a,p,t,k=fixture(name);scores.append(evaluate_case(a,p if pred=='original' else pred,t,**k))
        r=summarize(scores,expected_case_ids=['ok','missing','failure'])
        self.assertEqual(r['eligible_cases'],3);self.assertAlmostEqual(r['rates']['supported_decision'],1/3)
        with self.assertRaises(ValueError):summarize(scores[:1],expected_case_ids=['ok','missing'])

    def test_budget_trace_tampering_and_nonnumeric_units_are_denied(self):
        a,p,t,k=fixture()
        for budget in [True,-1,float('nan'),1.5,'3']:
            with self.subTest(budget=budget),self.assertRaises(ValueError):evaluate_case(a,p,t,**{**k,'budget':budget})
        changed=copy.deepcopy(t);changed[0]['charged_cost']=0
        self.assertFalse(evaluate_case(a,p,changed,**k)['acquisition']['valid'])
        self.assertFalse(evaluate_case(a,p,t,**{**k,'budget':2})['supported_decision'])
        cached=t+[{'document_id':'contract','status':'cached','charged_cost':0}]
        self.assertEqual(evaluate_case(a,p,cached,**k)['acquisition']['spent'],3)

    def test_unsupported_extra_assertion_and_fabricated_edge_denied(self):
        a,p,t,k=fixture();p['assertions']=[{'claim_id':'invented','support_fact_ids':['booked']}]
        self.assertFalse(evaluate_case(a,p,t,**k)['supported_decision'])
        a,p,t,k=fixture();p['edges'].append({'from_fact_id':'confirmed','to_fact_id':'booked','relation':'fabricated'})
        self.assertFalse(evaluate_case(a,p,t,**k)['supported_decision'])
