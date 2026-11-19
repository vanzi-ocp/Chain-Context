"""0.2.1 보강: 작성자·검토자 분리, F-05 불일치 기록, 시점 차이, 등급표, F-06 고정 스냅샷."""
import sqlite3
import tempfile
import unittest
from datetime import timedelta
from hashlib import sha256
from pathlib import Path

from pydantic import ValidationError

from chain_prism.core import DomainError, Store
from chain_prism.demo import AS_OF, DEMO_AUTHOR, seed
from chain_prism.models import Assertion, Discrepancy, Input, Judgment, Principal, ReviewRequest

AUTHOR = DEMO_AUTHOR
COMMON = {'case_id': 'DEMO', 'scope_id': 'SCOPE-1'}


class V021Tests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.addCleanup(self.store.close)
        seed(self.store)
        self.reviewer = Principal(id='reviewer', role='approver', case_ids=('DEMO',))

    def copy(self, record_id, **changes):
        original = self.store.get(record_id)
        return type(original).model_validate({**original.model_dump(), **changes})

    def request(self, jid='J-1', version=1, **changes):
        g = self.store.guardrail(jid)
        base = {'expected_version': version, 'expected_dependency_digest': g['dependency_digest'],
                'decision': 'approve_scoped', 'evidence_grade': 'E1',
                'judgment_status': 'confirmed_scoped', 'reason': '설명용 산술 범위 검토'}
        return ReviewRequest(**{**base, **changes})

    def discrepancy(self, **changes):
        base = dict(id='D-1', **COMMON, diff_type='doc_impl', subject_ids=('A-2',),
                    description='운영자금 제외가 약관에 명시되어 있는지 미확인',
                    impact='준비자산 30 범위', status='open', next_action='약관 판본 요청',
                    resolution_condition='약관에서 제외 조항 확인')
        return Discrepancy(**{**base, **changes})

    # ---- 작성자·검토자 분리
    def test_judgment_without_author_rejected(self):
        with self.assertRaises(DomainError):
            self.store.add(self.copy('J-1', id='J-NOAUTH'))

    def test_author_cannot_review_own_judgment(self):
        me = Principal(id=AUTHOR, role='approver', case_ids=('DEMO',))
        with self.assertRaises(PermissionError):
            self.store.review('J-1', self.request(), me)
        with self.assertRaises(PermissionError):
            self.store.review('J-1', self.request(decision='request_changes', evidence_grade=None,
                                                  judgment_status=None), me)

    def test_author_recorded_in_guardrail_and_summary(self):
        self.assertEqual(self.store.guardrail('J-1')['author'], AUTHOR)
        self.assertEqual(self.store.summary('DEMO', 'SCOPE-1', ['J-1'])['judgments'][0]['author'], AUTHOR)

    def test_disagreement_with_author_needs_resolution(self):
        req = self.request(decision='approve_conditional', evidence_grade='E2', judgment_status='conditional')
        with self.assertRaises(DomainError):
            self.store.review('J-1', req, self.reviewer)
        req = self.request(decision='approve_conditional', evidence_grade='E2', judgment_status='conditional',
                           disagreement_resolution='약관 판본 미확인으로 E2·조건부로 낮춤')
        self.assertEqual(self.store.review('J-1', req, self.reviewer).request.evidence_grade, 'E2')

    def test_inconsistent_proposal_rejected(self):
        with self.assertRaises(ValidationError):
            self.copy('J-1', id='J-BAD', proposed_grade='E4', proposed_status='confirmed_scoped')

    def test_grade_table_matches_appendix_c(self):
        for grade, status, decision in [('E3', 'confirmed_scoped', 'approve_scoped'),
                                        ('E4', 'conditional', 'approve_conditional')]:
            with self.assertRaises(DomainError):
                self.store.review('J-1', self.request(evidence_grade=grade, judgment_status=status, decision=decision,
                                                      disagreement_resolution='x'), self.reviewer)

    def test_legacy_db_without_author_column_opens_and_blocks_review(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 'old.sqlite')
            store = Store(path)
            seed(store)
            store.close()
            db = sqlite3.connect(path)
            db.execute('UPDATE records SET created_by=NULL')
            db.commit()
            db.close()
            reopened = Store(path)
            try:
                with self.assertRaises(DomainError):
                    reopened.review('J-1', ReviewRequest(
                        expected_version=1, expected_dependency_digest=reopened.guardrail('J-1')['dependency_digest'],
                        decision='approve_scoped', evidence_grade='E1', judgment_status='confirmed_scoped',
                        reason='x'), self.reviewer)
            finally:
                reopened.close()

    # ---- F-05 불일치 기록
    def test_open_discrepancy_blocks_confirmation_only(self):
        self.store.add(self.discrepancy())
        self.store.add(self.copy('J-1', id='J-D', discrepancy_ids=('D-1',)), actor=AUTHOR)
        g = self.store.guardrail('J-D')
        self.assertEqual(g['blocked_statuses'], ['confirmed_scoped'])
        self.assertIn('OPEN_DISCREPANCY', [i['code'] for i in g['issues']])

    def test_hidden_discrepancy_rejected_at_registration(self):
        self.store.add(self.discrepancy())
        with self.assertRaises(DomainError):
            self.store.add(self.copy('J-1', id='J-HIDE'), actor=AUTHOR)

    def test_discrepancy_found_after_judgment_forces_re_review(self):
        self.store.review('J-1', self.request(), self.reviewer)
        self.store.add(self.discrepancy())
        g = self.store.guardrail('J-1')
        self.assertTrue(g['re_review_required'])
        self.assertIn('UNDECLARED_DISCREPANCY', [i['code'] for i in g['issues']])
        self.assertEqual(set(g['blocked_statuses']), {'confirmed_scoped', 'conditional', 'multiple_interp'})
        self.assertIsNone(self.store.summary('DEMO', 'SCOPE-1', ['J-1'])['judgments'][0]['effective_status'])

    def test_discrepancy_status_change_invalidates_review(self):
        self.store.add(self.discrepancy())
        self.store.add(self.copy('J-1', id='J-D', discrepancy_ids=('D-1',), proposed_grade='E2',
                                 proposed_status='conditional'), actor=AUTHOR)
        self.store.review('J-D', self.request('J-D', decision='approve_conditional', evidence_grade='E2',
                                              judgment_status='conditional'), self.reviewer)
        self.store.add(self.discrepancy(id='D-1-V2', version=2, supersedes_id='D-1', status='explained',
                                        explanation_ids=('A-4',), resolution_condition=None))
        self.assertTrue(self.store.guardrail('J-D')['re_review_required'])

    def test_discrepancy_rules(self):
        with self.assertRaises(ValidationError):
            self.discrepancy(status='open', resolution_condition=None)
        with self.assertRaises(ValidationError):
            self.discrepancy(status='resolved', explanation_ids=())
        with self.assertRaises(ValidationError):
            self.discrepancy(diff_type='unresolved', status='resolved', explanation_ids=('A-4',))
        with self.assertRaises(DomainError):
            self.store.add(self.discrepancy(subject_ids=('J-1',)))

    # ---- 시점 차이
    def deviating_input(self, reason='9월 보고서를 11월 기준 범위에 나란히 둠'):
        later = AS_OF - timedelta(days=30)
        return Input(id='IN-SEP', **COMMON, source_ref='demo://report/sep', data_nature='illustrative',
                     content_hash=sha256(b'sep').hexdigest(), as_of=later, as_of_deviation_reason=reason)

    def test_timing_deviation_needs_reason(self):
        with self.assertRaises(DomainError):
            self.store.add(self.deviating_input(reason=None))

    def test_timing_deviation_blocks_until_explained(self):
        self.store.add(self.deviating_input())
        self.store.add(Assertion(id='A-SEP', **COMMON, input_id='IN-SEP', data_nature='illustrative', nature='F',
                                 record_role='observation_or_inference', statement='9월 보고서의 준비자산 1,210',
                                 claim_key='coverage-sep', numeric_value='1210', unit='USD',
                                 observation_scope='보고서 기재값'))
        self.store.add(self.copy('J-1', id='J-T', required_assertion_ids=('A-1', 'A-2', 'A-3', 'A-4', 'A-SEP')),
                       actor=AUTHOR)
        self.assertIn('TIMING_DEVIATION', [i['code'] for i in self.store.guardrail('J-T')['issues']])
        self.store.add(self.discrepancy(id='D-T', diff_type='fact_timing', subject_ids=('A-SEP',),
                                        description='9월 보고 시점과 범위 기준시점이 다름',
                                        status='explained', explanation_ids=('A-1',), resolution_condition=None))
        self.store.add(self.copy('J-1', id='J-T2', required_assertion_ids=('A-1', 'A-2', 'A-3', 'A-4', 'A-SEP'),
                                 discrepancy_ids=('D-T',)), actor=AUTHOR)
        g = self.store.guardrail('J-T2')
        self.assertNotIn('TIMING_DEVIATION', [i['code'] for i in g['issues']])
        self.assertNotIn('confirmed_scoped', g['blocked_statuses'])

    def test_deviating_input_cannot_enter_reconciliation(self):
        self.store.add(self.deviating_input())
        self.store.add(Assertion(id='A-SEP', **COMMON, input_id='IN-SEP', data_nature='illustrative', nature='F',
                                 record_role='observation_or_inference', statement='9월 준비자산 1,230',
                                 claim_key='c', numeric_value='1230', unit='USD', observation_scope='기재값'))
        rec = self.store.get('REC-1')
        c0 = rec.components[0].model_copy(update={'assertion_id': 'A-SEP'})
        bad = type(rec).model_validate({**rec.model_dump(), 'id': 'REC-T', 'components': (c0, *rec.components[1:])})
        with self.assertRaises(DomainError):
            self.store.add(bad)

    # ---- F-06 고정 스냅샷
    def test_conclusion_snapshot_frozen_and_verified(self):
        self.store.review('J-1', self.request(), self.reviewer)
        snap = self.store.freeze_conclusion('DEMO', 'SCOPE-1', ['J-1'], self.reviewer, '설명용 제출본')
        self.assertTrue(snap.complete)
        self.store.add(self.copy('A-1', id='A-1-V2', version=2, supersedes_id='A-1'))
        again = self.store.get_conclusion(snap.id)
        self.assertEqual(again.digest, snap.digest)
        self.assertEqual(again.body['judgments'][0]['effective_status'], 'confirmed_scoped')
        self.assertIsNone(self.store.summary('DEMO', 'SCOPE-1', ['J-1'])['judgments'][0]['effective_status'])

    def test_incomplete_snapshot_flagged_and_analyst_cannot_freeze(self):
        snap = self.store.freeze_conclusion('DEMO', 'SCOPE-1', ['J-1'], self.reviewer, '검토 전 초안')
        self.assertFalse(snap.complete)
        with self.assertRaises(PermissionError):
            self.store.freeze_conclusion('DEMO', 'SCOPE-1', ['J-1'],
                                         Principal(id='a', role='analyst', case_ids=('DEMO',)), 'x')

    def test_tampered_snapshot_detected(self):
        with tempfile.TemporaryDirectory() as directory:
            path = str(Path(directory) / 't.sqlite')
            store = Store(path)
            seed(store)
            snap = store.freeze_conclusion('DEMO', 'SCOPE-1', ['J-1'], self.reviewer, '제출본')
            body = store._db.execute('SELECT body FROM conclusions').fetchone()[0]
            self.assertIn('설명용 범위 안에서', body)
            store._db.execute('UPDATE conclusions SET body=?',
                              (body.replace('설명용 범위 안에서', '변조된 범위 안에서'),))
            store._db.commit()
            try:
                with self.assertRaises(DomainError):
                    store.get_conclusion(snap.id)
            finally:
                store.close()

    # ---- 회귀: DAO 지원금 사례 ― 지급자 미확인 행에 기대어 E3로 '채택(범위 한정)'을 낸 결론
    def test_pilot_dao_grant_e3_scoped_adoption_rejected(self):
        from chain_prism.models import SRow
        self.store.add(SRow(id='S-PAYER', **COMMON, definition='지급자: 4-of-7 다중서명 통제 집단(법인격 미확인)',
                            element_type='subject', identification_status='unidentified',
                            offchain_assertion_ids=('A-3',), conditional_handover=True,
                            handover_reason='지급자 실체·거주지 미확인', release_condition='재단 등기·서명자 명부'))
        self.store.add(self.copy('J-1', id='J-DAO', required_s_row_ids=('S-1', 'S-PAYER'),
                                 proposed_grade='E3', proposed_status='conditional'), actor=AUTHOR)
        g = self.store.guardrail('J-DAO')
        self.assertIn('confirmed_scoped', g['blocked_statuses'])
        with self.assertRaises(DomainError):
            self.store.review('J-DAO', self.request('J-DAO', evidence_grade='E3', judgment_status='confirmed_scoped',
                                                    disagreement_resolution='x'), self.reviewer)
        with self.assertRaises(ValidationError):
            self.copy('J-1', id='J-DAO-BAD', proposed_grade='E3', proposed_status='confirmed_scoped')


if __name__ == '__main__':
    unittest.main()
