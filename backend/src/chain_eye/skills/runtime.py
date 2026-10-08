"""Machine-enforced input, output, and budget policies for runtime Skills."""
from dataclasses import dataclass

from chain_eye.domain.contracts import Claim


class SkillPolicyError(RuntimeError):
    def __init__(self,code,message,details=None):
        super().__init__(message);self.code=code;self.details=details or {}


def _mapping(value,label):
    if not isinstance(value,dict):raise SkillPolicyError('SKILL_INPUT_INVALID',f'{label} must be an object')
    return value


def _financial_input(payload):
    payload=_mapping(payload,'financial input')
    metrics=payload.get('requested_metric_ids')
    if not isinstance(payload.get('dataset_id'),str) or not payload['dataset_id']:
        raise SkillPolicyError('SKILL_INPUT_INVALID','financial input requires a dataset ID')
    if not isinstance(payload.get('dataset_version'),int) or isinstance(payload['dataset_version'],bool) or payload['dataset_version']<=0:
        raise SkillPolicyError('SKILL_INPUT_INVALID','financial input requires a positive dataset version')
    if not isinstance(metrics,list) or not metrics or not all(isinstance(item,str) and item for item in metrics):
        raise SkillPolicyError('SKILL_INPUT_INVALID','financial input requires metric IDs')


def _research_input(payload):
    payload=_mapping(payload,'research input');facts=payload.get('verified_facts')
    if not isinstance(payload.get('question'),str) or not payload['question'].strip():
        raise SkillPolicyError('SKILL_INPUT_INVALID','research input requires a question')
    if not isinstance(facts,list) or not facts or any(getattr(item,'status',None)!='verified' for item in facts):
        raise SkillPolicyError('SKILL_INPUT_INVALID','research input requires verified facts')
    if not isinstance(payload.get('dataset_version'),int) or isinstance(payload['dataset_version'],bool):
        raise SkillPolicyError('SKILL_INPUT_INVALID','research input requires a dataset version')


def _scenario_input(payload):
    payload=_mapping(payload,'scenario input');request=_mapping(payload.get('request'),'scenario request')
    assumptions=_mapping(request.get('assumptions'),'scenario assumptions')
    if assumptions.get('acknowledged') is not True:
        raise SkillPolicyError('SKILL_INPUT_INVALID','scenario assumptions must be acknowledged')
    for key in ('revenue_fact_id','cost_fact_id','revenue_revision','cost_revision'):
        if request.get(key) in (None,''):raise SkillPolicyError('SKILL_INPUT_INVALID',f'scenario input requires {key}')


def _calculation_output(payload):
    calculations=payload.get('calculations') if isinstance(payload,dict) else None
    if not isinstance(calculations,list) or not calculations:
        raise SkillPolicyError('SKILL_OUTPUT_INVALID','financial skill produced no calculations')
    for item in calculations:
        value=item.model_dump(mode='json') if hasattr(item,'model_dump') else item
        if not isinstance(value,dict) or not value.get('id') or value.get('status') not in {'computed','not_computable'}:
            raise SkillPolicyError('SKILL_OUTPUT_INVALID','financial skill produced an invalid calculation')


def _claims_output(payload):
    claims=payload.get('claims') if isinstance(payload,dict) else None
    if not isinstance(claims,list) or not claims:
        raise SkillPolicyError('SKILL_OUTPUT_INVALID','research skill produced no claims')
    try:
        for item in claims:Claim.model_validate(item)
    except Exception as exc:
        raise SkillPolicyError('SKILL_OUTPUT_INVALID','research skill produced invalid claims') from exc


def _scenario_output(payload):
    result=payload.get('result') if isinstance(payload,dict) else None
    if result is None or not getattr(result,'scenario_id',None) or not getattr(result,'assumption_id',None) or not getattr(result,'calculation_ids',None):
        raise SkillPolicyError('SKILL_OUTPUT_INVALID','scenario skill produced an invalid result')


INPUT_VALIDATORS={
    'financial_snapshot.v1':_financial_input,
    'research_context.v1':_research_input,
    'scenario_request.v1':_scenario_input,
}
OUTPUT_VALIDATORS={
    'calculation_set.v1':_calculation_output,
    'validated_claims.v1':_claims_output,
    'scenario_result.v1':_scenario_output,
}
KNOWN_INPUT_CONTRACTS=frozenset(INPUT_VALIDATORS)
KNOWN_OUTPUT_CONTRACTS=frozenset(OUTPUT_VALIDATORS)


@dataclass(frozen=True)
class SkillSession:
    skill:object
    deadline:float
    clock:object

    def check_budget(self):
        if self.clock()>self.deadline:
            raise SkillPolicyError(
                'SKILL_BUDGET_EXCEEDED',f'skill time budget exceeded: {self.skill.id}',
                {'skill_id':self.skill.id,'skill_version':self.skill.version},
            )

    def remaining_seconds(self):
        remaining=self.deadline-self.clock()
        if remaining<=0:self.check_budget()
        return remaining

    def validate_output(self,payload):
        self.check_budget();OUTPUT_VALIDATORS[self.skill.output_contract](payload)


class SkillRuntimeGuard:
    def __init__(self,clock):self.clock=clock

    def start(self,skill,payload,run_deadline):
        now=self.clock();deadline=min(run_deadline,now+skill.timeout_seconds)
        INPUT_VALIDATORS[skill.input_contract](payload)
        session=SkillSession(skill,deadline,self.clock);session.check_budget();return session
