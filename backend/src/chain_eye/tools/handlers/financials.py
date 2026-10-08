"""Deterministic financial calculation handler."""


def compute_financials(context,fact_ids,revisions,metric_ids):
    from chain_eye.tools.spec import ToolFailure
    if set(fact_ids)!=set(revisions):raise ToolFailure('fact revisions must match fact IDs')
    by_id={fact.id:fact for fact in context.repository.facts(context.dataset_id,context.dataset_version)}
    facts=[]
    for fact_id in fact_ids:
        fact=by_id.get(fact_id)
        if fact is None or fact.revision!=revisions[fact_id]:
            raise ToolFailure('fact revision is outside the run snapshot')
        facts.append(fact)
    context.check_budget()
    return context.financial_service.compute(facts,metric_ids)
