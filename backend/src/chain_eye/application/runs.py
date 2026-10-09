"""Persisted run orchestration with one SQLite-claiming worker."""
import json
import re
import threading
import time
from decimal import Decimal,InvalidOperation

from pydantic import ValidationError

from chain_eye.agents.graph import DEFAULT_AGENT_GRAPH,LEGACY_V2_AGENT_GRAPH
from chain_eye.agents.orchestrator import AgentOrchestrator,NodeResult
from chain_eye.agents.policy import MAX_MODEL_CALLS,MAX_NODE_RETRIES,RUN_BUDGET_SECONDS
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
from chain_eye.domain.contracts import Claim,ErrorBody
from chain_eye.domain.financials import FINANCIAL_METRIC_IDS
from chain_eye.domain.review import FactScopeError
from chain_eye.domain.scenario import IdempotencyConflictError
from chain_eye.ports.services import ModelInvalidResponse,TypedProviderError
from chain_eye.prompts.registry import DEFAULT_PROMPT_REGISTRY
from chain_eye.skills.registry import DEFAULT_SKILL_REGISTRY
from chain_eye.skills.runtime import SkillPolicyError,SkillRuntimeGuard
from chain_eye.tools.registry import DEFAULT_TOOL_REGISTRY

PROMPT_VERSION='r4-claims-v3'
SCENARIO_TERMS=('情景','敏感性','冲击','传导','假设','scenario','sensitivity','shock')
PROMPT_SPEC=DEFAULT_PROMPT_REGISTRY.require(PROMPT_VERSION,'claims')
SYSTEM_PROMPT=PROMPT_SPEC.content
CLAIM_RESPONSE_SCHEMA={
    'type':'object','required':['claims'],'additionalProperties':False,
    'properties':{'claims':{'type':'array','minItems':1,'maxItems':3,'items':Claim.model_json_schema()}},
}
NUMBER_PATTERN=re.compile(r'(?<![A-Za-z])[-+]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?%?')


def _numbers(text):
    values=[]
    for token in NUMBER_PATTERN.findall(text or ''):
        try:
            value=Decimal(token.rstrip('%').replace(',',''))
        except InvalidOperation:
            continue
        values.append(value/100 if token.endswith('%') else value)
    return values


def _support_checked(claim,evidence_by_id,calculation_by_id,fact_numbers_by_evidence=None):
    claim_numbers=_numbers(claim.text)
    if not claim_numbers:return True
    artifact_numbers=[]
    for evidence_id in claim.evidence_ids:
        evidence=evidence_by_id.get(evidence_id)
        if evidence is not None:artifact_numbers.extend(_numbers(evidence.excerpt))
        # 事实类 claim：被引用证据对应的事实规范值（元）与年度也作为合法来源，
        # 否则模型按事实规范值（元）复述、而证据摘录是原始千元（且无年份）时会误判。
        if fact_numbers_by_evidence is not None:
            artifact_numbers.extend(fact_numbers_by_evidence.get(evidence_id, ()))
    for calculation_id in claim.calculation_ids:
        calculation=calculation_by_id.get(calculation_id)
        if calculation is None or calculation.get('value') is None:continue
        artifact_numbers.append(Decimal(calculation['value']))
    return all(value in artifact_numbers for value in claim_numbers)


class RunExecutionService:
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

    def _run_plan(self,state):
        record=state.record;bindings=state.bindings
        financial_skill=bindings.skills['financial_diagnosis']
        research_skill=bindings.skills['evidence_bound_research']
        scenario_skill=bindings.skills['scenario_impact'];claim_prompt=bindings.prompt;model_binding=bindings.model
        self._budget(state.started,record)
        plan=(
            ['extract','validate','finance','research','scenario_if_requested','verify','report']
            if state.mode=='live' else ['replay_validate','replay_copy','report_if_completed']
        )
        return NodeResult(condition=f'mode == {state.mode}',details={
            'plan':plan,'mode':state.mode,
            'execution_manifest_sha256':bindings.sha256,
            'graph':{
                'id':bindings.graph.id,'version':bindings.graph.version,
                'spec_sha256':bindings.graph.spec_sha256,
            },
            'prompt_id':claim_prompt.id,'prompt_version':claim_prompt.version,
            'prompt_sha256':claim_prompt.sha256,
            'skills':[
                {
                    'id':skill.id,'version':skill.version,'spec_sha256':skill.spec_sha256,
                    'instructions_sha256':skill.instructions_sha256,
                }
                for skill in (financial_skill,research_skill,scenario_skill)
            ],
            'tools':[
                {
                    'name':spec.name,'version':spec.version,'spec_sha256':spec.spec_sha256,
                    'implementation_id':spec.implementation_id,
                    'implementation_sha256':spec.implementation_sha256,
                }
                for spec in sorted(bindings.tools.values(),key=lambda item:item.name)
            ],
            'model':{
                key:model_binding[key]
                for key in ('provider','model','adapter_version','endpoint','public_config_sha256')
            },
        })

    def _run_extract(self,state):
        record=state.record;request=state.request
        financial_skill=state.bindings.skills['financial_diagnosis']
        financial_session=self.skill_runtime.start(financial_skill,{
            'dataset_id':record['dataset_id'],'dataset_version':record['dataset_version'],
            'requested_metric_ids':list(FINANCIAL_METRIC_IDS),
        },state.run_deadline)
        financial_tools=state.artifacts['tools'].for_skill(financial_skill,financial_session.deadline)
        segment_fact_metrics=['revenue','cost_of_sales']
        group_fact_metrics=['revenue','cost_of_sales','inventory','accounts_receivable','parent_net_profit','parent_adjusted_net_profit']
        segment_facts=financial_tools.call('get_facts',{
            'dataset_id':record['dataset_id'],'dataset_version':record['dataset_version'],
            'metric_ids':segment_fact_metrics,'segment':request.segment,'period':None,
        })
        group_facts=financial_tools.call('get_facts',{
            'dataset_id':record['dataset_id'],'dataset_version':record['dataset_version'],
            'metric_ids':group_fact_metrics,'segment':'group','period':None,
        })
        facts=[*segment_facts,*group_facts]
        self.repository.append_event(state.run_id,'file_access','extract',{'dataset_id':record['dataset_id'],'dataset_version':record['dataset_version'],'fact_count':len(facts)})
        state.artifacts.update(
            financial_session=financial_session,financial_tools=financial_tools,
            segment_facts=segment_facts,group_facts=group_facts,facts=facts,
        )
        return NodeResult(condition='completed',details={'fact_count':len(facts)})

    def _run_validate(self,state):
        record=state.record;segment_facts=state.artifacts['segment_facts'];group_facts=state.artifacts['group_facts']
        required={'revenue','cost_of_sales'}
        dataset=self.repository.get_dataset(record['dataset_id'],record['dataset_version'])
        current={fact.metric for fact in segment_facts if fact.status=='verified' and fact.period_end.startswith(str(dataset.year))}
        if not required<=current:
            missing=sorted(required-current)
            raise AppError(
                'FACT_NOT_VERIFIED','当前不可变快照缺少研究与财务基线所需的已复核事实',409,
                details={'missing_metrics':missing,'action':'create_new_run_after_fact_review'},
            )
        verified_segment_facts=[fact for fact in segment_facts if fact.status=='verified']
        verified_group_facts=[fact for fact in group_facts if fact.status=='verified']
        state.artifacts.update(
            verified_segment_facts=verified_segment_facts,
            verified_group_facts=verified_group_facts,
        )
        self._budget(state.started,record)
        return NodeResult(condition='completed',details={
            'verified_segment_fact_count':len(verified_segment_facts),
            'verified_group_fact_count':len(verified_group_facts),
        })

    def _run_finance(self,state):
        record=state.record;run_id=state.run_id
        financial_tools=state.artifacts['financial_tools']
        financial_session=state.artifacts['financial_session']
        verified_segment_facts=state.artifacts['verified_segment_facts']
        verified_group_facts=state.artifacts['verified_group_facts']
        calculation_ids=record.get('calculation_ids',[])
        if not calculation_ids:
            segment_metrics=list(FINANCIAL_METRIC_IDS[:3]);group_metrics=list(FINANCIAL_METRIC_IDS[3:])
            calculations=financial_tools.call('compute_financials',{
                'fact_ids':[fact.id for fact in verified_segment_facts],
                'revisions':{fact.id:fact.revision for fact in verified_segment_facts},'metric_ids':segment_metrics,
            })
            calculations+=financial_tools.call('compute_financials',{
                'fact_ids':[fact.id for fact in verified_group_facts],
                'revisions':{fact.id:fact.revision for fact in verified_group_facts},'metric_ids':group_metrics,
            })
            calculation_ids=[item.id for item in calculations]
            record=self.repository.update_run(run_id,calculation_ids=calculation_ids) or record
            self.repository.append_event(run_id,'calculation','finance',{'calculation_ids':calculation_ids,'formula_ids':[item.formula_id for item in calculations]})
        calculations=[self.repository.get('calculations',item) for item in calculation_ids]
        financial_session.validate_output({'calculations':calculations})
        computed_calculation_ids=[item['id'] for item in calculations if item and item.get('status')=='computed']
        state.update_record(record)
        state.artifacts.update(
            calculation_ids=calculation_ids,calculations=calculations,
            computed_calculation_ids=computed_calculation_ids,
        )
        self._budget(state.started,record)
        return NodeResult(condition='completed',details={
            'calculation_ids':calculation_ids,'computed_count':len(computed_calculation_ids),
        })

    def _run_research(self,state):
        record=state.record;run_id=state.run_id;request=state.request
        research_skill=state.bindings.skills['evidence_bound_research']
        claim_prompt=state.bindings.prompt;model_binding=state.bindings.model
        tools=state.artifacts['tools'];calculations=state.artifacts['calculations']
        computed_calculation_ids=state.artifacts['computed_calculation_ids']
        verified_segment_facts=state.artifacts['verified_segment_facts']
        research_session=self.skill_runtime.start(research_skill,{
            'dataset_id':record['dataset_id'],'dataset_version':record['dataset_version'],
            'question':request.question,'verified_facts':verified_segment_facts,
        },state.run_deadline)
        research_tools=tools.for_skill(research_skill,research_session.deadline)
        candidate_claims=record.get('claims',[])
        evidence_ids=sorted({evidence_id for fact in verified_segment_facts for evidence_id in fact.evidence_ids})
        evidence=research_tools.call('get_evidence',{'evidence_ids':evidence_ids})
        searched=research_tools.call('search_documents',{
            'dataset_id':record['dataset_id'],'dataset_version':record['dataset_version'],
            'query':request.question,'filters':{},'top_k':8,
        })
        by_id={item.id:item for item in [*evidence,*searched]}
        if not candidate_claims:
            context={
                'facts':[fact.model_dump(mode='json') for fact in verified_segment_facts],
                'calculations':calculations,
                'documents':[{'id':item.id,'content':f'<document>{item.excerpt}</document>'} for item in by_id.values()],
                'allowed_evidence_ids':sorted(by_id),'allowed_calculation_ids':computed_calculation_ids,
            }
            generation=None
            for attempt in range(MAX_NODE_RETRIES+1):
                record=self._reserve_model_call(record,state.started,research_session,attempt)
                try:
                    messages=[
                        {'role':'system','content':claim_prompt.content},
                        {'role':'user','content':json.dumps({'question':request.question,'context':context},ensure_ascii=False,separators=(',',':'))},
                    ]
                    # The current provider contract intentionally exposes only the
                    # R4/R5 ``claims`` task; add a task schema and adapter support
                    # before reusing this research node for another task name.
                    generation=self.llm.generate(
                        'claims',claim_prompt.version,messages,CLAIM_RESPONSE_SCHEMA,
                        {'timeout_seconds':max(1,min(60,int(research_session.remaining_seconds()))),'max_output_tokens':4000},
                    );break
                except TypedProviderError as exc:
                    self.repository.append_event(run_id,'llm_call','research',{
                        'status':'failed','provider':model_binding['provider'],
                        'model':model_binding['model'],'adapter_version':model_binding['adapter_version'],
                        'endpoint':model_binding['endpoint'],'public_config_sha256':model_binding['public_config_sha256'],
                        'skill_id':research_skill.id,
                        'skill_version':research_skill.version,'skill_spec_sha256':research_skill.spec_sha256,
                        'prompt_id':claim_prompt.id,'prompt_version':claim_prompt.version,
                        'prompt_sha256':claim_prompt.sha256,
                        'attempt':attempt+1,'error':{'code':exc.code,'message':str(exc),'retryable':exc.retryable},
                    })
                    if not exc.retryable or attempt==MAX_NODE_RETRIES:raise
            if generation.provider!=model_binding['provider'] or generation.model!=model_binding['model']:
                details={
                    'expected_provider':model_binding['provider'],'expected_model':model_binding['model'],
                    'actual_provider':generation.provider,'actual_model':generation.model,
                }
                self.repository.append_event(run_id,'llm_call','research',{
                    'status':'failed','provider':generation.provider,'model':generation.model,
                    'adapter_version':model_binding['adapter_version'],'endpoint':model_binding['endpoint'],
                    'public_config_sha256':model_binding['public_config_sha256'],
                    'skill_id':research_skill.id,'skill_version':research_skill.version,
                    'skill_spec_sha256':research_skill.spec_sha256,
                    'prompt_id':claim_prompt.id,'prompt_version':claim_prompt.version,
                    'prompt_sha256':claim_prompt.sha256,'error':{
                        'code':'MODEL_PROVENANCE_MISMATCH',
                        'message':'model response provenance does not match the Run binding',
                        'retryable':False,'details':details,
                    },
                })
                raise AppError(
                    'MODEL_PROVENANCE_MISMATCH','模型响应来源与 Run 固化绑定不一致',409,
                    details=details,
                )
            raw_claims=generation.output.get('claims') if isinstance(generation.output,dict) else None
            if not isinstance(raw_claims,list) or not 1<=len(raw_claims)<=3:
                raise ModelInvalidResponse('model must return from one to three claims')
            candidate_claims=[Claim.model_validate(item).model_dump(mode='json') for item in raw_claims]
            record=self.repository.update_run(run_id,claims=candidate_claims) or record
            self.repository.append_event(run_id,'llm_call','research',{
                'status':'completed','provider':generation.provider,'model':generation.model,
                'adapter_version':model_binding['adapter_version'],'endpoint':model_binding['endpoint'],
                'public_config_sha256':model_binding['public_config_sha256'],
                'skill_id':research_skill.id,'skill_version':research_skill.version,
                'skill_spec_sha256':research_skill.spec_sha256,
                'prompt_id':claim_prompt.id,'prompt_version':claim_prompt.version,
                'prompt_sha256':claim_prompt.sha256,
                'usage':generation.usage,'latency_ms':generation.latency_ms,
                'request_id':generation.request_id,'cost':generation.cost,'claim_count':len(candidate_claims),
            })
        state.update_record(record)
        state.artifacts.update(
            research_session=research_session,research_tools=research_tools,
            candidate_claims=candidate_claims,evidence_by_id=by_id,
        )
        self._budget(state.started,record)
        return NodeResult(condition='completed',details={
            'claim_count':len(candidate_claims),'evidence_count':len(by_id),
        })

    def _run_scenario(self,state):
        record=state.record;run_id=state.run_id;request=state.request
        scenario_skill=state.bindings.skills['scenario_impact']
        verified_segment_facts=state.artifacts['verified_segment_facts']
        tools=state.artifacts['tools']
        candidate_claims=state.artifacts['candidate_claims']
        calculation_ids=state.artifacts['calculation_ids']
        computed_calculation_ids=state.artifacts['computed_calculation_ids']
        scenario_ids=record.get('scenario_ids',[]);assumption_ids=[];question=request.question.casefold()
        price_impact=any(term in question for term in ('价格','price')) and any(term in question for term in ('影响','impact'))
        scenario_requested=bool(request.assumptions) or price_impact or any(term in question for term in SCENARIO_TERMS)
        if scenario_requested and request.assumptions is None:
            state.update_record(self.repository.update_run(
                run_id,status='waiting_review',current_node='scenario',
                missing_requirements=['scenario_assumptions'],
            ))
            return NodeResult(
                terminal=True,status='waiting_review',
                details={'missing_requirements':['scenario_assumptions']},
            )
        if scenario_requested and not scenario_ids:
            latest_year=max(fact.period_end for fact in verified_segment_facts)
            latest=[fact for fact in verified_segment_facts if fact.period_end==latest_year]
            revenue=next(fact for fact in latest if fact.metric=='revenue');cost=next(fact for fact in latest if fact.metric=='cost_of_sales')
            scenario_request={
                'dataset_id':record['dataset_id'],'dataset_version':record['dataset_version'],
                'revenue_fact_id':revenue.id,'cost_fact_id':cost.id,'revenue_revision':revenue.revision,'cost_revision':cost.revision,
                'model_version':'static-gross-profit-v1','assumptions':request.assumptions.model_dump(mode='json'),
            }
            scenario_session=self.skill_runtime.start(
                scenario_skill,{'request':scenario_request},state.run_deadline,
            )
            scenario_tools=tools.for_skill(scenario_skill,scenario_session.deadline)
            result=scenario_tools.call('compute_scenario',{'request':scenario_request})
            scenario_session.validate_output({'result':result})
            scenario_ids=[result.scenario_id];assumption_ids=[result.assumption_id]
            calculation_ids=[*calculation_ids,*result.calculation_ids]
            computed_calculation_ids=[*computed_calculation_ids,*result.calculation_ids]
            scenario_claim=Claim(
                id=f'scenario-{result.scenario_id}',kind='calculation',
                text=(
                    f'在已确认假设下，情景毛利为 {result.outputs.gross_profit} CNY，'
                    f'情景毛利率为 {result.outputs.gross_margin}，毛利变化为 '
                    f'{result.outputs.delta_gross_profit} CNY，毛利率变化为 '
                    f'{result.outputs.delta_gross_margin_pp} 个百分点。'
                ),
                evidence_ids=[],calculation_ids=result.calculation_ids,
                assumption_ids=[result.assumption_id],counter_evidence_ids=[],
                limitations=result.limitations,review_status='pending',
            ).model_dump(mode='json')
            candidate_claims=[*candidate_claims,scenario_claim]
            record=self.repository.update_run(
                run_id,scenario_ids=scenario_ids,calculation_ids=calculation_ids,
                assumption_ids=assumption_ids,claims=candidate_claims,
            ) or record
        else:assumption_ids=record.get('assumption_ids',[])
        state.update_record(record)
        state.artifacts.update(
            scenario_ids=scenario_ids,assumption_ids=assumption_ids,
            candidate_claims=candidate_claims,calculation_ids=calculation_ids,
            computed_calculation_ids=computed_calculation_ids,
        )
        self._budget(state.started,record)
        return NodeResult(condition='completed_or_skipped',details={
            'requested':scenario_requested,'scenario_ids':scenario_ids,
            'assumption_ids':assumption_ids,
        })

    def _run_verify(self,state):
        run_id=state.run_id
        research_tools=state.artifacts['research_tools']
        research_session=state.artifacts['research_session']
        candidate_claims=state.artifacts['candidate_claims']
        computed_calculation_ids=state.artifacts['computed_calculation_ids']
        assumption_ids=state.artifacts['assumption_ids']
        by_id=state.artifacts['evidence_by_id']
        verified_segment_facts=state.artifacts['verified_segment_facts']
        validated=research_tools.call('validate_claims',{
            'claims':candidate_claims,'allowed_evidence_ids':sorted(by_id),
            'allowed_calculation_ids':computed_calculation_ids,'allowed_assumption_ids':assumption_ids,
        })
        calculation_by_id={item['id']:item for item in (self.repository.get('calculations',item_id) for item_id in computed_calculation_ids) if item}
        fact_numbers_by_evidence={}
        for fact in verified_segment_facts:
            numbers=[Decimal(fact.value)]
            if fact.period_end:numbers.append(Decimal(fact.period_end[:4]))
            for evidence_id in fact.evidence_ids:
                fact_numbers_by_evidence.setdefault(evidence_id, []).extend(numbers)
        checked=[]
        for claim in validated:
            if claim.review_status=='pending' and not _support_checked(claim,by_id,calculation_by_id,fact_numbers_by_evidence):
                claim=claim.model_copy(update={'review_status':'insufficient'})
            checked.append(claim)
        final_claims=[item.model_dump(mode='json') for item in checked]
        if not final_claims:raise ModelInvalidResponse('run produced no claims')
        research_session.validate_output({'claims':final_claims})
        state.update_record(self.repository.update_run(
            run_id,status='running',missing_requirements=[],error=None,
            claims=final_claims,report_ready=False,
        ))
        state.artifacts['final_claims']=final_claims
        return NodeResult(condition='completed',details={
            'claims':final_claims,'report_ready':False,
            'pending':sum(item.review_status=='pending' for item in checked),
            'insufficient':sum(item.review_status=='insufficient' for item in checked),
            'rejected':sum(item.review_status=='rejected' for item in checked),
        })

    def _run_replay_validate(self,state):
        source=self.repository.get_run_record(state.request.replay_run_id)
        if source is None:raise AppError('NOT_FOUND','回放源 Run 不存在',404)
        source_bindings=self._resolve_bindings(source,verify_current_model=False)
        if source_bindings.sha256!=state.bindings.sha256:
            raise AppError('EXECUTION_VERSION_UNAVAILABLE','回放 Run 与源 Run 的执行版本清单不一致',409)
        state.artifacts['source']=source
        return NodeResult(condition='completed',details={'source_run_id':source['id']})

    def _run_replay_copy(self,state):
        source=state.artifacts['source']
        finalizing=source['status']=='completed'
        state.update_record(self.repository.update_run(
            state.run_id,status='running' if finalizing else source['status'],claims=source.get('claims',[]),
            calculation_ids=source.get('calculation_ids',[]),scenario_ids=source.get('scenario_ids',[]),
            assumption_ids=source.get('assumption_ids',[]),missing_requirements=[],error=source.get('error'),model_calls=0,
            report_ready=False,
        ))
        state.artifacts.update(
            final_claims=source.get('claims',[]),
            calculation_ids=source.get('calculation_ids',[]),
            scenario_ids=source.get('scenario_ids',[]),
            assumption_ids=source.get('assumption_ids',[]),
        )
        return NodeResult(
            condition='source completed' if finalizing else None,terminal=not finalizing,
            status='completed' if finalizing else source['status'],
            details={'source_run_id':source['id'],'source_status':source['status'],'model_calls':0},
        )

    def _run_report(self,state):
        self.reports.complete(state.run_id)
        state.update_record(self.repository.get_run_record(state.run_id))
        return NodeResult(terminal=True,details={'report_ready':True})

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
