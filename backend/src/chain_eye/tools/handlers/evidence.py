"""Snapshot-scoped fact and evidence handlers."""
import re


def get_facts(context,dataset_id,dataset_version,metric_ids=None,segment=None,period=None):
    context.check_snapshot(dataset_id,dataset_version);context.check_budget()
    if metric_ids is not None and (
        not isinstance(metric_ids,list) or len(metric_ids)>50
        or not all(isinstance(item,str) and item for item in metric_ids)
    ):
        from chain_eye.tools.spec import ToolFailure
        raise ToolFailure('metric_ids must contain at most 50 non-empty strings')
    metrics=set(metric_ids or [])
    facts=context.repository.facts(context.dataset_id,context.dataset_version);context.check_budget()
    return [
        fact for fact in facts
        if (not metrics or fact.metric in metrics)
        and (segment is None or fact.segment==segment)
        and (period is None or fact.period_end==period or fact.period_end.startswith(f'{period}-'))
    ]


def _search_terms(query):
    terms=set()
    for token in re.findall(r'[A-Za-z0-9_]+|[\u4e00-\u9fff]+',query.casefold()):
        if re.fullmatch(r'[\u4e00-\u9fff]+',token):
            if len(token)==1:terms.add(token)
            else:terms.update(token[index:index+2] for index in range(len(token)-1))
        elif len(token)>1:terms.add(token)
    return terms


def search_documents(context,dataset_id,dataset_version,query,filters=None,top_k=8):
    context.check_snapshot(dataset_id,dataset_version)
    if not isinstance(query,str) or not query.strip() or len(query)>500:
        from chain_eye.tools.spec import ToolFailure
        raise ToolFailure('query must be a non-empty string of at most 500 characters')
    if not isinstance(top_k,int) or isinstance(top_k,bool) or not 1<=top_k<=8:
        from chain_eye.tools.spec import ToolFailure
        raise ToolFailure('top_k must be an integer from 1 to 8')
    filters=filters or {};unknown=set(filters)-{'source_ids','locator_kind','pdf_page'}
    if unknown:
        from chain_eye.tools.spec import ToolFailure
        raise ToolFailure(f'unsupported search filter: {sorted(unknown)[0]}')
    terms=_search_terms(query)
    evidence=context.repository.evidence_for_snapshot(context.dataset_id,context.dataset_version)
    scored=[]
    for item in evidence:
        context.check_budget()
        if filters.get('source_ids') and item.source_id not in filters['source_ids']:continue
        if filters.get('locator_kind') and item.locator_kind!=filters['locator_kind']:continue
        if filters.get('pdf_page') and item.pdf_page!=filters['pdf_page']:continue
        text=item.excerpt.casefold();score=sum(1 for term in terms if term in text)
        if score:scored.append((score,item.id,item))
    scored.sort(key=lambda row:(-row[0],row[1]))
    return [row[2] for row in scored[:top_k]]


def get_evidence(context,evidence_ids):
    context.check_budget()
    if (
        not isinstance(evidence_ids,list) or not 1<=len(evidence_ids)<=50
        or not all(isinstance(item,str) and item for item in evidence_ids)
    ):
        from chain_eye.tools.spec import ToolFailure
        raise ToolFailure('evidence_ids must contain 1 to 50 non-empty strings')
    allowed={item.id:item for item in context.repository.evidence_for_snapshot(context.dataset_id,context.dataset_version)}
    context.check_budget()
    missing=[item for item in evidence_ids if item not in allowed]
    if missing:
        from chain_eye.tools.spec import ToolFailure
        raise ToolFailure('evidence reference is outside the run snapshot')
    return [allowed[item] for item in evidence_ids]
