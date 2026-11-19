from datetime import datetime, timezone
from hashlib import sha256

from .core import Store, calculate_reconciliation
from .models import AnalysisUnit, Assertion, Component, Input, Judgment, Reconciliation, Scope, SRow

AS_OF = datetime(2026, 10, 31, tzinfo=timezone.utc)
DEMO_AUTHOR = 'analyst-1'


def seed(store: Store, case='DEMO', scope='SCOPE-1'):
    store.add(Scope(id=scope, case_id=case, as_of=AS_OF, data_nature='illustrative',
                    termination_criteria='설명용 산술 대사와 검토 경계 확인'))
    common = {'case_id': case, 'scope_id': scope}
    for index, statement in enumerate(('준비자산 기초 1230', '운영자금 30 제외', '유통 잔액 1160', '미결 상환의무 40 포함'), 1):
        source = f'설명용 입력 {index}: {statement}'
        store.add(Input(id=f'IN-{index}', **common, source_ref=f'demo://component/{index}',
                        content_hash=sha256(source.encode()).hexdigest(), as_of=AS_OF, data_nature='illustrative'))
        store.add(Assertion(id=f'A-{index}', **common, input_id=f'IN-{index}', data_nature='illustrative',
                            nature='F', record_role='observation_or_inference', statement=statement,
                            claim_key='coverage', numeric_value=('1230', '30', '1160', '40')[index - 1], unit='USD',
                            observation_scope='설명용 자료에 기재된 값 확인; 실제 자산 실재는 미확인'))
    store.add(AnalysisUnit(id='UNIT-1', **common, question_statement='동일 기준시점의 준비자산과 상환의무는 산술적으로 일치하는가?',
                           question_type='consistency', module='M3', selection_reason='설명용 대사 사례'))
    store.add(SRow(id='S-1', **common, definition='설명용 범위에서 운영자금은 제외하고 미결 상환의무를 포함한다.',
                   element_type='condition', identification_status='confirmed', offchain_assertion_ids=('A-2', 'A-4')))
    store.add(Judgment(id='J-1', **common, unit_id='UNIT-1', required_s_row_ids=('S-1',),
                       required_assertion_ids=('A-1', 'A-2', 'A-3', 'A-4'),
                       proposed_grade='E1', proposed_status='confirmed_scoped',
                       author_rationale='설명용 범위 안에서 네 구성 항목이 모두 수치 주장에 연결되고 충돌이 없다.'),
              actor=DEMO_AUTHOR)
    components = tuple(Component(id=f'C-{i}', assertion_id=f'A-{i}', label=label, amount=value,
                                  side=side, treatment=treatment, rationale=reason, unit='USD', as_of=AS_OF)
                       for i, label, value, side, treatment, reason in [
                           (1, '준비자산 기초', '1230', 'reserve', 'base', '설명용 기초 자료'),
                           (2, '운영자금 제외', '30', 'reserve', 'exclude', '상환 재원 범위에서 제외한다고 가정'),
                           (3, '유통 잔액', '1160', 'obligation', 'base', '설명용 기초 자료'),
                           (4, '미결 상환의무', '40', 'obligation', 'include', '상환의무에 포함한다고 가정')])
    rec = Reconciliation(id='REC-1', **common, components=components, unit='USD', as_of=AS_OF)
    store.add(rec)
    return rec


def main():
    import json
    store = Store()
    rec = seed(store)
    print(json.dumps(calculate_reconciliation(rec), ensure_ascii=False, indent=2))
    print(json.dumps(store.guardrail('J-1'), ensure_ascii=False, indent=2))
    store.close()


if __name__ == '__main__':
    main()
