"""Read-only Run handlers exposed through the shared ToolRegistry."""

from chain_eye.tools.spec import ToolFailure


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
        'items':items,'next_after_seq':next_after_seq,'has_more':has_more,
    }


def get_report(context,run_id):
    record=_bound_run(context,run_id)
    report=context.repository.get_report(run_id)
    if report is None:
        status=record.get('status','unknown')
        raise ToolFailure(f'report is not available for run status: {status}')
    context.check_budget()
    return report
