import secrets
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from pydantic import Field

from .core import DomainError, Store, calculate_reconciliation
from .models import (AnalysisUnit, Assertion, Discrepancy, Input, Judgment, Model, Principal,
                     Reconciliation, ReviewRequest, Scope, SRow, TRow)


class SummaryRequest(Model):
    scope_id: str
    judgment_ids: tuple[str, ...] = Field(min_length=1)


class FreezeRequest(SummaryRequest):
    purpose: str


def create_app(store: Store | None = None, principals: dict[str, Principal] | None = None):
    """Tokens/principals are supplied by the hosting service, never by a request body.

    No default tokens or trusted identity headers. Production should replace this
    small static-token adapter with organization SSO and server-side authorization.
    """
    svc = store if store is not None else Store()
    identities = dict(principals or {})
    app = FastAPI(title='Chain Prism reference API', version='0.2.1')
    bearer = HTTPBearer(auto_error=False)

    def principal(credentials: Annotated[HTTPAuthorizationCredentials | None, Depends(bearer)]):
        if credentials and credentials.scheme.lower() == 'bearer':
            for token, identity in identities.items():
                if secrets.compare_digest(credentials.credentials, token):
                    return identity
        raise HTTPException(401, '인증이 필요합니다.')

    Identity = Annotated[Principal, Depends(principal)]

    def allow(identity, case_id, write=False):
        if case_id not in identity.case_ids:
            raise HTTPException(403, '이 사건에 접근할 수 없습니다.')
        if write and identity.role not in ('analyst', 'senior_reviewer', 'approver'):
            raise HTTPException(403, '기록 권한이 없습니다.')

    @app.exception_handler(DomainError)
    async def domain_error(request: Request, exc: DomainError):
        return JSONResponse(status_code=409, content={'detail': str(exc)})

    @app.exception_handler(PermissionError)
    async def permission_error(request: Request, exc: PermissionError):
        return JSONResponse(status_code=403, content={'detail': str(exc)})

    @app.get('/health')
    def health():
        return {'status': 'ok', 'implementation_version': '0.2.1'}

    # Typed endpoint factories preserve request validation without a permissive dict body.
    def register(path, cls):
        def endpoint(case_id: str, payload, identity):
            allow(identity, case_id, write=True)
            if payload.case_id != case_id:
                raise DomainError('경로와 본문의 사건이 다릅니다.')
            # 작성자는 요청 본문이 아니라 인증된 사용자로 정한다.
            return svc.add(payload, actor=identity.id)
        endpoint.__annotations__ = {'case_id': str, 'payload': cls, 'identity': Identity}
        endpoint.__name__ = 'create_' + cls.__name__.lower()
        app.post('/cases/{case_id}/' + path, status_code=201)(endpoint)

    for path, cls in [('scopes', Scope), ('analysis-units', AnalysisUnit), ('inputs', Input),
                      ('assertions', Assertion), ('t-rows', TRow), ('s-rows', SRow),
                      ('discrepancies', Discrepancy), ('judgments', Judgment)]:
        register(path, cls)

    # These functions use explicit runtime annotations because the principal dependency
    # is local to this application factory.
    def guardrail(judgment_id, identity):
        j = svc.get(judgment_id, Judgment)
        allow(identity, j.case_id)
        return svc.guardrail(j.id)
    guardrail.__annotations__ = {'judgment_id': str, 'identity': Identity}
    app.post('/judgments/{judgment_id}/guardrail-checks')(guardrail)

    def review(judgment_id, payload, identity):
        j = svc.get(judgment_id, Judgment)
        allow(identity, j.case_id)
        return svc.review(judgment_id, payload, identity)
    review.__annotations__ = {'judgment_id': str, 'payload': ReviewRequest, 'identity': Identity}
    app.post('/judgments/{judgment_id}/reviews', status_code=201)(review)

    def reconciliation(case_id, payload, identity):
        allow(identity, case_id, write=True)
        if payload.case_id != case_id:
            raise DomainError('경로와 본문의 사건이 다릅니다.')
        svc.add(payload, actor=identity.id)
        return svc.run_result(payload.id)
    reconciliation.__annotations__ = {'case_id': str, 'payload': Reconciliation, 'identity': Identity}
    app.post('/cases/{case_id}/reconciliation-runs', status_code=201)(reconciliation)

    def get_reconciliation(run_id, identity):
        rec = svc.get(run_id, Reconciliation)
        allow(identity, rec.case_id)
        return svc.run_result(rec.id)
    get_reconciliation.__annotations__ = {'run_id': str, 'identity': Identity}
    app.get('/reconciliation-runs/{run_id}')(get_reconciliation)

    def summary(case_id, payload, identity):
        allow(identity, case_id)
        return svc.summary(case_id, payload.scope_id, payload.judgment_ids)
    summary.__annotations__ = {'case_id': str, 'payload': SummaryRequest, 'identity': Identity}
    app.post('/cases/{case_id}/summary-runs')(summary)

    def freeze(case_id, payload, identity):
        allow(identity, case_id)
        return svc.freeze_conclusion(case_id, payload.scope_id, payload.judgment_ids, identity, payload.purpose)
    freeze.__annotations__ = {'case_id': str, 'payload': FreezeRequest, 'identity': Identity}
    app.post('/cases/{case_id}/conclusion-snapshots', status_code=201)(freeze)

    def get_conclusion(conclusion_id, identity):
        snap = svc.get_conclusion(conclusion_id)
        allow(identity, snap.case_id)
        return snap
    get_conclusion.__annotations__ = {'conclusion_id': str, 'identity': Identity}
    app.get('/conclusion-snapshots/{conclusion_id}')(get_conclusion)
    return app
