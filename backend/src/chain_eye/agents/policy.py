"""Shared orchestration budgets used by graph declarations and runtime execution."""

RUN_BUDGET_SECONDS=600
MAX_MODEL_CALLS=12
MAX_NODE_RETRIES=2


def can_recover_interrupted_node(graph,node_id,record):
    """Decide whether restarting a persisted node can duplicate unsafe work."""
    if node_id is None:return True
    try:node=graph.require_node(node_id)
    except KeyError:return False
    if node.recoverability=='safe':return True
    completed_artifact={
        'finance':bool(record.get('calculation_ids')),
        'research':bool(record.get('claims')),
        'scenario':bool(record.get('scenario_ids')),
        'report':bool(record.get('report_ready')),
    }.get(node_id,False)
    # Scenario calculation and report persistence are idempotent, so an
    # interruption before their completion marker is also safe to retry.
    return completed_artifact or node_id in {'scenario','report'}
