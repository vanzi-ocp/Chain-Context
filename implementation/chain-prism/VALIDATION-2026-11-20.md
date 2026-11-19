# 저장소 업로드 전 검증 · 2026-11-20

제공받은 v0.2.1 원본 코드를 변경하지 않고 실행했습니다.

- Python 3.12.14
- pydantic 2.13.4, FastAPI 0.141.1, Starlette 1.6.0, httpx 0.28.1
- 명령: `python -m unittest discover -v`
- 결과: API 테스트 포함 63개 통과
- Starlette TestClient의 httpx 관련 사용 중단 예정 경고가 있었으나 테스트 실패는 없었습니다.

원 패키지의 VALIDATION.md와 test-results.txt는 이전 환경의 검증 이력이므로 수정하지 않았습니다. 이번 테스트 통과는 운영 배포·독립 감사·전문 판단의 정확성 검증을 뜻하지 않습니다.

## 실행 출력

```text
/opt/codex/runtimes/codex-primary-runtime/dependencies/python/lib/python3.12/site-packages/fastapi/testclient.py:1: StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated; install `httpx2` instead.
  from starlette.testclient import TestClient as TestClient  # noqa
test_analyst_cannot_approve_via_api (tests.test_api.ApiTests.test_analyst_cannot_approve_via_api) ... ok
test_client_cannot_supply_reviewer_identity (tests.test_api.ApiTests.test_client_cannot_supply_reviewer_identity) ... ok
test_conclusion_snapshot_endpoints (tests.test_api.ApiTests.test_conclusion_snapshot_endpoints) ... ok
test_cross_case_access_denied (tests.test_api.ApiTests.test_cross_case_access_denied) ... ok
test_get_saved_run (tests.test_api.ApiTests.test_get_saved_run) ... ok
test_judgment_author_comes_from_token (tests.test_api.ApiTests.test_judgment_author_comes_from_token) ... ok
test_no_auth_rejected (tests.test_api.ApiTests.test_no_auth_rejected) ... ok
test_openapi_generated (tests.test_api.ApiTests.test_openapi_generated) ... ok
test_reviewer_cannot_review_judgment_they_registered (tests.test_api.ApiTests.test_reviewer_cannot_review_judgment_they_registered) ... ok
test_stale_review_token_rejected (tests.test_api.ApiTests.test_stale_review_token_rejected) ... ok
test_successful_review_uses_server_identity (tests.test_api.ApiTests.test_successful_review_uses_server_identity) ... ok
test_summary_scope_validation (tests.test_api.ApiTests.test_summary_scope_validation) ... ok
test_typed_registration_and_path_case_check (tests.test_api.ApiTests.test_typed_registration_and_path_case_check) ... ok
test_actual_illustrative_mixing_rejected (tests.test_core.CoreTests.test_actual_illustrative_mixing_rejected) ... ok
test_analyst_cannot_approve (tests.test_core.CoreTests.test_analyst_cannot_approve) ... ok
test_assertion_replacement_alone_invalidates_review (tests.test_core.CoreTests.test_assertion_replacement_alone_invalidates_review) ... ok
test_component_unit_time_and_source_amount_rejected (tests.test_core.CoreTests.test_component_unit_time_and_source_amount_rejected) ... ok
test_display_cap_does_not_hide_gap (tests.test_core.CoreTests.test_display_cap_does_not_hide_gap) ... ok
test_duplicate_component_rejected (tests.test_core.CoreTests.test_duplicate_component_rejected) ... ok
test_duplicate_srow_rejected (tests.test_core.CoreTests.test_duplicate_srow_rejected) ... ok
test_duplicate_supersession_and_version_jump_rejected (tests.test_core.CoreTests.test_duplicate_supersession_and_version_jump_rejected) ... ok
test_e4_cannot_confirm (tests.test_core.CoreTests.test_e4_cannot_confirm) ... ok
test_float_money_and_nan_rejected (tests.test_core.CoreTests.test_float_money_and_nan_rejected) ... ok
test_fresh_judgment_can_be_reviewed_after_replacement (tests.test_core.CoreTests.test_fresh_judgment_can_be_reviewed_after_replacement) ... ok
test_h_cannot_be_hidden_in_structure (tests.test_core.CoreTests.test_h_cannot_be_hidden_in_structure) ... ok
test_input_change_propagates_through_assertion (tests.test_core.CoreTests.test_input_change_propagates_through_assertion) ... ok
test_lineage_overlap_preserves_both_records (tests.test_core.CoreTests.test_lineage_overlap_preserves_both_records) ... ok
test_mismatched_decision_status_rejected (tests.test_core.CoreTests.test_mismatched_decision_status_rejected) ... ok
test_missing_parent_rejected (tests.test_core.CoreTests.test_missing_parent_rejected) ... ok
test_missing_srow_rejected (tests.test_core.CoreTests.test_missing_srow_rejected) ... ok
test_multiple_interpretations_need_two_alternatives (tests.test_core.CoreTests.test_multiple_interpretations_need_two_alternatives) ... ok
test_na_reason_does_not_replace_evidence (tests.test_core.CoreTests.test_na_reason_does_not_replace_evidence) ... ok
test_old_dependency_cannot_receive_conditional_approval (tests.test_core.CoreTests.test_old_dependency_cannot_receive_conditional_approval) ... ok
test_persistence_of_records_reviews_and_run_snapshot (tests.test_core.CoreTests.test_persistence_of_records_reviews_and_run_snapshot) ... ok
test_reconciliation_adjusts_both_sides (tests.test_core.CoreTests.test_reconciliation_adjusts_both_sides) ... ok
test_review_other_case_rejected (tests.test_core.CoreTests.test_review_other_case_rejected) ... ok
test_same_case_different_scope_rejected (tests.test_core.CoreTests.test_same_case_different_scope_rejected) ... ok
test_scope_and_case_mixing_rejected (tests.test_core.CoreTests.test_scope_and_case_mixing_rejected) ... ok
test_self_cycle_rejected (tests.test_core.CoreTests.test_self_cycle_rejected) ... ok
test_srow_change_alone_propagates (tests.test_core.CoreTests.test_srow_change_alone_propagates) ... ok
test_stale_snapshot_rejected (tests.test_core.CoreTests.test_stale_snapshot_rejected) ... ok
test_substantive_assurance_not_automatically_confirmed (tests.test_core.CoreTests.test_substantive_assurance_not_automatically_confirmed) ... ok
test_transitive_input_lineage_propagates (tests.test_core.CoreTests.test_transitive_input_lineage_propagates) ... ok
test_two_different_claims_from_one_input_not_deleted (tests.test_core.CoreTests.test_two_different_claims_from_one_input_not_deleted) ... ok
test_author_cannot_review_own_judgment (tests.test_v021.V021Tests.test_author_cannot_review_own_judgment) ... ok
test_author_recorded_in_guardrail_and_summary (tests.test_v021.V021Tests.test_author_recorded_in_guardrail_and_summary) ... ok
test_conclusion_snapshot_frozen_and_verified (tests.test_v021.V021Tests.test_conclusion_snapshot_frozen_and_verified) ... ok
test_deviating_input_cannot_enter_reconciliation (tests.test_v021.V021Tests.test_deviating_input_cannot_enter_reconciliation) ... ok
test_disagreement_with_author_needs_resolution (tests.test_v021.V021Tests.test_disagreement_with_author_needs_resolution) ... ok
test_discrepancy_found_after_judgment_forces_re_review (tests.test_v021.V021Tests.test_discrepancy_found_after_judgment_forces_re_review) ... ok
test_discrepancy_rules (tests.test_v021.V021Tests.test_discrepancy_rules) ... ok
test_discrepancy_status_change_invalidates_review (tests.test_v021.V021Tests.test_discrepancy_status_change_invalidates_review) ... ok
test_grade_table_matches_appendix_c (tests.test_v021.V021Tests.test_grade_table_matches_appendix_c) ... ok
test_hidden_discrepancy_rejected_at_registration (tests.test_v021.V021Tests.test_hidden_discrepancy_rejected_at_registration) ... ok
test_incomplete_snapshot_flagged_and_analyst_cannot_freeze (tests.test_v021.V021Tests.test_incomplete_snapshot_flagged_and_analyst_cannot_freeze) ... ok
test_inconsistent_proposal_rejected (tests.test_v021.V021Tests.test_inconsistent_proposal_rejected) ... ok
test_judgment_without_author_rejected (tests.test_v021.V021Tests.test_judgment_without_author_rejected) ... ok
test_legacy_db_without_author_column_opens_and_blocks_review (tests.test_v021.V021Tests.test_legacy_db_without_author_column_opens_and_blocks_review) ... ok
test_open_discrepancy_blocks_confirmation_only (tests.test_v021.V021Tests.test_open_discrepancy_blocks_confirmation_only) ... ok
test_pilot_dao_grant_e3_scoped_adoption_rejected (tests.test_v021.V021Tests.test_pilot_dao_grant_e3_scoped_adoption_rejected) ... ok
test_tampered_snapshot_detected (tests.test_v021.V021Tests.test_tampered_snapshot_detected) ... ok
test_timing_deviation_blocks_until_explained (tests.test_v021.V021Tests.test_timing_deviation_blocks_until_explained) ... ok
test_timing_deviation_needs_reason (tests.test_v021.V021Tests.test_timing_deviation_needs_reason) ... ok

----------------------------------------------------------------------
Ran 63 tests in 0.599s

OK

```
