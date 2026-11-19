import unittest

from fastapi.testclient import TestClient

from chain_prism.api import create_app
from chain_prism.core import Store
from chain_prism.demo import seed
from chain_prism.models import Principal


class ApiTests(unittest.TestCase):
    def setUp(self):
        self.store = Store()
        self.addCleanup(self.store.close)
        seed(self.store)
        self.client = TestClient(create_app(self.store, {
            'test-analyst': Principal(id='analyst-1', role='analyst', case_ids=('DEMO',)),
            'test-reviewer': Principal(id='reviewer-1', role='approver', case_ids=('DEMO',)),
            'test-other': Principal(id='other-1', role='approver', case_ids=('OTHER',)),
        }))
        self.headers = {'Authorization': 'Bearer test-reviewer'}

    def request(self):
        g = self.client.post('/judgments/J-1/guardrail-checks', headers=self.headers).json()
        return {'expected_version': 1, 'expected_dependency_digest': g['dependency_digest'],
                'decision': 'approve_scoped', 'evidence_grade': 'E1',
                'judgment_status': 'confirmed_scoped', 'reason': '산술 범위 검토'}

    def test_no_auth_rejected(self):
        self.assertEqual(self.client.post('/judgments/J-1/guardrail-checks').status_code, 401)

    def test_client_cannot_supply_reviewer_identity(self):
        payload = {**self.request(), 'reviewer_role': 'approver', 'reviewer_id': 'forged'}
        self.assertEqual(self.client.post('/judgments/J-1/reviews', json=payload, headers=self.headers).status_code, 422)

    def test_analyst_cannot_approve_via_api(self):
        result = self.client.post('/judgments/J-1/reviews', json=self.request(),
                                  headers={'Authorization': 'Bearer test-analyst'})
        self.assertEqual(result.status_code, 403)

    def test_successful_review_uses_server_identity(self):
        result = self.client.post('/judgments/J-1/reviews', json=self.request(), headers=self.headers)
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(result.json()['principal']['id'], 'reviewer-1')

    def test_cross_case_access_denied(self):
        result = self.client.post('/judgments/J-1/guardrail-checks', headers={'Authorization': 'Bearer test-other'})
        self.assertEqual(result.status_code, 403)

    def test_get_saved_run(self):
        result = self.client.get('/reconciliation-runs/REC-1', headers=self.headers)
        self.assertEqual(result.status_code, 200)
        self.assertEqual(result.json()['adjusted_ratio_pct'], '100.00')

    def test_typed_registration_and_path_case_check(self):
        record = self.store.get('IN-1').model_dump(mode='json')
        record['id'] = 'IN-NEW'
        result = self.client.post('/cases/DEMO/inputs', json=record, headers=self.headers)
        self.assertEqual(result.status_code, 201, result.text)
        record['id'], record['case_id'] = 'IN-MISMATCH', 'OTHER'
        self.assertEqual(self.client.post('/cases/DEMO/inputs', json=record, headers=self.headers).status_code, 409)

    def test_summary_scope_validation(self):
        result = self.client.post('/cases/DEMO/summary-runs', json={'scope_id': 'SCOPE-1', 'judgment_ids': ['J-1']}, headers=self.headers)
        self.assertEqual(result.status_code, 200, result.text)
        self.assertIsNone(result.json()['judgments'][0]['effective_status'])

    def test_stale_review_token_rejected(self):
        request = self.request()
        original = self.store.get('A-1')
        self.store.add(type(original).model_validate({**original.model_dump(), 'id': 'A-1-V2', 'version': 2, 'supersedes_id': 'A-1'}))
        self.assertEqual(self.client.post('/judgments/J-1/reviews', json=request, headers=self.headers).status_code, 409)

    def test_openapi_generated(self):
        result = self.client.get('/openapi.json')
        self.assertEqual(result.status_code, 200)
        self.assertIn('/cases/{case_id}/inputs', result.json()['paths'])

    def test_judgment_author_comes_from_token(self):
        record = self.store.get('J-1').model_dump(mode='json')
        record['id'] = 'J-API'
        analyst = {'Authorization': 'Bearer test-analyst'}
        result = self.client.post('/cases/DEMO/judgments', json=record, headers=analyst)
        self.assertEqual(result.status_code, 201, result.text)
        self.assertEqual(self.store.author('J-API'), 'analyst-1')
        record['id'], record['created_by'] = 'J-FORGED', 'someone-else'
        self.assertEqual(self.client.post('/cases/DEMO/judgments', json=record, headers=analyst).status_code, 422)

    def test_reviewer_cannot_review_judgment_they_registered(self):
        record = self.store.get('J-1').model_dump(mode='json')
        record['id'] = 'J-SELF'
        self.assertEqual(self.client.post('/cases/DEMO/judgments', json=record, headers=self.headers).status_code, 201)
        g = self.client.post('/judgments/J-SELF/guardrail-checks', headers=self.headers).json()
        payload = {**self.request(), 'expected_dependency_digest': g['dependency_digest']}
        self.assertEqual(self.client.post('/judgments/J-SELF/reviews', json=payload, headers=self.headers).status_code, 403)

    def test_conclusion_snapshot_endpoints(self):
        self.assertEqual(self.client.post('/judgments/J-1/reviews', json=self.request(), headers=self.headers).status_code, 201)
        body = {'scope_id': 'SCOPE-1', 'judgment_ids': ['J-1'], 'purpose': '제출본'}
        created = self.client.post('/cases/DEMO/conclusion-snapshots', json=body, headers=self.headers)
        self.assertEqual(created.status_code, 201, created.text)
        self.assertTrue(created.json()['complete'])
        fetched = self.client.get(f"/conclusion-snapshots/{created.json()['id']}", headers=self.headers)
        self.assertEqual(fetched.json()['digest'], created.json()['digest'])
        denied = self.client.post('/cases/DEMO/conclusion-snapshots', json=body,
                                  headers={'Authorization': 'Bearer test-analyst'})
        self.assertEqual(denied.status_code, 403)


if __name__ == '__main__':
    unittest.main()
