"""R5 report assembly from one immutable, evidence-bound Run snapshot."""
import hashlib
from datetime import datetime,timezone

from pydantic import ValidationError

from chain_eye.api.dto import Report
from chain_eye.application.errors import AppError
from chain_eye.domain.contracts import AssumptionRecord,Calculation,Claim,ScenarioResult

REPORTABLE_CLAIM_STATUSES=frozenset({'pending','supported'})
SEGMENT_LABELS={'power_battery':'动力电池','energy_storage':'储能电池'}


def _unique(values):
    return list(dict.fromkeys(value for value in values if value))


class ReportService:
    def __init__(self,repository,clock=None):
        self.repository=repository
        self.clock=clock or (lambda:datetime.now(timezone.utc))

    def get_or_build(self,run_id):
        return self._get_or_build(run_id,False)

    def complete(self,run_id):
        """Atomically persist the report and move a running report node to completed."""
        return self._get_or_build(run_id,True)

    def _get_or_build(self,run_id,complete_run):
        existing=self.repository.get_report(run_id)
        if existing is not None:return existing
        record=self.repository.get_run_record(run_id)
        if record is None:raise AppError('NOT_FOUND','Run 不存在',404)
        expected_status='running' if complete_run else 'completed'
        if record['status']!=expected_status or (complete_run and record.get('current_node')!='report'):
            raise AppError(
                'REPORT_NOT_READY','仅已完成的 Run 可以生成报告',409,
                details={'run_status':record['status']},
            )
        claims=[self._validate_contract(Claim,item,'claim_contract',item.get('id','unknown') if isinstance(item,dict) else 'unknown') for item in record.get('claims',[])]
        calculations=[]
        for calculation_id in record.get('calculation_ids',[]):
            raw=self.repository.get('calculations',calculation_id)
            if raw is None:self._invalid('calculation',calculation_id)
            calculations.append(self._validate_contract(Calculation,raw,'calculation_contract',calculation_id))
        report=self.build(record,claims,calculations)
        digest=hashlib.sha256(report.model_dump_json().encode('utf-8')).hexdigest()
        saved,_=self.repository.save_report(report,{
            'status':'completed','report_ready':True,'formats':['json','markdown','pdf'],
            'report_sha256':digest,'claim_count':len(report.claims),
            'calculation_count':len(report.calculations),'evidence_count':len(report.evidence),
        },complete_run=complete_run)
        return saved

    @staticmethod
    def _invalid(kind,reference):
        raise AppError(
            'REPORT_INVALID_REFERENCE','Run 产物包含无法在绑定快照内解析的引用',409,
            details={'kind':kind,'reference':reference},
        )

    def _validate_contract(self,model,value,kind,reference):
        try:return model.model_validate(value)
        except ValidationError:self._invalid(kind,reference)

    def build(self,run_snapshot,claims,calculations):
        """Build the frozen Report DTO from one completed Run artifact snapshot."""
        record=run_snapshot
        dataset=self.repository.get_dataset(record['dataset_id'],record['dataset_version'])
        if dataset is None:self._invalid('dataset',f"{record['dataset_id']}@{record['dataset_version']}")

        snapshot_facts=self.repository.facts(record['dataset_id'],record['dataset_version'])
        fact_by_id={fact.id:fact for fact in snapshot_facts}
        evidence_items=self.repository.evidence_for_snapshot(record['dataset_id'],record['dataset_version'])
        evidence_by_id={item.id:item for item in evidence_items}

        calculation_ids=[item.id for item in calculations]
        if calculation_ids!=record.get('calculation_ids',[]):
            self._invalid('calculation_set',','.join(calculation_ids))
        calculation_by_id={}
        referenced_fact_ids=set();calculation_fact_ids=set()
        for calculation in calculations:
            for fact_id,revision in calculation.input_revisions.items():
                fact=fact_by_id.get(fact_id)
                if fact is None or fact.revision!=revision:self._invalid('fact_revision',f'{fact_id}@{revision}')
                referenced_fact_ids.add(fact_id);calculation_fact_ids.add(fact_id)
            calculation_by_id[calculation.id]=calculation

        scenarios=[];assumption_by_id={}
        for scenario_id in record.get('scenario_ids',[]):
            raw=self.repository.get('scenarios',scenario_id)
            if raw is None:self._invalid('scenario',scenario_id)
            scenario=self._validate_contract(ScenarioResult,raw,'scenario_contract',scenario_id)
            if scenario.dataset_id!=record['dataset_id'] or scenario.dataset_version!=record['dataset_version']:
                self._invalid('scenario_snapshot',scenario_id)
            if set(scenario.input_revisions)!={scenario.revenue_fact_id,scenario.cost_fact_id}:
                self._invalid('scenario_fact_set',scenario_id)
            if not set(scenario.calculation_ids)<=set(calculation_by_id):self._invalid('scenario_calculation',scenario_id)
            for fact_id,revision in scenario.input_revisions.items():
                fact=fact_by_id.get(fact_id)
                if fact is None or fact.revision!=revision:self._invalid('scenario_fact_revision',f'{fact_id}@{revision}')
                referenced_fact_ids.add(fact_id)
            assumption=AssumptionRecord(id=scenario.assumption_id,values=scenario.assumptions)
            prior=assumption_by_id.get(assumption.id)
            if prior is not None and prior!=assumption:self._invalid('assumption_collision',assumption.id)
            assumption_by_id[assumption.id]=assumption;scenarios.append(scenario)

        run_assumptions=set(record.get('assumption_ids',[]))
        if run_assumptions!=set(assumption_by_id):
            missing=sorted(run_assumptions-set(assumption_by_id)) or sorted(set(assumption_by_id)-run_assumptions)
            self._invalid('assumption',missing[0])

        all_claims=[self._validate_contract(Claim,item,'claim_contract',getattr(item,'id','unknown')) for item in claims]
        claims=[claim for claim in all_claims if claim.review_status in REPORTABLE_CLAIM_STATUSES]
        claim_evidence_ids=set();claim_calculation_ids=set();claim_assumption_ids=set()
        for claim in claims:
            claim_evidence_ids.update(claim.evidence_ids);claim_evidence_ids.update(claim.counter_evidence_ids)
            claim_calculation_ids.update(claim.calculation_ids);claim_assumption_ids.update(claim.assumption_ids)
        for evidence_id in claim_evidence_ids:
            if evidence_id not in evidence_by_id:self._invalid('claim_evidence',evidence_id)
        for calculation_id in claim_calculation_ids:
            if calculation_id not in calculation_by_id:self._invalid('claim_calculation',calculation_id)
        for assumption_id in claim_assumption_ids:
            if assumption_id not in assumption_by_id:self._invalid('claim_assumption',assumption_id)

        for fact in snapshot_facts:
            if set(fact.evidence_ids)&claim_evidence_ids:referenced_fact_ids.add(fact.id)
        facts=sorted(
            (fact for fact in snapshot_facts if fact.id in referenced_fact_ids),
            key=lambda fact:(fact.segment,fact.period_end,fact.metric,fact.id),
        )

        evidence_ids=set(claim_evidence_ids)
        for fact in facts:evidence_ids.update(fact.evidence_ids)
        for assumption in assumption_by_id.values():evidence_ids.update(assumption.values.evidence_ids)
        for evidence_id in evidence_ids:
            if evidence_id not in evidence_by_id:self._invalid('evidence',evidence_id)
        evidence=[evidence_by_id[item] for item in sorted(evidence_ids)]

        if not (facts or calculations or claims or scenarios):
            raise AppError('REPORT_EMPTY','Run 没有可生成报告的已校验产物',409)

        limitations=[f"报告绑定数据快照 {record['dataset_id']}@{record['dataset_version']}，不会跟随最新事实静默变化。"]
        if record['mode']=='replay':
            limitations.append(f'本报告来自回放 Run；数字和引用复用源 Run {record["request"]["replay_run_id"]}，不承诺模型逐字复现。')
        if any(claim.review_status=='pending' for claim in claims):limitations.append('pending Claim 已通过引用存在性与数字对照，关键结论仍需人工支持性复核。')
        excluded_insufficient=sum(claim.review_status=='insufficient' for claim in all_claims)
        excluded_rejected=sum(claim.review_status=='rejected' for claim in all_claims)
        if excluded_insufficient:limitations.append(f'已从正文排除 {excluded_insufficient} 条证据不足 Claim。')
        if excluded_rejected:limitations.append(f'已从正文排除 {excluded_rejected} 条引用不合法 Claim。')
        for calculation in calculations:
            if calculation.status=='not_computable':limitations.append(f'{calculation.formula_id} 不可计算：{calculation.reason}')
        for claim in claims:limitations.extend(claim.limitations)
        for scenario in scenarios:limitations.extend(scenario.limitations)
        current=self.repository.get_dataset(record['dataset_id'])
        if current is not None and current.version!=record['dataset_version']:
            limitations.append(f'当前数据包已更新到版本 {current.version}；本报告仍使用版本 {record["dataset_version"]}。')

        artifact_segments={fact.segment for fact in facts if fact.id in calculation_fact_ids and fact.segment!='group'}
        segment=next(iter(artifact_segments)) if len(artifact_segments)==1 else record['request']['segment']
        return Report(
            run_id=record['id'],dataset_id=record['dataset_id'],dataset_version=record['dataset_version'],
            mode=record['mode'],title=f'{dataset.name}｜{SEGMENT_LABELS[segment]}研究简报',
            facts=facts,calculations=calculations,claims=claims,scenarios=scenarios,
            assumptions=[assumption_by_id[item] for item in sorted(assumption_by_id)],
            evidence=evidence,limitations=_unique(limitations),generated_at=self.clock().isoformat(),
        )
