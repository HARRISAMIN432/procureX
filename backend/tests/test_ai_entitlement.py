from collections.abc import Sequence
from typing import cast
from uuid import UUID

import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.sql import Select

from app.auth.context import RequestContext
from app.models.commercial import OrganizationSubscription
from app.services.evaluation_analysis import _check_monthly_ai_limit
from app.services.evaluations import EvaluationConflictError


class ScalarSession:
    def __init__(self, values: Sequence[object]) -> None:
        self.values = iter(values)
        self.statements: list[Select[tuple[object, ...]]] = []

    async def scalar(self, statement: Select[tuple[object, ...]]) -> object:
        self.statements.append(statement)
        return next(self.values)


def context_with_results(*values: object) -> tuple[RequestContext, ScalarSession]:
    session = ScalarSession(values)
    context = RequestContext(
        organization_id=UUID(int=1),
        user_id=UUID(int=2),
        membership_id=UUID(int=3),
        permissions=frozenset(),
        session=cast(AsyncSession, session),
    )
    return context, session


@pytest.mark.parametrize("used,allowed", [(24, True), (25, False), (26, False)])
async def test_monthly_ai_limit_is_enforced_before_queuing(used: int, allowed: bool) -> None:
    subscription = OrganizationSubscription(
        organization_id=UUID(int=1), ai_run_limit_monthly=25
    )
    context, session = context_with_results(subscription, used)

    if allowed:
        await _check_monthly_ai_limit(context)
    else:
        with pytest.raises(EvaluationConflictError, match="Monthly AI analysis limit"):
            await _check_monthly_ai_limit(context)

    assert len(session.statements) == 2
    assert session.statements[0]._for_update_arg is not None


async def test_ai_is_unavailable_without_an_entitlement() -> None:
    context, session = context_with_results(None)

    with pytest.raises(EvaluationConflictError, match="AI entitlement is not configured"):
        await _check_monthly_ai_limit(context)

    assert len(session.statements) == 1
