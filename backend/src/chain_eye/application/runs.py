"""Persisted run orchestration with one SQLite-claiming worker."""
import json
import re
import threading
import time
from decimal import Decimal,InvalidOperation

from pydantic import ValidationError

from chain_eye.api.dto import ResumeRequest,RunCreate
from chain_eye.application.errors import AppError
from chain_eye.application.financials import FinancialService
from chain_eye.application.reports import ReportService
from chain_eye.application.run_manifest import (
    ExecutionManifestError,build_execution_manifest,manifest_sha256,resolve_execution_manifest,
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
from chain_eye.tools.registry import DEFAULT_TOOL_REGISTRY

RUN_BUDGET_SECONDS=600
MAX_MODEL_CALLS=12
MAX_NODE_RETRIES=2
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
        tool_registry=None,prompt_registry=None,skill_registry=None,
    ):
        self.repository=repository;self.llm=llm;self.clock=clock
        self.financials=FinancialService(repository);self.scenarios=ScenarioExecutionService(repository)
        self.reports=ReportService(repository)
        self.tool_registry=tool_registry or DEFAULT_TOOL_REGISTRY
        self.prompt_registry=prompt_registry or DEFAULT_PROMPT_REGISTRY
        self.skill_registry=skill_registry or DEFAULT_SKILL_REGISTRY
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
        config=getattr(self.llm,'public_config',{'provider':'test','model':'injected','response_format':'json_object'})
        try:
            skills=(self.financial_skill,self.research_skill,self.scenario_skill)
            if source is None:
                manifest=build_execution_manifest(self.claim_prompt,skills,self.tool_registry)
                manifest_hash=manifest_sha256(manifest)
            else:
                self._resolve_bindings(source)
                manifest=source['execution_manifest'];manifest_hash=source['execution_manifest_sha256']
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

    def _resolve_bindings(self,record):
        try:
            return resolve_execution_manifest(
                record.get('execution_manifest'),record.get('execution_manifest_sha256'),
                self.prompt_registry,self.skill_registry,self.tool_registry,
            )
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
            bindings=self._resolve_bindings(record)
            if record['mode']=='replay':self._execute_replay(record,bindings);return
            self._execute_live(record,started,bindings)
        except TypedProviderError as exc:
            self._finish_error(run_id,record,exc.code,str(exc),exc.retryable)
        except ValidationError as exc:
            self._finish_error(run_id,record,'MODEL_INVALID_RESPONSE',str(exc),False)
        except AppError as exc:
            self._finish_error(run_id,record,exc.code,exc.message,exc.retryable,exc.details)
        except Exception as exc:
            self._finish_error(run_id,record,'RUN_FAILED',str(exc),False)

    def _budget(self,started,record):
        if self.clock()-started>RUN_BUDGET_SECONDS:raise AppError('BUDGET_EXCEEDED','Run 已超过 10 分钟总预算',429)
        if record.get('model_calls',0)>=MAX_MODEL_CALLS:raise AppError('BUDGET_EXCEEDED','Run 已达到模型调用预算',429)

    def _node(self,record,node,status='started',details=None):
        record=self.repository.update_run(record['id'],current_node=node) or record
        self.repository.append_event(record['id'],'node_status',node,{'status':status,**(details or {})})
        return record

    def _execute_live(self,record,started,bindings):
        run_id=record['id'];request=RunCreate.model_validate(record['request'])
        financial_skill=bindings.skills['financial_diagnosis']
        research_skill=bindings.skills['evidence_bound_research']
        scenario_skill=bindings.skills['scenario_impact'];claim_prompt=bindings.prompt
        tools=RunTools(
            self.repository,self.financials,self.scenarios,run_id,
            record['dataset_id'],record['dataset_version'],registry=self.tool_registry,
            tool_specs=bindings.tools,
        )
        financial_tools=tools.for_skill(financial_skill)
        research_tools=tools.for_skill(research_skill)
        scenario_tools=tools.for_skill(scenario_skill)

        record=self._node(record,'plan',details={
            'plan':['extract','validate','finance','research','scenario_if_requested','verify','report'],
            'execution_manifest_sha256':bindings.sha256,
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
                {'name':spec.name,'version':spec.version,'spec_sha256':spec.spec_sha256}
                for spec in sorted(bindings.tools.values(),key=lambda item:item.name)
            ],
        })
        self._budget(started,record)

        record=self._node(record,'extract')
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
        self.repository.append_event(run_id,'file_access','extract',{'dataset_id':record['dataset_id'],'dataset_version':record['dataset_version'],'fact_count':len(facts)})

        record=self._node(record,'validate')
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
        self._budget(started,record)

        record=self._node(record,'finance')
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
        computed_calculation_ids=[item['id'] for item in calculations if item and item.get('status')=='computed']
        self._budget(started,record)

        record=self._node(record,'research')
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
                self._budget(started,record)
                calls=record.get('model_calls',0)+1
                record=self.repository.update_run(run_id,model_calls=calls,node_retries={**record.get('node_retries',{}),'research':attempt}) or record
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
                        {'timeout_seconds':60,'max_output_tokens':4000},
                    );break
                except TypedProviderError as exc:
                    self.repository.append_event(run_id,'llm_call','research',{
                        'status':'failed','provider':getattr(self.llm,'provider','unknown'),
                        'model':getattr(self.llm,'model','unknown'),'skill_id':research_skill.id,
                        'skill_version':research_skill.version,'skill_spec_sha256':research_skill.spec_sha256,
                        'prompt_id':claim_prompt.id,'prompt_version':claim_prompt.version,
                        'prompt_sha256':claim_prompt.sha256,
                        'attempt':attempt+1,'error':{'code':exc.code,'message':str(exc),'retryable':exc.retryable},
                    })
                    if not exc.retryable or attempt==MAX_NODE_RETRIES:raise
            raw_claims=generation.output.get('claims') if isinstance(generation.output,dict) else None
            if not isinstance(raw_claims,list) or not 1<=len(raw_claims)<=3:
                raise ModelInvalidResponse('model must return from one to three claims')
            candidate_claims=[Claim.model_validate(item).model_dump(mode='json') for item in raw_claims]
            record=self.repository.update_run(run_id,claims=candidate_claims) or record
            self.repository.append_event(run_id,'llm_call','research',{
                'status':'completed','provider':generation.provider,'model':generation.model,
                'skill_id':research_skill.id,'skill_version':research_skill.version,
                'skill_spec_sha256':research_skill.spec_sha256,
                'prompt_id':claim_prompt.id,'prompt_version':claim_prompt.version,
                'prompt_sha256':claim_prompt.sha256,
                'usage':generation.usage,'latency_ms':generation.latency_ms,
                'request_id':generation.request_id,'cost':generation.cost,'claim_count':len(candidate_claims),
            })
        self._budget(started,record)

        record=self._node(record,'scenario')
        scenario_ids=record.get('scenario_ids',[]);assumption_ids=[];question=request.question.casefold()
        price_impact=any(term in question for term in ('价格','price')) and any(term in question for term in ('影响','impact'))
        scenario_requested=bool(request.assumptions) or price_impact or any(term in question for term in SCENARIO_TERMS)
        if scenario_requested and request.assumptions is None:
            self.repository.update_run(run_id,status='waiting_review',current_node='scenario',missing_requirements=['scenario_assumptions'])
            self.repository.append_event(run_id,'node_status','scenario',{'status':'waiting_review','missing_requirements':['scenario_assumptions']})
            return
        if scenario_requested and not scenario_ids:
            latest_year=max(fact.period_end for fact in verified_segment_facts)
            latest=[fact for fact in verified_segment_facts if fact.period_end==latest_year]
            revenue=next(fact for fact in latest if fact.metric=='revenue');cost=next(fact for fact in latest if fact.metric=='cost_of_sales')
            scenario_request={
                'dataset_id':record['dataset_id'],'dataset_version':record['dataset_version'],
                'revenue_fact_id':revenue.id,'cost_fact_id':cost.id,'revenue_revision':revenue.revision,'cost_revision':cost.revision,
                'model_version':'static-gross-profit-v1','assumptions':request.assumptions.model_dump(mode='json'),
            }
            result=scenario_tools.call('compute_scenario',{'request':scenario_request})
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
        self._budget(started,record)

        record=self._node(record,'verify')
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
        self.repository.append_event(run_id,'node_status','verify',{
            'status':'support_checked','pending':sum(item.review_status=='pending' for item in checked),
            'insufficient':sum(item.review_status=='insufficient' for item in checked),
            'rejected':sum(item.review_status=='rejected' for item in checked),
        })
        self.repository.update_run(run_id,status='running',current_node='report',missing_requirements=[],error=None,claims=final_claims,report_ready=False)
        self.repository.append_event(run_id,'node_status','verify',{'status':'completed','claims':final_claims,'report_ready':False})
        self.reports.complete(run_id)

    def _execute_replay(self,record,bindings):
        source=self.repository.get_run_record(record['request']['replay_run_id'])
        if source is None:raise AppError('NOT_FOUND','回放源 Run 不存在',404)
        source_bindings=self._resolve_bindings(source)
        if source_bindings.sha256!=bindings.sha256:
            raise AppError('EXECUTION_VERSION_UNAVAILABLE','回放 Run 与源 Run 的执行版本清单不一致',409)
        self.repository.append_event(record['id'],'node_status','plan',{
            'status':'completed','mode':'replay','source_run_id':source['id'],
            'execution_manifest_sha256':bindings.sha256,
        })
        finalizing=source['status']=='completed'
        self.repository.update_run(
            record['id'],status='running' if finalizing else source['status'],current_node='report' if finalizing else 'verify',claims=source.get('claims',[]),
            calculation_ids=source.get('calculation_ids',[]),scenario_ids=source.get('scenario_ids',[]),
            assumption_ids=source.get('assumption_ids',[]),missing_requirements=[],error=source.get('error'),model_calls=0,
            report_ready=False,
        )
        self.repository.append_event(record['id'],'node_status','verify',{'status':source['status'],'mode':'replay','claims':source.get('claims',[]),'report_ready':False})
        if finalizing:self.reports.complete(record['id'])

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
