"""Immutable registry bindings captured when a Run is created."""
import hashlib
import json
from dataclasses import dataclass

from chain_eye.prompts.registry import PromptRegistryError
from chain_eye.skills.registry import SkillRegistryError
from chain_eye.tools.spec import ToolFailure

REQUIRED_SKILL_IDS=frozenset({'financial_diagnosis','evidence_bound_research','scenario_impact'})


class ExecutionManifestError(ValueError):
    pass


def manifest_sha256(manifest):
    canonical=json.dumps(manifest,ensure_ascii=False,sort_keys=True,separators=(',',':'))
    return hashlib.sha256(canonical.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class RunBindings:
    prompt:object
    skills:dict
    tools:dict
    manifest:dict
    sha256:str


def build_execution_manifest(prompt,skills,tool_registry):
    skill_map={skill.id:skill for skill in skills}
    if set(skill_map)!=REQUIRED_SKILL_IDS:raise ExecutionManifestError('required skills are not fully configured')
    tool_names=sorted({name for skill in skills for name in skill.allowed_tools})
    tools={}
    for name in tool_names:
        spec=tool_registry.require(name)
        tools[name]={'version':spec.version,'spec_sha256':spec.spec_sha256}
    return {
        'schema_version':'1',
        'prompt':{'id':prompt.id,'version':prompt.version,'sha256':prompt.sha256},
        'skills':{
            skill_id:{
                'version':skill.version,'spec_sha256':skill.spec_sha256,
                'instructions_sha256':skill.instructions_sha256,
            }
            for skill_id,skill in sorted(skill_map.items())
        },
        'tools':tools,
    }


def resolve_execution_manifest(manifest,expected_sha256,prompt_registry,skill_registry,tool_registry):
    if not isinstance(manifest,dict) or set(manifest)!={'schema_version','prompt','skills','tools'}:
        raise ExecutionManifestError('invalid execution manifest')
    if manifest['schema_version']!='1' or manifest_sha256(manifest)!=expected_sha256:
        raise ExecutionManifestError('execution manifest hash mismatch')
    prompt_ref=manifest['prompt'];skill_refs=manifest['skills'];tool_refs=manifest['tools']
    if not isinstance(prompt_ref,dict) or set(prompt_ref)!={'id','version','sha256'}:
        raise ExecutionManifestError('invalid prompt binding')
    if not isinstance(skill_refs,dict) or set(skill_refs)!=REQUIRED_SKILL_IDS:
        raise ExecutionManifestError('invalid skill bindings')
    if not isinstance(tool_refs,dict):raise ExecutionManifestError('invalid tool bindings')
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
            if not isinstance(reference,dict) or set(reference)!={'version','spec_sha256'}:
                raise ExecutionManifestError(f'invalid tool binding: {name}')
            tools[name]=tool_registry.resolve(name,reference['version'],reference['spec_sha256'])
    except (KeyError,PromptRegistryError,SkillRegistryError,ToolFailure) as exc:
        raise ExecutionManifestError(str(exc)) from exc
    research=skills['evidence_bound_research']
    if research.prompt_version!=prompt.version:
        raise ExecutionManifestError('research skill prompt does not match the Run binding')
    return RunBindings(prompt,skills,tools,manifest,expected_sha256)
