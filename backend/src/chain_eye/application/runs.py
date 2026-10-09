"""Persisted run orchestration with one SQLite-claiming worker."""
import threading
import time

from pydantic import ValidationError

from chain_eye.agents.graph import DEFAULT_AGENT_GRAPH,LEGACY_V2_AGENT_GRAPH
from chain_eye.agents.nodes import RunGraphNodeHandlers
from chain_eye.agents.orchestrator import AgentOrchestrator
from chain_eye.agents.policy import MAX_MODEL_CALLS,RUN_BUDGET_SECONDS
from chain_eye.agents.state import AgentState
from chain_eye.api.dto import ResumeRequest,RunCreate
from chain_eye.application.errors import AppError
from chain_eye.application.financials import FinancialService
from chain_eye.application.reports import ReportService
from chain_eye.application.run_manifest import (
    ExecutionManifestError,build_execution_manifest,manifest_sha256,normalize_model_config,
    resolve_execution_manifest,
)
from chain_eye.application.run_tools import RunTools
from chain_eye.application.scenarios import ScenarioExecutionService
from chain_eye.domain.contracts import ErrorBody
from chain_eye.domain.review import FactScopeError
from chain_eye.domain.scenario import IdempotencyConflictError
from chain_eye.ports.services import TypedProviderError
from chain_eye.prompts.registry import DEFAULT_PROMPT_REGISTRY
from chain_eye.skills.registry import DEFAULT_SKILL_REGISTRY
from chain_eye.skills.runtime import SkillPolicyError,SkillRuntimeGuard
from chain_eye.tools.registry import DEFAULT_TOOL_REGISTRY

PROMPT_VERSION='r4-claims-v3'
PROMPT_SPEC=DEFAULT_PROMPT_REGISTRY.require(PROMPT_VERSION,'claims')
SYSTEM_PROMPT=PROMPT_SPEC.content


class RunExecutionService(RunGraphNodeHandlers):
    def __init__(
        self,repository,llm,clock=time.monotonic,
        tool_registry=None,prompt_registry=None,skill_registry=None,graph=None,
    ):
        self.repository=repository;self.llm=llm;self.clock=clock
        try:self.model_config=normalize_model_config(getattr(self.llm,'public_config',None))
        except ExecutionManifestError as exc:raise ValueError('LLM adapter must expose a complete safe public_config') from exc
        self.financials=FinancialService(repository);self.scenarios=ScenarioExecutionService(repository)
        self.reports=ReportService(repository)
        self.skill_runtime=SkillRuntimeGuard(clock)
        self.tool_registry=tool_registry or DEFAULT_TOOL_REGISTRY
        self.prompt_registry=prompt_registry or DEFAULT_PROMPT_REGISTRY
        self.skill_registry=skill_registry or DEFAULT_SKILL_REGISTRY
        self.graph=graph or DEFAULT_AGENT_GRAPH
        self.financial_skill=self.skill_registry.require('financial_diagnosis')
        self.research_skill=self.skill_registry.require('evidence_bound_research')
        self.scenario_skill=self.skill_registry.require('scenario_impact')
        if self.research_skill.prompt_version is None:
            raise ValueError('evidence_bound_research must declare a prompt version')
        self.claim_prompt=self.prompt_registry.require(self.research_skill.prompt_version,'claims')
        for skill in (self.financial_skill,self.research_skill,self.scenario_skill):
            for tool_name in skill.allowed_tools:self.tool_registry.require(tool_name)

    def create(self,request:RunCreate,idempotency_key:str):
        return self.create_with_status(request,idempotency_key)[0]

    def create_with_status(self,request:RunCreate,idempotency_key:str):
        source=self._validate_replay(request) if request.mode=='replay' else None
        try:
            skills=(self.financial_skill,self.research_skill,self.scenario_skill)
            if source is None:
                config=self.model_config
                manifest=build_execution_manifest(self.graph,self.claim_prompt,skills,self.tool_registry,config)
                manifest_hash=manifest_sha256(manifest)
            else:
                source_bindings=self._resolve_bindings(source,verify_current_model=False)
                manifest=source['execution_manifest'];manifest_hash=source['execution_manifest_sha256']
                config=source_bindings.model['public_config']
            prompt_ref=manifest['prompt'];skill_refs=manifest['skills']
            return self.repository.create_run(
                request,idempotency_key,config,prompt_ref['version'],
                prompt_id=prompt_ref['id'],prompt_sha256=prompt_ref['sha256'],
                skill_versions=skill_refs,
                execution_manifest=manifest,execution_manifest_sha256=manifest_hash,
            )
        except IdempotencyConflictError as exc:
            raise AppError('INVALID_INPUT','Idempotency-Key 已用于不同请求',409,details={'reason':'IDEMPOTENCY_KEY_REUSED'}) from exc

    def _validate_replay(self,request):
        source=self.repository.get_run_record(request.replay_run_id)
        if source is None:raise AppError('NOT_FOUND','回放源 Run 不存在',404)
        if source.get('owner_id')!='local' or source['dataset_id']!=request.dataset_id or source['dataset_version']!=request.dataset_version:
            raise AppError('SCOPE_MISMATCH','回放源 Run 不属于相同数据快照',409)
        if source['status'] not in ('completed','partial'):
            raise AppError('INVALID_RUN_STATE','仅可回放已结束的 Run',409)
        if not source.get('execution_manifest') or not source.get('execution_manifest_sha256'):
            raise AppError(
                'EXECUTION_VERSION_UNAVAILABLE','回放源 Run 缺少不可变执行版本清单',409,
                details={'resource':'execution_manifest','source_run_id':source['id']},
            )
        return source

    def _resolve_bindings(self,record,verify_current_model):
        try:
            bindings=resolve_execution_manifest(
                record.get('execution_manifest'),record.get('execution_manifest_sha256'),
                self.graph,LEGACY_V2_AGENT_GRAPH,
                self.prompt_registry,self.skill_registry,self.tool_registry,
                self.model_config if verify_current_model else None,
            )
            if record.get('model_config')!=bindings.model['public_config']:
                raise ExecutionManifestError('persisted model configuration does not match the execution manifest')
            return bindings
        except ExecutionManifestError as exc:
            raise AppError(
                'EXECUTION_VERSION_UNAVAILABLE','Run 创建时绑定的 Agent 资源不可用或不一致',409,
                details={'reason':str(exc)},
            ) from exc

    def resume(self,run_id,request:ResumeRequest):
        current=self.repository.get_run_record(run_id)
        if current is None:raise AppError('NOT_FOUND','Run 不存在',404)
        if 'scenario_assumptions' in current.get('missing_requirements',[]) and request.assumptions is None:
            raise AppError('INVALID_INPUT','恢复情景 Run 必须提交已确认假设',422)
        try:
            record=self.repository.resume_run(
                run_id,request.expected_run_status,request.dataset_version,
                request.assumptions.model_dump(mode='json') if request.assumptions else None,
            )
        except ValueError as exc:
            raise AppError('RUN_STATE_CONFLICT','Run 状态已变化，不能恢复',409) from exc
        except FactScopeError as exc:
            raise AppError('SCOPE_MISMATCH','恢复请求与 Run 数据快照不一致',409) from exc
        return self.repository.get_run(run_id)

    def execute(self,run_id):
        record=self.repository.get_run_record(run_id)
        if record is None or record['status']!='running':return
        started=self.clock()
        try:
            bindings=self._resolve_bindings(record,verify_current_model=record['mode']!='replay')
            self._execute_graph(record,started,bindings)
        except TypedProviderError as exc:
            self._finish_error(run_id,record,exc.code,str(exc),exc.retryable)
        except ValidationError as exc:
            self._finish_error(run_id,record,'MODEL_INVALID_RESPONSE',str(exc),False)
        except AppError as exc:
            self._finish_error(run_id,record,exc.code,exc.message,exc.retryable,exc.details)
        except SkillPolicyError as exc:
            self._finish_error(run_id,record,exc.code,str(exc),False,exc.details)
        except Exception as exc:
            self._finish_error(run_id,record,'RUN_FAILED',str(exc),False)

    def _budget(self,started,record,session=None):
        if self.clock()-started>RUN_BUDGET_SECONDS:raise AppError('BUDGET_EXCEEDED','Run 已超过 10 分钟总预算',429)
        if record.get('model_calls',0)>=MAX_MODEL_CALLS:raise AppError('BUDGET_EXCEEDED','Run 已达到模型调用预算',429)
        if session is not None:session.check_budget()

    def _reserve_model_call(self,record,started,session,attempt):
        self._budget(started,record,session)
        skill=session.skill;skill_calls=dict(record.get('skill_model_calls',{}))
        used=skill_calls.get(skill.id,0)
        if used>=skill.max_model_calls:
            raise SkillPolicyError(
                'SKILL_BUDGET_EXCEEDED',f'skill model-call budget exceeded: {skill.id}',
                {'skill_id':skill.id,'skill_version':skill.version,'max_model_calls':skill.max_model_calls},
            )
        skill_calls[skill.id]=used+1
        return self.repository.update_run(
            record['id'],model_calls=record.get('model_calls',0)+1,skill_model_calls=skill_calls,
            node_retries={**record.get('node_retries',{}),'research':attempt},
        ) or record

    def _execute_graph(self,record,started,bindings):
        request=RunCreate.model_validate(record['request'])
        state=AgentState(
            run_id=record['id'],dataset_id=record['dataset_id'],
            dataset_version=record['dataset_version'],mode=record['mode'],request=request,
            record=record,bindings=bindings,started=started,
            run_deadline=started+RUN_BUDGET_SECONDS,
        )
        state.artifacts['tools']=RunTools(
            self.repository,self.financials,self.scenarios,state.run_id,
            state.dataset_id,state.dataset_version,clock=self.clock,registry=self.tool_registry,
            tool_specs=bindings.tools,
        )
        handlers={
            'plan':self._run_plan,'extract':self._run_extract,
            'validate':self._run_validate,'finance':self._run_finance,
            'research':self._run_research,'scenario':self._run_scenario,
            'verify':self._run_verify,'replay_validate':self._run_replay_validate,
            'replay_copy':self._run_replay_copy,'report':self._run_report,
        }
        AgentOrchestrator(bindings.graph,self.repository,self.clock).execute(state,handlers)

    def _finish_error(self,run_id,record,code,message,retryable,details=None):
        current=self.repository.get_run_record(run_id) or record
        status='partial' if current.get('calculation_ids') else 'failed'
        error=ErrorBody(code=code,message=message[:1000],details=details or {},retryable=retryable,request_id=run_id).model_dump(mode='json')
        self.repository.update_run(run_id,status=status,error=error,report_ready=False)
        self.repository.append_event(run_id,'error',current.get('current_node') or 'run',{'status':status,'error':error})


class RunWorker:
    """A single process-local worker; jobs are claimed atomically from SQLite."""
    def __init__(self,repository,service):
        self.repository=repository;self.service=service;self._wake=threading.Event();self._stop=threading.Event();self._thread=None

    def submit(self):
        if self._thread is None or not self._thread.is_alive():
            self.repository.recover_interrupted_runs()
            self._thread=threading.Thread(target=self._loop,name='chain-eye-run-worker',daemon=True);self._thread.start()
        self._wake.set()

    def _loop(self):
        while not self._stop.is_set():
            run_id=self.repository.claim_next_run()
            if run_id is not None:self.service.execute(run_id);continue
            self._wake.wait(0.5);self._wake.clear()

    def stop(self):
        self._stop.set();self._wake.set()
        if self._thread and self._thread.is_alive():self._thread.join(timeout=2)
