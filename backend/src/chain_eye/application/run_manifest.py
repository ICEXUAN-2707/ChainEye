"""Immutable registry bindings captured when a Run is created."""
import hashlib
import json
from dataclasses import dataclass

from chain_eye.prompts.registry import PromptRegistryError
from chain_eye.skills.registry import SkillRegistryError
from chain_eye.tools.spec import ToolFailure

REQUIRED_SKILL_IDS=frozenset({'financial_diagnosis','evidence_bound_research','scenario_impact'})
REQUIRED_MODEL_CONFIG_KEYS=frozenset({
    'provider','model','adapter_version','endpoint','response_format','timeout_seconds',
})


class ExecutionManifestError(ValueError):
    pass


def manifest_sha256(manifest):
    canonical=json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def _canonical_sha256(value):
    canonical=json.dumps(value,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


def normalize_model_config(config):
    if not isinstance(config,dict) or set(config)!=REQUIRED_MODEL_CONFIG_KEYS:
        raise ExecutionManifestError('invalid public model configuration')
    if any(not isinstance(config[key],str) or not config[key] for key in REQUIRED_MODEL_CONFIG_KEYS-{'timeout_seconds'}):
        raise ExecutionManifestError('invalid public model configuration value')
    timeout=config['timeout_seconds']
    if not isinstance(timeout,(int,float)) or isinstance(timeout,bool) or timeout<=0:
        raise ExecutionManifestError('invalid public model timeout')
    try:
        return json.loads(json.dumps(config,ensure_ascii=False,sort_keys=True,separators=(',',':')))
    except (TypeError,ValueError) as exc:
        raise ExecutionManifestError('public model configuration is not JSON serializable') from exc


def build_model_binding(model_config):
    config=normalize_model_config(model_config)
    return {
        'provider':config['provider'],'model':config['model'],
        'adapter_version':config['adapter_version'],'endpoint':config['endpoint'],
        'public_config':config,'public_config_sha256':_canonical_sha256(config),
    }


@dataclass(frozen=True)
class RunBindings:
    prompt:object
    skills:dict
    tools:dict
    model:dict
    manifest:dict
    sha256:str


def build_execution_manifest(prompt,skills,tool_registry,model_config):
    skill_map={skill.id:skill for skill in skills}
    if set(skill_map)!=REQUIRED_SKILL_IDS:raise ExecutionManifestError('required skills are not fully configured')
    tool_names=sorted({name for skill in skills for name in skill.allowed_tools})
    tools={}
    for name in tool_names:
        spec=tool_registry.require(name)
        tools[name]={
            'version':spec.version,'spec_sha256':spec.spec_sha256,
            'implementation_id':spec.implementation_id,
            'implementation_sha256':spec.implementation_sha256,
        }
    return {
        'schema_version':'2',
        'prompt':{'id':prompt.id,'version':prompt.version,'sha256':prompt.sha256},
        'skills':{
            skill_id:{
                'version':skill.version,'spec_sha256':skill.spec_sha256,
                'instructions_sha256':skill.instructions_sha256,
            }
            for skill_id,skill in sorted(skill_map.items())
        },
        'tools':tools,
        'model':build_model_binding(model_config),
    }


def resolve_execution_manifest(manifest,expected_sha256,prompt_registry,skill_registry,tool_registry,current_model_config=None):
    if not isinstance(manifest,dict) or set(manifest)!={'schema_version','prompt','skills','tools','model'}:
        raise ExecutionManifestError('invalid execution manifest')
    if manifest['schema_version']!='2' or manifest_sha256(manifest)!=expected_sha256:
        raise ExecutionManifestError('execution manifest hash mismatch')
    prompt_ref=manifest['prompt'];skill_refs=manifest['skills'];tool_refs=manifest['tools'];model_ref=manifest['model']
    if not isinstance(prompt_ref,dict) or set(prompt_ref)!={'id','version','sha256'}:
        raise ExecutionManifestError('invalid prompt binding')
    if not isinstance(skill_refs,dict) or set(skill_refs)!=REQUIRED_SKILL_IDS:
        raise ExecutionManifestError('invalid skill bindings')
    if not isinstance(tool_refs,dict):raise ExecutionManifestError('invalid tool bindings')
    if not isinstance(model_ref,dict) or set(model_ref)!={
        'provider','model','adapter_version','endpoint','public_config','public_config_sha256',
    }:raise ExecutionManifestError('invalid model binding')
    bound_model=build_model_binding(model_ref['public_config'])
    if model_ref!=bound_model:raise ExecutionManifestError('model binding hash or public configuration mismatch')
    if current_model_config is not None and build_model_binding(current_model_config)!=model_ref:
        raise ExecutionManifestError('current model adapter does not match the Run binding')
    try:
        prompt=prompt_registry.resolve(prompt_ref['id'],prompt_ref['version'],prompt_ref['sha256'])
        skills={}
        for skill_id,reference in skill_refs.items():
            if not isinstance(reference,dict) or set(reference)!={'version','spec_sha256','instructions_sha256'}:
                raise ExecutionManifestError(f'invalid skill binding: {skill_id}')
            skills[skill_id]=skill_registry.resolve(
                skill_id,reference['version'],reference['spec_sha256'],reference['instructions_sha256'],
            )
        expected_tools={name for skill in skills.values() for name in skill.allowed_tools}
        if set(tool_refs)!=expected_tools:raise ExecutionManifestError('tool bindings do not match skill allowlists')
        tools={}
        for name,reference in tool_refs.items():
            if not isinstance(reference,dict) or set(reference)!={
                'version','spec_sha256','implementation_id','implementation_sha256',
            }:
                raise ExecutionManifestError(f'invalid tool binding: {name}')
            tools[name]=tool_registry.resolve(
                name,reference['version'],reference['spec_sha256'],
                reference['implementation_id'],reference['implementation_sha256'],
            )
    except (KeyError,PromptRegistryError,SkillRegistryError,ToolFailure) as exc:
        raise ExecutionManifestError(str(exc)) from exc
    research=skills['evidence_bound_research']
    if research.prompt_version!=prompt.version:
        raise ExecutionManifestError('research skill prompt does not match the Run binding')
    return RunBindings(prompt,skills,tools,bound_model,manifest,expected_sha256)
