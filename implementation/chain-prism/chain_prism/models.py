from __future__ import annotations

from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Nature = Literal['actual', 'illustrative']
Status = Literal['confirmed_scoped', 'conditional', 'multiple_interp', 'reserved']
Grade = Literal['E1', 'E2', 'E3', 'E4']
Role = Literal['analyst', 'senior_reviewer', 'approver']
DiffType = Literal['fact_timing', 'doc_impl', 'module_premise', 'legitimate_basis', 'unresolved']
DiffStatus = Literal['open', 'explained', 'resolved', 'carried_forward']

# 부록 C 도표 C-1: 증거 등급이 허용하는 가장 강한 결론 표현.
# E1 범위를 밝혀 확정 / E2 범위를 좁혀 확정 또는 조건부 / E3 조건부 또는 유보 / E4 유보.
# 복수 해석은 부록 C 검토 기록 문단(작성자·검토자 불합의 시 복수 해석이나 유보)에 따라
# E1~E3에서 허용한다. 등급보다 약한 표현을 고르는 것은 언제나 허용한다.
GRADE_ALLOWED = {
    'E1': frozenset({'confirmed_scoped', 'conditional', 'multiple_interp', 'reserved'}),
    'E2': frozenset({'confirmed_scoped', 'conditional', 'multiple_interp', 'reserved'}),
    'E3': frozenset({'conditional', 'multiple_interp', 'reserved'}),
    'E4': frozenset({'reserved'}),
}


class Model(BaseModel):
    model_config = ConfigDict(frozen=True, extra='forbid', allow_inf_nan=False)

    @field_validator('*')
    @classmethod
    def no_blank_strings(cls, v):
        if isinstance(v, str) and not v.strip():
            raise ValueError('빈 문자열이나 공백만 있는 값은 허용하지 않습니다.')
        return v


class Scoped(Model):
    id: str
    case_id: str
    scope_id: str
    version: int = Field(default=1, ge=1)
    supersedes_id: str | None = None


class Scope(Model):
    id: str
    case_id: str
    version: int = Field(default=1, ge=1)
    supersedes_id: str | None = None
    data_nature: Nature
    as_of: datetime
    termination_criteria: str

    @field_validator('as_of')
    @classmethod
    def aware_time(cls, v):
        if v.utcoffset() is None:
            raise ValueError('기준시점에는 시간대가 필요합니다.')
        return v


class AnalysisUnit(Scoped):
    question_statement: str
    question_type: Literal['rights', 'auth_control', 'attribution', 'event_class', 'consistency', 'valuation']
    module: Literal['M1', 'M2', 'M3', 'M4', 'M5']
    question_card_id: str | None = None
    question_card_version: str | None = None
    selection_reason: str

    @model_validator(mode='after')
    def card_pair(self):
        if bool(self.question_card_id) != bool(self.question_card_version):
            raise ValueError('질문 카드 ID와 버전을 함께 지정하세요.')
        return self


class Input(Scoped):
    parent_input_ids: tuple[str, ...] = ()
    data_nature: Nature
    source_ref: str
    content_hash: str = Field(pattern=r'^[0-9a-f]{64}$')
    as_of: datetime
    # 범위 기준시점과 다른 시점의 자료(예: 9월 보고서와 11월 온체인 관찰)를 섞지 않고
    # 나란히 두려면 사유를 적는다. 이런 입력은 대사에 넣을 수 없고 F-05 기록 대상이 된다.
    as_of_deviation_reason: str | None = None

    _aware = field_validator('as_of')(Scope.aware_time.__func__)


class Assertion(Scoped):
    input_id: str
    data_nature: Nature
    nature: Literal['F', 'I', 'H']
    record_role: Literal['observation_or_inference', 'assumption', 'hypothesis']
    purpose: Literal['fact_completion', 'stress', 'alternative_structure', 'tech_experiment'] | None = None
    statement: str
    claim_key: str
    observation_scope: str | None = None
    conflicts_with: tuple[str, ...] = ()
    numeric_value: Decimal | None = None
    unit: str | None = None

    @field_validator('numeric_value', mode='before')
    @classmethod
    def numeric(cls, v):
        return None if v is None else exact_decimal(v)

    @model_validator(mode='after')
    def role_rules(self):
        if self.nature == 'H':
            if self.record_role not in ('assumption', 'hypothesis') or self.purpose is None:
                raise ValueError('H에는 가정/가설 역할과 목적이 필요합니다.')
        elif self.record_role != 'observation_or_inference' or self.purpose is not None:
            raise ValueError('F/I에는 observation_or_inference 역할만 허용합니다.')
        if self.nature == 'F' and not self.observation_scope:
            raise ValueError('F에는 직접 관찰한 범위를 명시하세요. 문서의 기재와 실재 사실은 다릅니다.')
        if self.numeric_value is not None and self.unit is None:
            raise ValueError('수치 주장에는 단위가 필요합니다.')
        return self


class TRow(Scoped):
    action_description: str
    nature: Literal['F', 'I']
    assertion_ids: tuple[str, ...] = Field(min_length=1)


class SRow(Scoped):
    definition: str
    element_type: Literal['subject', 'right', 'obligation', 'condition', 'unresolved_issue']
    identification_status: Literal['confirmed', 'inferred', 'unidentified']
    t_row_ids: tuple[str, ...] = ()
    offchain_assertion_ids: tuple[str, ...] = ()
    onchain_not_applicable: bool = False
    onchain_na_reason: str | None = None
    conditional_handover: bool = False
    handover_reason: str | None = None
    release_condition: str | None = None

    @model_validator(mode='after')
    def backing(self):
        if self.onchain_not_applicable and not self.onchain_na_reason:
            raise ValueError('온체인 비적용 사유가 필요합니다.')
        backed = bool(self.t_row_ids or self.offchain_assertion_ids)
        if not backed and not (self.element_type == 'unresolved_issue' and self.identification_status == 'unidentified'):
            raise ValueError('비적용 사유는 근거가 아닙니다. 근거 없는 항목은 미해결·미확인으로 기록하세요.')
        if self.conditional_handover and not (self.handover_reason and self.release_condition):
            raise ValueError('조건부 인계에는 사유와 해제 조건이 필요합니다.')
        return self


class Discrepancy(Scoped):
    """F-05 불일치·추가 확인 기록. 상태를 바꿀 때는 새 버전(supersedes_id)으로 등록한다."""
    diff_type: DiffType
    subject_ids: tuple[str, ...] = Field(min_length=1)
    description: str
    impact: str
    status: DiffStatus
    next_action: str | None = None
    resolution_condition: str | None = None
    explanation_ids: tuple[str, ...] = ()

    @model_validator(mode='after')
    def status_rules(self):
        if self.status in ('open', 'carried_forward') and not self.resolution_condition:
            raise ValueError('미해소 차이에는 해소 조건을 적으세요.')
        if self.status in ('explained', 'resolved') and not self.explanation_ids:
            raise ValueError('설명·해소한 차이에는 그 근거 주장을 연결하세요.')
        if self.diff_type == 'unresolved' and self.status in ('explained', 'resolved'):
            raise ValueError('미해결 유형은 설명·해소 상태가 될 수 없습니다. 유형을 바꾼 새 버전을 등록하세요.')
        if set(self.subject_ids) & set(self.explanation_ids):
            raise ValueError('차이의 대상과 그 설명 근거는 같을 수 없습니다.')
        return self


class Judgment(Scoped):
    unit_id: str
    required_s_row_ids: tuple[str, ...] = ()
    required_assertion_ids: tuple[str, ...] = ()
    relied_h_ids: tuple[str, ...] = ()
    discrepancy_ids: tuple[str, ...] = ()
    requires_substantive_assurance: tuple[str, ...] = ()
    # 작성자의 등급·상태·이유(부록 C: 작성자와 검토자가 각각 등급과 이유를 기록한다).
    proposed_grade: Grade
    proposed_status: Status
    author_rationale: str

    @model_validator(mode='after')
    def proposal_rules(self):
        if self.proposed_status not in GRADE_ALLOWED[self.proposed_grade]:
            raise ValueError(f'{self.proposed_grade} 등급으로는 {self.proposed_status} 결론을 제안할 수 없습니다.')
        return self


def exact_decimal(v):
    if isinstance(v, (float, bool)):
        raise ValueError('금액·비율은 문자열 또는 정수로 전달하세요. float은 허용하지 않습니다.')
    try:
        value = Decimal(v)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError('올바른 십진 금액·비율을 입력하세요.') from exc
    if not value.is_finite():
        raise ValueError('유한한 금액·비율만 허용합니다.')
    return value


class Amount(Model):
    amount: Decimal = Field(ge=0)
    _decimal = field_validator('amount', mode='before')(exact_decimal)


class Component(Amount):
    id: str
    assertion_id: str
    label: str
    side: Literal['reserve', 'obligation']
    treatment: Literal['base', 'include', 'exclude']
    rationale: str
    unit: str
    as_of: datetime
    _aware = field_validator('as_of')(Scope.aware_time.__func__)


class Reconciliation(Scoped):
    components: tuple[Component, ...] = Field(min_length=1)
    unit: str
    as_of: datetime
    tolerance: Decimal = Field(default=Decimal('0.00'), ge=0)
    display_cap: Decimal | None = Field(default=None, gt=0)
    _aware = field_validator('as_of')(Scope.aware_time.__func__)
    _decimal = field_validator('tolerance', 'display_cap', mode='before')(lambda v: None if v is None else exact_decimal(v))


class Principal(Model):
    id: str
    role: Role
    case_ids: tuple[str, ...]


class ReviewRequest(Model):
    expected_version: int = Field(ge=1)
    expected_dependency_digest: str
    decision: Literal['request_changes', 'hold_reserved', 'approve_conditional', 'approve_scoped', 'accept_multiple_interp']
    evidence_grade: Grade | None = None
    judgment_status: Status | None = None
    reason: str
    interpretation_alternatives: tuple[str, ...] = ()
    # 작성자 제안과 등급·상태가 다를 때 차이를 해소한 근거(기준·추가 증거·승인 사유).
    disagreement_resolution: str | None = None


class Review(Model):
    id: str
    judgment_id: str
    judgment_version: int
    case_id: str
    scope_id: str
    principal: Principal
    request: ReviewRequest
    dependency_digest: str
    dependency_ids: tuple[str, ...]
    ruleset_version: str
    recorded_at: datetime


class ConclusionSnapshot(Model):
    """F-06 제출용 고정 스냅샷. 조회 시점의 요약을 그대로 보존한다."""
    id: str
    case_id: str
    scope_id: str
    purpose: str
    frozen_by: Principal
    frozen_at: datetime
    ruleset_version: str
    complete: bool
    body: dict
    digest: str


RECORD_TYPES = (Scope, AnalysisUnit, Input, Assertion, TRow, SRow, Discrepancy, Judgment, Reconciliation)
TYPE_MAP = {t.__name__: t for t in RECORD_TYPES}
