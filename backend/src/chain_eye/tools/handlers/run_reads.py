"""Read-only Run handlers exposed through the shared ToolRegistry."""

from chain_eye.tools.spec import ToolFailure


PUBLIC_PAYLOAD_FIELDS={
    'file_access':frozenset({'dataset_id','dataset_version','fact_count'}),
    'calculation':frozenset({'calculation_ids','formula_ids'}),
    'report_generated':frozenset({
        'status','report_ready','formats','report_sha256','claim_count','calculation_count','evidence_count',
    }),
    'error':frozenset({'status','error'}),
    'llm_call':frozenset({
        'status','provider','model','adapter_version','endpoint','public_config_sha256',
        'model_implementation_id','model_implementation_sha256','skill_id','skill_version',
        'skill_spec_sha256','prompt_id','prompt_version','prompt_sha256','attempt','error',
        'usage','latency_ms','request_id','cost','claim_count',
    }),
    'tool_call':frozenset({
        'call_id','run_id','tool_name','tool_version','tool_spec_sha256','tool_implementation_id',
        'tool_implementation_sha256','skill_id','skill_version','skill_spec_sha256','input',
        'input_sha256','output','output_sha256','status','error','started_at','ended_at',
    }),
    'node_status':frozenset({
        'graph_id','graph_version','graph_spec_sha256','node_id','node_version','node_spec_sha256',
        'status','duration_ms','error_code','plan','mode','execution_manifest_sha256','graph','skills',
        'model','provenance','source_run_id','provenance_status','source_status','model_calls',
        'fact_count','verified_segment_fact_count','verified_group_fact_count','calculation_ids',
        'computed_count','claim_count','evidence_count','requested','scenario_ids','assumption_ids',
        'missing_requirements','claims','report_ready','pending','insufficient','rejected',
    }),
}


def _public_event(event):
    value=event.model_dump(mode='json')
    allowed=PUBLIC_PAYLOAD_FIELDS.get(value['type'],frozenset())
    payload=value.get('payload',{})
    value['payload']={key:item for key,item in payload.items() if key in allowed}
    if not allowed and payload:value['payload_omitted']=True
    return value


def _bound_run(context,run_id):
    context.check_budget()
    record=context.repository.get_run_record(run_id)
    if record is None or record.get('owner_id')!='local':raise ToolFailure('run does not exist')
    context.check_snapshot(record['dataset_id'],record['dataset_version'])
    return record


def get_run_trace(context,run_id,after_seq=0,limit=100):
    _bound_run(context,run_id)
    if not isinstance(after_seq,int) or isinstance(after_seq,bool) or after_seq<0:
        raise ToolFailure('after_seq must be a non-negative integer')
    if not isinstance(limit,int) or isinstance(limit,bool) or not 1<=limit<=200:
        raise ToolFailure('limit must be an integer from 1 to 200')
    items,next_after_seq,has_more=context.repository.list_run_events(run_id,after_seq,limit)
    context.check_budget()
    return {
        'run_id':run_id,'dataset_id':context.dataset_id,'dataset_version':context.dataset_version,
        'items':[_public_event(item) for item in items],
        'next_after_seq':next_after_seq,'has_more':has_more,
    }


def get_report(context,run_id):
    record=_bound_run(context,run_id)
    report=context.repository.get_report(run_id)
    if report is None:
        status=record.get('status','unknown')
        raise ToolFailure(f'report is not available for run status: {status}')
    context.check_budget()
    return report
