"""Deterministic scenario handler."""
from chain_eye.domain.contracts import ScenarioRequest


def compute_scenario(context,request):
    parsed=ScenarioRequest.model_validate(request)
    context.check_snapshot(parsed.dataset_id,parsed.dataset_version);context.check_budget()
    return context.scenario_service.execute(parsed,f'run-{context.run_id}')
