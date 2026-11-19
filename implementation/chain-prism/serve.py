"""Optional local server: set tokens outside source code before launching."""
import os

from chain_prism.api import create_app
from chain_prism.core import Store
from chain_prism.models import Principal

analyst_token = os.environ.get('PRISM_ANALYST_TOKEN')
reviewer_token = os.environ.get('PRISM_REVIEWER_TOKEN')
if not analyst_token or not reviewer_token or analyst_token == reviewer_token:
    raise RuntimeError('서로 다른 PRISM_ANALYST_TOKEN / PRISM_REVIEWER_TOKEN을 환경변수로 설정하세요.')
case_ids = tuple(value.strip() for value in os.environ.get('PRISM_CASE_IDS', 'DEMO').split(',') if value.strip())
app = create_app(Store(os.environ.get('PRISM_DB_PATH', 'chain_prism.sqlite')), {
    analyst_token: Principal(id='local-analyst', role='analyst', case_ids=case_ids),
    reviewer_token: Principal(id='local-reviewer', role='approver', case_ids=case_ids),
})
