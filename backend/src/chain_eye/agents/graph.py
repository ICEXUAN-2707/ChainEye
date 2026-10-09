"""Authoritative G3 graph declaration; node handlers are wired by the orchestrator."""
from dataclasses import replace

from chain_eye.agents.spec import GraphSpec,NodeSpec,TransitionSpec
from chain_eye.agents.state import AGENT_STATE_FIELDS,AGENT_STATE_SCHEMA_VERSION
from chain_eye.agents.policy import MAX_NODE_RETRIES,RUN_BUDGET_SECONDS
from chain_eye.skills.registry import DEFAULT_SKILL_REGISTRY

EVENT_FIELDS=(
    'graph_id','graph_version','graph_spec_sha256','node_id','node_version',
    'node_spec_sha256','status','duration_ms','error_code',
)


def _skill_tools(skill_id,*selected):
    allowed=DEFAULT_SKILL_REGISTRY.require(skill_id).allowed_tools
    if not set(selected)<=allowed:raise ValueError(f'graph tool is outside skill allowlist: {skill_id}')
    return tuple(selected)


DEFAULT_AGENT_GRAPH=GraphSpec(
    id='chain-eye-research',version='1',state_schema_version=AGENT_STATE_SCHEMA_VERSION,
    state_fields=AGENT_STATE_FIELDS,initial_node='plan',
    nodes=(
        NodeSpec('plan','1','Select the live or replay path.',('record','bindings'),('route',),None,(),RUN_BUDGET_SECONDS,0,'safe',(),EVENT_FIELDS),
        NodeSpec('extract','1','Read the immutable fact snapshot.',('request','record'),('facts',),'financial_diagnosis',_skill_tools('financial_diagnosis','get_facts'),RUN_BUDGET_SECONDS,0,'safe',(),EVENT_FIELDS),
        NodeSpec('validate','1','Require a reviewed financial baseline.',('facts',),('verified_facts',),'financial_diagnosis',(),RUN_BUDGET_SECONDS,0,'safe',('failed',),EVENT_FIELDS),
        NodeSpec('finance','1','Persist deterministic financial calculations.',('verified_facts',),('calculation_ids',),'financial_diagnosis',_skill_tools('financial_diagnosis','compute_financials'),RUN_BUDGET_SECONDS,0,'conditional',('failed',),EVENT_FIELDS),
        NodeSpec('research','1','Produce evidence-bound candidate claims.',('verified_facts','calculation_ids'),('claims','evidence',),'evidence_bound_research',_skill_tools('evidence_bound_research','get_evidence','search_documents'),RUN_BUDGET_SECONDS,MAX_NODE_RETRIES,'unsafe',('partial','failed'),EVENT_FIELDS),
        NodeSpec('scenario','1','Wait for or execute explicit scenario assumptions.',('request','verified_facts'),('scenario_ids','assumption_ids'),'scenario_impact',_skill_tools('scenario_impact','compute_scenario'),RUN_BUDGET_SECONDS,0,'conditional',('waiting_review','failed'),EVENT_FIELDS),
        NodeSpec('verify','1','Validate references and numeric support.',('claims','evidence','calculation_ids'),('validated_claims',),'evidence_bound_research',_skill_tools('evidence_bound_research','validate_claims'),RUN_BUDGET_SECONDS,0,'safe',('partial','failed'),EVENT_FIELDS),
        NodeSpec('replay_validate','1','Validate the replay source and immutable bindings.',('record','bindings'),('source_run_id',),None,(),RUN_BUDGET_SECONDS,0,'safe',('failed',),EVENT_FIELDS),
        NodeSpec('replay_copy','1','Copy validated source artifacts without a model call.',('source_run_id',),('claims','calculation_ids','scenario_ids'),None,(),RUN_BUDGET_SECONDS,0,'safe',('partial','failed'),EVENT_FIELDS),
        NodeSpec('report','1','Persist one report and export boundary.',('claims','calculation_ids'),('report_ready',),None,(),RUN_BUDGET_SECONDS,0,'conditional',('completed','partial','failed'),EVENT_FIELDS),
    ),
    transitions=(
        TransitionSpec('plan','extract','mode == live'),
        TransitionSpec('plan','replay_validate','mode == replay'),
        TransitionSpec('extract','validate','completed'),
        TransitionSpec('validate','finance','completed'),
        TransitionSpec('finance','research','completed'),
        TransitionSpec('research','scenario','completed'),
        TransitionSpec('scenario','verify','completed_or_skipped'),
        TransitionSpec('verify','report','completed'),
        TransitionSpec('replay_validate','replay_copy','completed'),
        TransitionSpec('replay_copy','report','source completed'),
    ),
)

# Schema-v2 manifests predate graph bindings. This frozen compatibility identity
# preserves their established R5 path without pretending the old manifest
# cryptographically bound a graph. A hash-lock test makes future drift explicit.
LEGACY_V2_AGENT_GRAPH=replace(
    DEFAULT_AGENT_GRAPH,id='chain-eye-r5-compat',version='manifest-v2',
)
