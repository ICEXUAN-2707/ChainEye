"""Local, read-only ChainEye MCP server over stdio."""
from typing import Any

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ResourceError,ToolError
from mcp.types import ToolAnnotations

from chain_eye.mcp.context import build_repository,run_context,snapshot_context
from chain_eye.mcp.serialization import MCPSerializationError,bounded_json,bounded_value
from chain_eye.prompts.registry import DEFAULT_PROMPT_REGISTRY
from chain_eye.skills.registry import DEFAULT_SKILL_REGISTRY,SkillRegistryError
from chain_eye.tools.registry import DEFAULT_TOOL_REGISTRY,MCP_TOOL_NAMES
from chain_eye.tools.spec import ToolFailure

READ_ONLY=ToolAnnotations(readOnlyHint=True,destructiveHint=False,idempotentHint=True,openWorldHint=False)


def _tool_call(registry,name,arguments,context):
    try:return bounded_value(registry.call(name,arguments,context,caller='mcp'))
    except (ToolFailure,MCPSerializationError) as exc:raise ToolError(str(exc)) from exc
    except Exception as exc:raise ToolError('ChainEye data access failed') from exc


def _tool_context(callback):
    try:return callback()
    except ToolFailure as exc:raise ToolError(str(exc)) from exc
    except Exception as exc:raise ToolError('ChainEye context is unavailable') from exc


def _bounded_ids(values,name,required=False):
    if values is None and not required:return None
    if (
        not isinstance(values,list) or not int(required)<=len(values)<=50
        or not all(isinstance(item,str) and item and len(item)<=128 for item in values)
    ):
        minimum='1' if required else '0'
        raise ToolError(f'{name} must contain {minimum} to 50 identifiers of at most 128 characters')
    return values


def _resource_call(callback):
    try:return bounded_json(callback())
    except (ToolFailure,SkillRegistryError,MCPSerializationError) as exc:raise ResourceError(str(exc)) from exc
    except Exception as exc:raise ResourceError('ChainEye resource is unavailable') from exc


def _skill_metadata(skill):
    return {
        'id':skill.id,'version':skill.version,'description':skill.description,
        'instructions_sha256':skill.instructions_sha256,'spec_sha256':skill.spec_sha256,
        'allowed_tools':sorted(skill.allowed_tools),'prompt_version':skill.prompt_version,
        'input_requirements':list(skill.input_requirements),
        'output_constraints':list(skill.output_constraints),
        'input_contract':skill.input_contract,'output_contract':skill.output_contract,
        'timeout_seconds':skill.timeout_seconds,'max_model_calls':skill.max_model_calls,
    }


def _dataset_value(repository,dataset_id,dataset_version):
    snapshot_context(repository,dataset_id,dataset_version)
    return repository.get_dataset(dataset_id,dataset_version)


def create_server(repository=None,db_path=None,seed=True,tool_registry=None,prompt_registry=None,skill_registry=None):
    repo=repository or build_repository(db_path,seed)
    tools=tool_registry or DEFAULT_TOOL_REGISTRY
    prompts=prompt_registry or DEFAULT_PROMPT_REGISTRY
    skills=skill_registry or DEFAULT_SKILL_REGISTRY
    for name in MCP_TOOL_NAMES:
        spec=tools.require(name)
        if 'mcp' not in spec.allowed_callers or spec.side_effect!='read':
            raise RuntimeError(f'invalid MCP tool policy: {name}')
    server=MCPServer(
        'chain-eye',title='ChainEye Evidence Research',version='0.1.0',
        instructions='Read-only access to versioned ChainEye datasets, evidence, traces, reports and registry metadata.',
        log_level='ERROR',
    )

    @server.tool(name='get_facts',description=tools.require('get_facts').description,annotations=READ_ONLY,structured_output=True)
    def mcp_get_facts(dataset_id:str,dataset_version:int,metric_ids:list[str]|None=None,segment:str|None=None,period:str|None=None)->dict[str,Any]:
        metric_ids=_bounded_ids(metric_ids,'metric_ids')
        context=_tool_context(lambda:snapshot_context(repo,dataset_id,dataset_version))
        items=_tool_call(tools,'get_facts',{
            'dataset_id':dataset_id,'dataset_version':dataset_version,'metric_ids':metric_ids,
            'segment':segment,'period':period,
        },context)
        return {'dataset_id':dataset_id,'dataset_version':dataset_version,'items':items}

    @server.tool(name='get_evidence',description=tools.require('get_evidence').description,annotations=READ_ONLY,structured_output=True)
    def mcp_get_evidence(dataset_id:str,dataset_version:int,evidence_ids:list[str])->dict[str,Any]:
        evidence_ids=_bounded_ids(evidence_ids,'evidence_ids',True)
        context=_tool_context(lambda:snapshot_context(repo,dataset_id,dataset_version))
        items=_tool_call(tools,'get_evidence',{'evidence_ids':evidence_ids},context)
        return {'dataset_id':dataset_id,'dataset_version':dataset_version,'items':items}

    @server.tool(name='search_documents',description=tools.require('search_documents').description,annotations=READ_ONLY,structured_output=True)
    def mcp_search_documents(dataset_id:str,dataset_version:int,query:str,filters:dict[str,Any]|None=None,top_k:int=8)->dict[str,Any]:
        if not query.strip() or len(query)>500:raise ToolError('query must contain 1 to 500 characters')
        context=_tool_context(lambda:snapshot_context(repo,dataset_id,dataset_version))
        items=_tool_call(tools,'search_documents',{
            'dataset_id':dataset_id,'dataset_version':dataset_version,'query':query,
            'filters':filters,'top_k':top_k,
        },context)
        return {'dataset_id':dataset_id,'dataset_version':dataset_version,'items':items}

    @server.tool(name='get_run_trace',description=tools.require('get_run_trace').description,annotations=READ_ONLY,structured_output=True)
    def mcp_get_run_trace(run_id:str,after_seq:int=0,limit:int=100)->dict[str,Any]:
        context=_tool_context(lambda:run_context(repo,run_id))
        return _tool_call(tools,'get_run_trace',{'run_id':run_id,'after_seq':after_seq,'limit':limit},context)

    @server.tool(name='get_report',description=tools.require('get_report').description,annotations=READ_ONLY,structured_output=True)
    def mcp_get_report(run_id:str)->dict[str,Any]:
        context=_tool_context(lambda:run_context(repo,run_id))
        return _tool_call(tools,'get_report',{'run_id':run_id},context)

    @server.resource('chain-eye://about',name='chain-eye-about',description='ChainEye MCP capability and safety metadata.',mime_type='application/json')
    def about()->str:
        return bounded_json({
            'name':'chain-eye','version':'0.1.0','transport':'stdio','mode':'read-only',
            'tools':sorted(MCP_TOOL_NAMES),'dataset_versions_required':True,
            'paid_model_calls':False,
        })

    @server.resource('chain-eye://datasets/{dataset_id}/versions/{dataset_version}',name='dataset-version',description='One immutable Dataset version.',mime_type='application/json')
    def dataset_resource(dataset_id:str,dataset_version:int)->str:
        return _resource_call(lambda:_dataset_value(repo,dataset_id,dataset_version))

    @server.resource('chain-eye://datasets/{dataset_id}/versions/{dataset_version}/evidence/{evidence_id}',name='evidence',description='Evidence scoped to one Dataset version.',mime_type='application/json')
    def evidence_resource(dataset_id:str,dataset_version:int,evidence_id:str)->str:
        def read():
            context=snapshot_context(repo,dataset_id,dataset_version)
            items=tools.call('get_evidence',{'evidence_ids':[evidence_id]},context,caller='mcp')
            return items[0]
        return _resource_call(read)

    @server.resource('chain-eye://runs/{run_id}/trace',name='run-trace',description='Bounded first page of an immutable Run trace.',mime_type='application/json')
    def trace_resource(run_id:str)->str:
        return _resource_call(lambda:tools.call(
            'get_run_trace',{'run_id':run_id,'after_seq':0,'limit':100},run_context(repo,run_id),caller='mcp',
        ))

    @server.resource('chain-eye://runs/{run_id}/report',name='run-report',description='An already persisted Run report.',mime_type='application/json')
    def report_resource(run_id:str)->str:
        return _resource_call(lambda:tools.call(
            'get_report',{'run_id':run_id},run_context(repo,run_id),caller='mcp',
        ))

    @server.resource('chain-eye://skills/{skill_id}/{version}',name='skill-metadata',description='Versioned runtime Skill metadata without model invocation.',mime_type='application/json')
    def skill_resource(skill_id:str,version:str)->str:
        return _resource_call(lambda:_skill_metadata(skills.require(skill_id,version)))

    @server.prompt(name='evidence_bound_research',title='Evidence-bound research',description='Return the versioned ChainEye research prompt without invoking a model.')
    def research_prompt(question:str,segment:str='power_battery')->str:
        if not question.strip() or len(question)>2000:raise ToolError('question must contain 1 to 2000 characters')
        if segment not in {'power_battery','energy_storage'}:raise ToolError('unsupported research segment')
        skill=skills.require('evidence_bound_research')
        prompt=prompts.require(skill.prompt_version,'claims')
        return (
            f'[prompt_id={prompt.id} prompt_version={prompt.version} prompt_sha256={prompt.sha256}]\n'
            f'[skill_id={skill.id} skill_version={skill.version} skill_spec_sha256={skill.spec_sha256}]\n'
            f'[segment={segment}]\n\n{prompt.content}\n\nUser research question: {question}'
        )

    return server


def main():
    create_server().run(transport='stdio')


if __name__=='__main__':main()
