import tempfile
import unittest
from datetime import timedelta
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from chain_prism.core import DomainError, Store, calculate_reconciliation
from chain_prism.demo import AS_OF, seed
from chain_prism.models import (Assertion, Component, Input, Judgment, Principal, Reconciliation,
                               ReviewRequest, Scope, SRow, TRow)


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.addCleanup(self.store.close)
        self.rec = seed(self.store)
        self.principal = Principal(id='reviewer', role='approver', case_ids=('DEMO',))

    def copy(self, record_id, **changes):
        original = self.store.get(record_id)
        return type(original).model_validate({**original.model_dump(), **changes})

    def request(self, **changes):
        g = self.store.guardrail('J-1')
        return ReviewRequest(**dict({'expected_version': 1, 'expected_dependency_digest': g['dependency_digest'],
                                     'decision': 'approve_scoped', 'evidence_grade': 'E1',
                                     'judgment_status': 'confirmed_scoped', 'reason': '명시된 설명용 산술 범위 검토'}, **changes))

    def test_reconciliation_adjusts_both_sides(self):
        result = self.store.run_result('REC-1')
        self.assertEqual(result['raw_ratio_pct'], '106.03')
        self.assertEqual(result['adjusted_reserve'], '1200')
        self.assertEqual(result['adjusted_obligation'], '1200')
        self.assertEqual(result['adjusted_ratio_pct'], '100.00')
        self.assertFalse(result['auto_approved_conclusion'])

    def test_display_cap_does_not_hide_gap(self):
        components = tuple(c for c in self.rec.components if c.treatment == 'base')
        rec = Reconciliation(**{**self.rec.model_dump(), 'id': 'REC-RAW', 'components': components, 'display_cap': '1'})
        result = calculate_reconciliation(rec)
        self.assertEqual(result['adjusted_ratio_pct'], '106.03')
        self.assertEqual(result['capped_display_ratio_pct'], '100.00')
        self.assertEqual(result['difference_amount'], '70')
        self.assertFalse(result['within_tolerance'])

    def test_missing_srow_rejected(self):
        with self.assertRaises(DomainError):
            self.store.add(self.copy('J-1', id='J-MISSING', required_s_row_ids=('ABSENT',)), actor='analyst-1')

    def test_missing_parent_rejected(self):
        with self.assertRaises(DomainError):
            self.store.add(self.copy('IN-1', id='IN-BAD', parent_input_ids=('ABSENT',)))

    def test_self_cycle_rejected(self):
        with self.assertRaises(DomainError):
            self.store.add(self.copy('IN-1', id='IN-SELF', parent_input_ids=('IN-SELF',)))

    def test_assertion_replacement_alone_invalidates_review(self):
        self.store.review('J-1', self.request(), self.principal)
        self.store.add(self.copy('A-1', id='A-1-V2', version=2, supersedes_id='A-1', numeric_value='1229'))
        g = self.store.guardrail('J-1')
        self.assertTrue(g['re_review_required'])
        summary = self.store.summary('DEMO', 'SCOPE-1', ['J-1'])['judgments'][0]
        self.assertIsNotNone(summary['latest_review'])
        self.assertFalse(summary['review_applies_to_current_dependencies'])
        self.assertIsNone(summary['effective_status'])

    def test_input_change_propagates_through_assertion(self):
        self.store.add(self.copy('IN-1', id='IN-1-V2', version=2, supersedes_id='IN-1', content_hash='b' * 64))
        self.assertTrue(self.store.guardrail('J-1')['re_review_required'])

    def test_srow_change_alone_propagates(self):
        self.store.add(self.copy('S-1', id='S-1-V2', version=2, supersedes_id='S-1', definition='개정 범위'))
        self.assertTrue(self.store.guardrail('J-1')['re_review_required'])
        self.assertNotEqual(self.store.get('S-1').definition, '개정 범위')

    def test_transitive_input_lineage_propagates(self):
        self.store.add(self.copy('IN-1', id='DERIVED', parent_input_ids=('IN-1',), content_hash='c' * 64))
        self.store.add(self.copy('A-1', id='A-DERIVED', input_id='DERIVED'))
        self.store.add(self.copy('J-1', id='J-DERIVED', required_assertion_ids=('A-DERIVED',)), actor='analyst-1')
        self.store.add(self.copy('IN-1', id='IN-1-V2', supersedes_id='IN-1', version=2))
        self.assertTrue(self.store.guardrail('J-DERIVED')['re_review_required'])

    def test_fresh_judgment_can_be_reviewed_after_replacement(self):
        self.store.add(self.copy('A-1', id='A-1-V2', version=2, supersedes_id='A-1'))
        self.store.add(self.copy('J-1', id='J-2', version=2, supersedes_id='J-1', required_assertion_ids=('A-1-V2', 'A-2', 'A-3', 'A-4')), actor='analyst-1')
        g = self.store.guardrail('J-2')
        req = self.request(expected_version=2, expected_dependency_digest=g['dependency_digest'])
        self.store.review('J-2', req, self.principal)
        self.assertEqual(self.store.summary('DEMO', 'SCOPE-1', ['J-2'])['judgments'][0]['effective_status'], 'confirmed_scoped')

    def test_duplicate_srow_rejected(self):
        with self.assertRaises(DomainError):
            self.store.add(self.store.get('S-1'))

    def test_duplicate_supersession_and_version_jump_rejected(self):
        with self.assertRaises(DomainError):
            self.store.add(self.copy('A-1', id='A-JUMP', version=3, supersedes_id='A-1'))
        self.store.add(self.copy('A-1', id='A-V2', version=2, supersedes_id='A-1'))
        with self.assertRaises(DomainError):
            self.store.add(self.copy('A-1', id='A-FORK', version=2, supersedes_id='A-1'))

    def test_mismatched_decision_status_rejected(self):
        with self.assertRaises(DomainError):
            self.store.review('J-1', self.request(decision='approve_conditional'), self.principal)

    def test_stale_snapshot_rejected(self):
        req = self.request()
        self.store.add(self.copy('IN-1', id='IN-1-V2', version=2, supersedes_id='IN-1'))
        with self.assertRaises(DomainError):
            self.store.review('J-1', req, self.principal)

    def test_old_dependency_cannot_receive_conditional_approval(self):
        self.store.add(self.copy('A-1', id='A-1-V2', version=2, supersedes_id='A-1'))
        with self.assertRaises(DomainError):
            self.store.review('J-1', self.request(decision='approve_conditional', judgment_status='conditional'), self.principal)

    def test_analyst_cannot_approve(self):
        with self.assertRaises(PermissionError):
            self.store.review('J-1', self.request(), Principal(id='a', role='analyst', case_ids=('DEMO',)))

    def test_review_other_case_rejected(self):
        with self.assertRaises(PermissionError):
            self.store.review('J-1', self.request(), Principal(id='a', role='approver', case_ids=('OTHER',)))

    def test_e4_cannot_confirm(self):
        with self.assertRaises(DomainError):
            self.store.review('J-1', self.request(evidence_grade='E4'), self.principal)

    def test_multiple_interpretations_need_two_alternatives(self):
        with self.assertRaises(DomainError):
            self.store.review('J-1', self.request(decision='accept_multiple_interp', judgment_status='multiple_interp',
                                                 interpretation_alternatives=('해석 A',)), self.principal)

    def test_na_reason_does_not_replace_evidence(self):
        with self.assertRaises(ValidationError):
            SRow(id='S-NA', case_id='DEMO', scope_id='SCOPE-1', definition='상환권', element_type='right',
                 identification_status='confirmed', onchain_not_applicable=True, onchain_na_reason='오프체인 권리')

    def test_actual_illustrative_mixing_rejected(self):
        with self.assertRaises(DomainError):
            self.store.add(self.copy('IN-1', id='IN-ACTUAL', data_nature='actual'))

    def test_scope_and_case_mixing_rejected(self):
        self.store.add(Scope(id='SCOPE-OTHER', case_id='OTHER', as_of=AS_OF, data_nature='illustrative', termination_criteria='test'))
        with self.assertRaises(DomainError):
            self.store.add(self.copy('A-1', id='A-OTHER', scope_id='SCOPE-OTHER', case_id='OTHER'))
        with self.assertRaises(DomainError):
            self.store.summary('OTHER', 'SCOPE-OTHER', ['J-1'])

    def test_same_case_different_scope_rejected(self):
        self.store.add(Scope(id='SCOPE-2', case_id='DEMO', as_of=AS_OF, data_nature='illustrative', termination_criteria='test'))
        with self.assertRaises(DomainError):
            self.store.add(self.copy('A-1', id='A-CROSS', scope_id='SCOPE-2'))

    def test_lineage_overlap_preserves_both_records(self):
        self.store.add(self.copy('IN-1', id='DERIVED', parent_input_ids=('IN-1', 'IN-2'), content_hash='c' * 64))
        self.store.add(self.copy('A-1', id='A-DERIVED', input_id='DERIVED', nature='I'))
        result = self.store.evidence_independence(['A-1', 'A-DERIVED'])
        self.assertEqual(len(result['assertion_ids']), 2)
        self.assertEqual(len(result['overlaps']), 1)
        self.assertIsNone(result['independent_evidence_count'])

    def test_two_different_claims_from_one_input_not_deleted(self):
        self.store.add(self.copy('A-1', id='A-OTHER-CLAIM', claim_key='other'))
        self.assertEqual(len(self.store.evidence_independence(['A-1', 'A-OTHER-CLAIM'])['assertion_ids']), 2)

    def test_float_money_and_nan_rejected(self):
        c = self.rec.components[0]
        for value in (1.2, 'NaN', 'Infinity', '-1'):
            with self.assertRaises(ValidationError):
                Component.model_validate({**c.model_dump(), 'amount': value})

    def test_component_unit_time_and_source_amount_rejected(self):
        for changes in ({'unit': 'BTC'}, {'as_of': AS_OF + timedelta(days=1)}, {'amount': '1231'}):
            c = Component.model_validate({**self.rec.components[0].model_dump(), **changes})
            rec = Reconciliation.model_validate({**self.rec.model_dump(), 'id': 'REC-BAD', 'components': (c, *self.rec.components[1:])})
            with self.assertRaises(DomainError):
                self.store.add(rec)

    def test_duplicate_component_rejected(self):
        rec = Reconciliation.model_validate({**self.rec.model_dump(), 'id': 'REC-DUP', 'components': (*self.rec.components, self.rec.components[0])})
        with self.assertRaises(DomainError):
            self.store.add(rec)

    def test_h_cannot_be_hidden_in_structure(self):
        self.store.add(self.copy('A-1', id='H-1', nature='H', record_role='assumption', purpose='fact_completion'))
        self.store.add(self.copy('S-1', id='S-H', offchain_assertion_ids=('H-1',)))
        with self.assertRaises(DomainError):
            self.store.add(self.copy('J-1', id='J-HIDDEN', required_s_row_ids=('S-H',)), actor='analyst-1')
        self.store.add(self.copy('J-1', id='J-H', required_s_row_ids=('S-H',), relied_h_ids=('H-1',)), actor='analyst-1')
        self.assertIn('confirmed_scoped', self.store.guardrail('J-H')['blocked_statuses'])

    def test_substantive_assurance_not_automatically_confirmed(self):
        self.store.add(self.copy('J-1', id='J-SUB', requires_substantive_assurance=('asset_existence',)), actor='analyst-1')
        self.assertIn('confirmed_scoped', self.store.guardrail('J-SUB')['blocked_statuses'])

    def test_persistence_of_records_reviews_and_run_snapshot(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'test.sqlite')
            store = Store(path)
            seed(store)
            g = store.guardrail('J-1')
            req = ReviewRequest(expected_version=1, expected_dependency_digest=g['dependency_digest'],
                                decision='hold_reserved', evidence_grade='E4', judgment_status='reserved', reason='추가 확인',
                                disagreement_resolution='작성자 E1 제안과 달리 외부 확인 전까지 유보하기로 합의')
            store.review('J-1', req, self.principal)
            store.close()
            reopened = Store(path)
            try:
                self.assertEqual(reopened.run_result('REC-1')['adjusted_ratio_pct'], '100.00')
                self.assertEqual(reopened.summary('DEMO', 'SCOPE-1', ['J-1'])['judgments'][0]['effective_status'], 'reserved')
            finally:
                reopened.close()


if __name__ == '__main__':
    unittest.main()
