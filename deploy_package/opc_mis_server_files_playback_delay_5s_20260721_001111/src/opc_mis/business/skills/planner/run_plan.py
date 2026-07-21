"""Create Planner's bounded initial execution plan."""

from opc_mis.domain.enums import RunTaskType
from opc_mis.domain.planner_models import RunPlan

INITIAL_TASKS = (
    RunTaskType.FINANCE_ASSESSMENT,
    RunTaskType.OPERATIONS_ASSESSMENT,
    RunTaskType.INITIAL_RISK_SCAN,
)


def build_run_plan(blocked: bool) -> RunPlan:
    """Return an executable initial plan only when Planner readiness is not blocked."""
    if blocked:
        return RunPlan(
            parallel_initial_tasks=(),
            plan_reason=(
                "Initial assessment is deferred until Planner blocking data requests are resolved."
            ),
        )
    return RunPlan(
        parallel_initial_tasks=INITIAL_TASKS,
        plan_reason=(
            "Base case is valid. Finance Assessment, Operations Assessment, and Initial Risk "
            "Scan may start in parallel. Downstream routing belongs to the Orchestrator."
        ),
    )
