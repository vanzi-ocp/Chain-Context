from __future__ import annotations

import hashlib
import json
import sqlite3
from collections import defaultdict
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP, localcontext
from threading import RLock
from uuid import uuid4

from .models import (GRADE_ALLOWED, AnalysisUnit, Assertion, ConclusionSnapshot, Discrepancy, Input,
                     Judgment, Principal, Reconciliation, Review, ReviewRequest, Scope, Scoped, SRow,
                     TRow, TYPE_MAP)

RULESET = 'ocp-reference-guardrail-0.2.1'
ALL_CONCLUSIONS = ('confirmed_scoped', 'conditional', 'multiple_interp')


def canonical_digest(obj):
    return hashlib.sha256(json.dumps(obj, sort_keys=True, ensure_ascii=False).encode()).hexdigest()


class DomainError(ValueError):
    pass


def refs(record):
    """Evidence dependencies, excluding supersession (which has a different meaning)."""
    result = [record.scope_id] if isinstance(record, Scoped) else []
    if isinstance(record, Input):
        result += list(record.parent_input_ids)
    elif isinstance(record, Assertion):
        result += [record.input_id] + list(record.conflicts_with)
    elif isinstance(record, TRow):
        result += list(record.assertion_ids)
    elif isinstance(record, SRow):
        result += list(record.t_row_ids) + list(record.offchain_assertion_ids)
    elif isinstance(record, Discrepancy):
        result += list(record.subject_ids) + list(record.explanation_ids)
    elif isinstance(record, Judgment):
        result += ([record.unit_id] + list(record.required_s_row_ids) + list(record.required_assertion_ids)
                   + list(record.relied_h_ids) + list(record.discrepancy_ids))
    elif isinstance(record, Reconciliation):
        result += [c.assertion_id for c in record.components]
    return tuple(dict.fromkeys(result))


class Store:
    """Append-only SQLite reference store. All writes are serialized and transactional.

    It preserves records and reviews across restart. This is not a tamper-proof
    archive: database administrators can edit the database outside this service.
    """

    def __init__(self, path=':memory:'):
        self._lock = RLock()
        self._db = sqlite3.connect(path, check_same_thread=False)
        self._db.execute('PRAGMA foreign_keys=ON')
        self._db.executescript('''
            CREATE TABLE IF NOT EXISTS records (
                id TEXT PRIMARY KEY, kind TEXT NOT NULL, body TEXT NOT NULL,
                supersedes TEXT UNIQUE REFERENCES records(id));
            CREATE TABLE IF NOT EXISTS reviews (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL,
                judgment_id TEXT NOT NULL REFERENCES records(id), body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS run_results (
                id TEXT PRIMARY KEY REFERENCES records(id), body TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS conclusions (
                seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT UNIQUE NOT NULL, body TEXT NOT NULL);
        ''')
        # 0.2.0 DB 호환: 작성자 열이 없으면 추가한다(기존 레코드는 작성자 미상으로 남는다).
        columns = {row[1] for row in self._db.execute('PRAGMA table_info(records)')}
        if 'created_by' not in columns:
            self._db.execute('ALTER TABLE records ADD COLUMN created_by TEXT')
            self._db.commit()

    def close(self):
        self._db.close()

    def get(self, record_id, cls=None):
        with self._lock:
            row = self._db.execute('SELECT kind,body FROM records WHERE id=?', (record_id,)).fetchone()
            if row is None:
                raise DomainError(f'미등록 참조: {record_id}')
            record = TYPE_MAP[row[0]].model_validate_json(row[1])
            if cls is not None and not isinstance(record, cls):
                raise DomainError(f'참조 유형 불일치: {record_id}, expected {cls.__name__}')
            return record

    def author(self, record_id):
        row = self._db.execute('SELECT created_by FROM records WHERE id=?', (record_id,)).fetchone()
        if row is None:
            raise DomainError(f'미등록 참조: {record_id}')
        return row[0]

    def _current(self, kind, case_id, scope_id):
        rows = self._db.execute('SELECT id FROM records WHERE kind=?', (kind,)).fetchall()
        out = []
        for (rid,) in rows:
            r = self.get(rid)
            if r.case_id == case_id and r.scope_id == scope_id and not self.is_superseded(rid):
                out.append(r)
        return out

    def _touching_discrepancies(self, judgment, closure):
        return [d for d in self._current('Discrepancy', judgment.case_id, judgment.scope_id)
                if set(d.subject_ids) & closure]

    def is_superseded(self, record_id):
        return self._db.execute('SELECT 1 FROM records WHERE supersedes=?', (record_id,)).fetchone() is not None

    def _same_scope(self, record, target):
        if record.case_id != target.case_id or record.scope_id != target.scope_id:
            raise DomainError(f'사건·범위 불일치: {record.id} → {target.id}')

    def add(self, record, actor: str | None = None):
        """actor는 서버가 인증으로 정한 작성자 ID다. 판단(F-04)은 작성자 없이 등록할 수 없다."""
        with self._lock, self._db:
            self._db.execute('BEGIN IMMEDIATE')
            if type(record).__name__ not in TYPE_MAP:
                raise DomainError('지원하지 않는 레코드 유형')
            if isinstance(record, Judgment) and not actor:
                raise DomainError('판단은 작성자(actor)와 함께 등록해야 합니다. 작성자와 검토자를 구분하기 위함입니다.')
            if self._db.execute('SELECT 1 FROM records WHERE id=?', (record.id,)).fetchone():
                raise DomainError(f'기존 ID 덮어쓰기 금지: {record.id}')
            if record.supersedes_id:
                previous = self.get(record.supersedes_id, type(record))
                if previous.case_id != record.case_id or record.version != previous.version + 1:
                    raise DomainError('대체 버전은 동일 사건에서 이전 버전 +1이어야 합니다.')
                if isinstance(record, Scoped):
                    self._same_scope(record, previous)
                if self.is_superseded(previous.id):
                    raise DomainError('이미 대체된 버전의 중복 대체·분기 금지')
            elif record.version != 1:
                raise DomainError('최초 레코드는 version=1이어야 합니다.')
            if isinstance(record, Scoped):
                scope = self.get(record.scope_id, Scope)
                if scope.case_id != record.case_id:
                    raise DomainError('다른 사건의 범위 참조 금지')
                if self.is_superseded(scope.id):
                    raise DomainError('대체된 범위에 신규 레코드를 등록할 수 없습니다.')
                for rid in refs(record):
                    target = self.get(rid)
                    if isinstance(target, Scoped):
                        self._same_scope(record, target)
                if isinstance(record, (Input, Assertion)) and record.data_nature != scope.data_nature:
                    raise DomainError('실증 자료와 설명용 자료를 같은 범위에 혼합할 수 없습니다.')
            if isinstance(record, Input):
                for parent in record.parent_input_ids:
                    self.get(parent, Input)
                if record.as_of != scope.as_of and not record.as_of_deviation_reason:
                    raise DomainError('입력 기준시점이 범위와 다릅니다. 정규화한 새 입력을 등록하거나, '
                                      '시점이 다른 자료를 나란히 둘 사유(as_of_deviation_reason)를 적으세요.')
                if record.as_of == scope.as_of and record.as_of_deviation_reason:
                    raise DomainError('기준시점이 범위와 같은 입력에는 시점 차이 사유를 적지 않습니다.')
            elif isinstance(record, Assertion):
                inp = self.get(record.input_id, Input)
                if inp.data_nature != record.data_nature:
                    raise DomainError('입력과 주장의 자료 성격 불일치')
                for conflict in record.conflicts_with:
                    self.get(conflict, Assertion)
            elif isinstance(record, TRow):
                assertions = [self.get(a, Assertion) for a in record.assertion_ids]
                if record.nature == 'F' and any(a.nature != 'F' for a in assertions):
                    raise DomainError('추론·가정을 T행에서 관찰 사실로 승격할 수 없습니다.')
            elif isinstance(record, SRow):
                for t in record.t_row_ids:
                    self.get(t, TRow)
                for a in record.offchain_assertion_ids:
                    self.get(a, Assertion)
            elif isinstance(record, Discrepancy):
                for sid in record.subject_ids:
                    if not isinstance(self.get(sid), (Assertion, TRow, SRow)):
                        raise DomainError('차이의 대상은 주장·T행·S행이어야 합니다.')
                for eid in record.explanation_ids:
                    self.get(eid, Assertion)
            elif isinstance(record, Judgment):
                self.get(record.unit_id, AnalysisUnit)
                for d in record.discrepancy_ids:
                    self.get(d, Discrepancy)
                    if self.is_superseded(d):
                        raise DomainError(f'대체된 불일치 기록을 인용할 수 없습니다: {d}')
                for s in record.required_s_row_ids:
                    self.get(s, SRow)
                for a in record.required_assertion_ids:
                    self.get(a, Assertion)
                for h in record.relied_h_ids:
                    if self.get(h, Assertion).nature != 'H':
                        raise DomainError('relied_h_ids에는 H만 지정할 수 있습니다.')
                # No H laundering through S/T rows: all actually relied-on H must be declared.
                dependencies = self._closure_for(record)
                h_ids = {i for i in dependencies if isinstance(self.get(i), Assertion) and self.get(i).nature == 'H'}
                if h_ids - set(record.relied_h_ids):
                    raise DomainError('의존관계에 포함된 H를 relied_h_ids에 명시하세요.')
                # 판단의 근거에 걸린 F-05 차이도 숨길 수 없다.
                hidden = {d.id for d in self._touching_discrepancies(record, dependencies)} - set(record.discrepancy_ids)
                if hidden:
                    raise DomainError(f'근거에 걸린 불일치 기록을 discrepancy_ids에 명시하세요: {sorted(hidden)}')
            elif isinstance(record, Reconciliation):
                self._validate_reconciliation(record, scope)
            try:
                self._db.execute('INSERT INTO records(id,kind,body,supersedes,created_by) VALUES (?,?,?,?,?)',
                                 (record.id, type(record).__name__, record.model_dump_json(), record.supersedes_id, actor))
                if isinstance(record, Reconciliation):
                    self._db.execute('INSERT INTO run_results VALUES (?,?)',
                                     (record.id, json.dumps(calculate_reconciliation(record), ensure_ascii=False)))
            except sqlite3.IntegrityError as exc:
                raise DomainError('중복 ID 또는 대체 버전 충돌') from exc
            return record

    def _closure_for(self, record):
        seen, visiting = set(), set()

        def visit(rid):
            if rid in visiting:
                raise DomainError(f'계보·참조 순환: {rid}')
            if rid in seen:
                return
            visiting.add(rid)
            target = self.get(rid)
            for child in refs(target):
                visit(child)
            visiting.remove(rid)
            seen.add(rid)

        for rid in refs(record):
            if rid == record.id:
                raise DomainError('자기 참조 금지')
            visit(rid)
        return seen

    def _validate_reconciliation(self, rec, scope):
        if rec.as_of != scope.as_of:
            raise DomainError('대사 기준시점이 범위와 다릅니다.')
        ids, assertions = set(), set()
        for c in rec.components:
            assertion = self.get(c.assertion_id, Assertion)
            if assertion.numeric_value != c.amount or assertion.unit != c.unit:
                raise DomainError('대사 금액·단위가 연결된 수치 주장과 다릅니다.')
            if self.is_superseded(assertion.id) or any(self.is_superseded(rid) for rid in self._closure_for(assertion)):
                raise DomainError('대체된 근거로 새 대사를 실행할 수 없습니다.')
            if self.get(assertion.input_id, Input).as_of != rec.as_of:
                raise DomainError('기준시점이 다른 입력은 대사에 넣지 않습니다. 차이는 F-05(Discrepancy)에 기록하세요.')
            if c.id in ids or c.assertion_id in assertions:
                raise DomainError('동일 구성 항목·동일 금액 근거 중복 집계 금지')
            ids.add(c.id)
            assertions.add(c.assertion_id)
            if c.unit != rec.unit or c.as_of != rec.as_of:
                raise DomainError('구성 항목의 단위·시점 불일치')
        for side in ('reserve', 'obligation'):
            if not any(c.side == side and c.treatment == 'base' for c in rec.components):
                raise DomainError('준비자산·의무 각각 기초 잔액이 필요합니다.')
        # Distinct components from the same document can be legitimate. Do not
        # collapse them by source alone; duplicate economic items need separate review.
        calculate_reconciliation(rec)

    def run_result(self, run_id):
        with self._lock:
            self.get(run_id, Reconciliation)
            row = self._db.execute('SELECT body FROM run_results WHERE id=?', (run_id,)).fetchone()
            if row is None:
                raise DomainError('실행 결과 스냅샷이 없습니다.')
            return json.loads(row[0])

    def lineage_roots(self, input_id):
        inp = self.get(input_id, Input)
        if not inp.parent_input_ids:
            return frozenset([inp.content_hash])
        return frozenset().union(*(self.lineage_roots(p) for p in inp.parent_input_ids))

    def evidence_independence(self, assertion_ids):
        """Preserve records. Report shared origins; never count them as independent votes."""
        result, overlaps = {}, []
        for aid in dict.fromkeys(assertion_ids):
            a = self.get(aid, Assertion)
            result[aid] = self.lineage_roots(a.input_id)
        for index, left in enumerate(result):
            for right in list(result)[index + 1:]:
                common = result[left] & result[right]
                if common:
                    overlaps.append({'assertion_ids': [left, right], 'shared_root_hashes': sorted(common)})
        return {'assertion_ids': list(result), 'overlaps': overlaps,
                'independent_evidence_count': None,
                'note': '공유 원천은 독립 증거 수로 합산하지 않습니다. 원천 분리도 독립성을 입증하지 않습니다.'}

    def guardrail(self, judgment_id):
        with self._lock:
            j = self.get(judgment_id, Judgment)
            dependencies = self._closure_for(j)
            all_records = [self.get(rid) for rid in dependencies]
            issues, blocked = [], set()
            stale = sorted(rid for rid in dependencies | {j.id} if self.is_superseded(rid))
            if stale:
                issues.append({'code': 'STALE_DEPENDENCY', 'ids': stale})
                blocked.update(('confirmed_scoped', 'conditional', 'multiple_interp'))
            relevant = [r for r in all_records if isinstance(r, Assertion)]
            # No blanket "direct evidence absent => E4" rule. Sufficiency remains human judgment.
            if not relevant:
                issues.append({'code': 'CORE_EVIDENCE_MISSING', 'ids': []})
                blocked.update(('confirmed_scoped', 'conditional', 'multiple_interp'))
            for r in all_records:
                if isinstance(r, SRow) and (r.identification_status != 'confirmed' or r.conditional_handover):
                    issues.append({'code': 'STRUCTURE_GATE', 'ids': [r.id]})
                    blocked.add('confirmed_scoped')
                if isinstance(r, Assertion) and r.conflicts_with:
                    issues.append({'code': 'EVIDENCE_CONFLICT', 'ids': [r.id, *r.conflicts_with]})
                    blocked.add('confirmed_scoped')
            if j.relied_h_ids:
                issues.append({'code': 'RELIED_H', 'ids': list(j.relied_h_ids)})
                blocked.add('confirmed_scoped')
            # F-05: 판단의 근거에 걸린 차이
            touching = self._touching_discrepancies(j, dependencies)
            undeclared = sorted({d.id for d in touching} - set(j.discrepancy_ids))
            if undeclared:
                issues.append({'code': 'UNDECLARED_DISCREPANCY', 'ids': undeclared})
                blocked.update(ALL_CONCLUSIONS)
            declared = [r for r in all_records if isinstance(r, Discrepancy)]
            for d in declared:
                if d.status in ('open', 'carried_forward'):
                    issues.append({'code': 'OPEN_DISCREPANCY', 'ids': [d.id], 'diff_type': d.diff_type})
                    blocked.add('confirmed_scoped')
            # 기준시점이 다른 입력: 설명·해소된 fact_timing 차이가 그 입력을 다루지 않으면 확정 불가
            covered = set()
            for d in declared:
                if d.diff_type == 'fact_timing' and d.status in ('explained', 'resolved') and not self.is_superseded(d.id):
                    for sid in d.subject_ids:
                        covered |= self._closure_for(self.get(sid)) | {sid}
            for r in all_records:
                if isinstance(r, Input) and r.as_of_deviation_reason and r.id not in covered:
                    issues.append({'code': 'TIMING_DEVIATION', 'ids': [r.id]})
                    blocked.add('confirmed_scoped')
            if j.requires_substantive_assurance:
                issues.append({'code': 'SUBSTANTIVE_ASSURANCE_REQUIRES_SEPARATE_ASSESSMENT', 'ids': list(j.requires_substantive_assurance)})
                blocked.add('confirmed_scoped')
            # Include supersession state so a concurrent correction invalidates the review token.
            snapshot = [{'id': rid, 'body': self.get(rid).model_dump(mode='json'),
                         'superseded': self.is_superseded(rid)} for rid in sorted(dependencies | {j.id})]
            snapshot.append({'undeclared_discrepancies': undeclared})
            digest = canonical_digest(snapshot)
            needs = bool(stale or undeclared)
            return {'judgment_id': j.id, 'judgment_version': j.version, 'author': self.author(j.id),
                    'proposal': {'grade': j.proposed_grade, 'status': j.proposed_status, 'rationale': j.author_rationale},
                    'blocked_statuses': sorted(blocked), 'issues': issues,
                    're_review_required': needs, 'dependency_ids': sorted(dependencies),
                    'dependency_digest': digest, 'ready_for_review': not needs,
                    'ruleset_version': RULESET,
                    'independence': self.evidence_independence([r.id for r in relevant])}

    def review(self, judgment_id: str, request: ReviewRequest, principal: Principal):
        with self._lock, self._db:
            self._db.execute('BEGIN IMMEDIATE')
            j = self.get(judgment_id, Judgment)
            if j.case_id not in principal.case_ids:
                raise PermissionError('검토자의 사건 접근 권한이 없습니다.')
            if self.is_superseded(j.id):
                raise DomainError('대체된 판단은 검토할 수 없습니다.')
            author = self.author(j.id)
            if author is None:
                raise DomainError('작성자 미상의 판단(0.2.0 이전 기록)은 검토할 수 없습니다. 작성자를 밝힌 새 버전을 등록하세요.')
            if author == principal.id:
                raise PermissionError('작성자는 자기 판단을 검토할 수 없습니다.')
            g = self.guardrail(j.id)
            if request.expected_version != j.version or request.expected_dependency_digest != g['dependency_digest']:
                raise DomainError('판단 버전 또는 근거 스냅샷이 변경되었습니다. 다시 조회하세요.')
            expected_status = {'approve_scoped': 'confirmed_scoped', 'approve_conditional': 'conditional',
                               'hold_reserved': 'reserved', 'accept_multiple_interp': 'multiple_interp',
                               'request_changes': None}[request.decision]
            if request.judgment_status != expected_status:
                raise DomainError('검토 결정과 판단 상태의 조합이 맞지 않습니다.')
            if expected_status is not None:
                if principal.role not in ('senior_reviewer', 'approver'):
                    raise PermissionError('전문 판단 검토에는 상위 검토 권한이 필요합니다.')
                if request.evidence_grade is None:
                    raise DomainError('판단 상태를 기록할 때 근거 등급을 명시하세요.')
                if expected_status in g['blocked_statuses']:
                    raise DomainError('가드레일에서 차단한 결론입니다.')
                if expected_status == 'multiple_interp' and len(set(request.interpretation_alternatives)) < 2:
                    raise DomainError('복수 해석은 성립 가능한 대안을 두 개 이상 기록해야 합니다.')
                if expected_status not in GRADE_ALLOWED[request.evidence_grade]:
                    raise DomainError(f'{request.evidence_grade} 등급으로는 {expected_status} 결론을 기록할 수 없습니다(부록 C 도표 C-1).')
                if ((request.evidence_grade, expected_status) != (j.proposed_grade, j.proposed_status)
                        and not request.disagreement_resolution):
                    raise DomainError('작성자 제안과 등급·상태가 다릅니다. 차이를 해소한 근거(disagreement_resolution)를 적으세요.')
            elif request.evidence_grade is not None:
                raise DomainError('수정 요청은 최종 등급을 확정하지 않습니다.')
            rec = Review(id=f'REV-{uuid4().hex}', judgment_id=j.id, judgment_version=j.version,
                         case_id=j.case_id, scope_id=j.scope_id, principal=principal, request=request,
                         dependency_digest=g['dependency_digest'], dependency_ids=tuple(g['dependency_ids']),
                         ruleset_version=RULESET, recorded_at=datetime.now(timezone.utc))
            self._db.execute('INSERT INTO reviews(id,judgment_id,body) VALUES (?,?,?)',
                             (rec.id, j.id, rec.model_dump_json()))
            return rec

    def summary(self, case_id, scope_id, judgment_ids):
        with self._lock:
            scope = self.get(scope_id, Scope)
            if scope.case_id != case_id:
                raise DomainError('사건·범위 불일치')
            items = []
            for jid in judgment_ids:
                j = self.get(jid, Judgment)
                if j.case_id != case_id or j.scope_id != scope_id:
                    raise DomainError('다른 사건·범위의 판단을 요약에 섞을 수 없습니다.')
                g = self.guardrail(jid)
                row = self._db.execute('SELECT body FROM reviews WHERE judgment_id=? ORDER BY seq DESC LIMIT 1', (jid,)).fetchone()
                latest = Review.model_validate_json(row[0]) if row else None
                active = bool(latest and latest.dependency_digest == g['dependency_digest'] and not g['re_review_required'])
                items.append({'judgment': j.model_dump(mode='json'), 'author': g['author'], 'guardrail': g,
                              'latest_review': latest.model_dump(mode='json') if latest else None,
                              'review_applies_to_current_dependencies': active,
                              'effective_status': latest.request.judgment_status if active else None})
            return {'case_id': case_id, 'scope_id': scope_id, 'data_nature': scope.data_nature,
                    'generated_at': datetime.now(timezone.utc).isoformat(), 'judgments': items,
                    'note': '과거 검토는 보존됩니다. 근거 변경 시 현재 유효 결론으로 사용하지 않습니다.'}


    def freeze_conclusion(self, case_id, scope_id, judgment_ids, principal: Principal, purpose: str):
        """F-06 제출용 고정 스냅샷. 근거가 나중에 바뀌어도 이 기록은 바뀌지 않는다."""
        if case_id not in principal.case_ids:
            raise PermissionError('이 사건에 접근할 수 없습니다.')
        if principal.role not in ('senior_reviewer', 'approver'):
            raise PermissionError('결론 고정에는 상위 검토 권한이 필요합니다.')
        if not purpose.strip():
            raise DomainError('고정 목적을 적으세요.')
        with self._lock, self._db:
            self._db.execute('BEGIN IMMEDIATE')
            body = self.summary(case_id, scope_id, judgment_ids)
            complete = all(item['effective_status'] is not None for item in body['judgments'])
            snap = ConclusionSnapshot(id=f'CON-{uuid4().hex}', case_id=case_id, scope_id=scope_id, purpose=purpose,
                                      frozen_by=principal, frozen_at=datetime.now(timezone.utc),
                                      ruleset_version=RULESET, complete=complete, body=body,
                                      digest=canonical_digest(body))
            self._db.execute('INSERT INTO conclusions(id,body) VALUES (?,?)', (snap.id, snap.model_dump_json()))
            return snap

    def get_conclusion(self, conclusion_id):
        with self._lock:
            row = self._db.execute('SELECT body FROM conclusions WHERE id=?', (conclusion_id,)).fetchone()
            if row is None:
                raise DomainError(f'미등록 결론 스냅샷: {conclusion_id}')
            snap = ConclusionSnapshot.model_validate_json(row[0])
            if canonical_digest(snap.body) != snap.digest:
                raise DomainError('결론 스냅샷의 내용이 저장 당시 해시와 다릅니다.')
            return snap


def calculate_reconciliation(rec: Reconciliation):
    """Reconcile numerator AND denominator; clipping is an explicitly separate display value."""
    with localcontext() as ctx:
        ctx.prec = 50
        totals = defaultdict(lambda: Decimal(0))
        breakdown = []
        for c in rec.components:
            totals[(c.side, c.treatment)] += c.amount
            breakdown.append(c.model_dump(mode='json'))
        rb, ob = totals['reserve', 'base'], totals['obligation', 'base']
        reserve = rb + totals['reserve', 'include'] - totals['reserve', 'exclude']
        obligation = ob + totals['obligation', 'include'] - totals['obligation', 'exclude']
        if ob <= 0 or obligation <= 0 or reserve < 0 or rb < 0:
            raise DomainError('의무는 양수, 조정 준비자산은 0 이상이어야 합니다.')
        def pct(a, b):
            return str((a / b * 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP))
        gap = reserve - obligation
        result = {'run_id': rec.id, 'case_id': rec.case_id, 'scope_id': rec.scope_id,
                  'unit': rec.unit, 'as_of': rec.as_of.isoformat(),
                  'raw_reserve': str(rb), 'raw_obligation': str(ob), 'raw_ratio_pct': pct(rb, ob),
                  'adjusted_reserve': str(reserve), 'adjusted_obligation': str(obligation),
                  'adjusted_ratio_pct': pct(reserve, obligation), 'difference_amount': str(gap),
                  'within_tolerance': abs(gap) <= rec.tolerance, 'tolerance': str(rec.tolerance),
                  'component_breakdown': breakdown, 'auto_approved_conclusion': False,
                  'candidate_state': 'needs_review', 'ruleset_version': RULESET,
                  'note': '산술 재현 결과입니다. 실재성·상환능력·통제 효과성·조정의 적정성을 확정하지 않습니다.'}
        if rec.display_cap is not None:
            result['capped_display_ratio_pct'] = pct(min(reserve / obligation, rec.display_cap), Decimal(1))
            result['display_cap_is_reconciliation_adjustment'] = False
        return result
