"""Fail-closed loader for runtime skill policies."""
import json
from pathlib import Path

from chain_eye.prompts.registry import DEFAULT_PROMPT_REGISTRY,PromptRegistryError,content_sha256,normalized_text
from chain_eye.skills.schema import SkillSpec
from chain_eye.skills.runtime import KNOWN_INPUT_CONTRACTS,KNOWN_OUTPUT_CONTRACTS
from chain_eye.tools.registry import DEFAULT_TOOL_REGISTRY
from chain_eye.tools.spec import ToolFailure


class SkillRegistryError(ValueError):
    pass


class SkillRegistry:
    def __init__(self,specs,active_versions=None):
        self._specs={};versions_by_id={}
        for spec in specs:
            identity=(spec.id,spec.version)
            if identity in self._specs:raise SkillRegistryError(f'duplicate skill: {spec.id}@{spec.version}')
            if spec.input_contract not in KNOWN_INPUT_CONTRACTS or spec.output_contract not in KNOWN_OUTPUT_CONTRACTS:
                raise SkillRegistryError(f'unknown skill contract: {spec.id}@{spec.version}')
            self._specs[identity]=spec;versions_by_id.setdefault(spec.id,set()).add(spec.version)
        if not self._specs:raise SkillRegistryError('skill registry is empty')
        if active_versions is None:
            ambiguous=[skill_id for skill_id,versions in versions_by_id.items() if len(versions)!=1]
            if ambiguous:raise SkillRegistryError(f'active skill version is required: {ambiguous[0]}')
            active_versions={skill_id:next(iter(versions)) for skill_id,versions in versions_by_id.items()}
        if set(active_versions)!=set(versions_by_id):raise SkillRegistryError('active skill versions do not match registry IDs')
        for skill_id,version in active_versions.items():
            if (skill_id,version) not in self._specs:raise SkillRegistryError(f'unknown active skill: {skill_id}@{version}')
        self._active_versions=dict(active_versions)

    @classmethod
    def from_directory(cls,root,tool_registry=None,prompt_registry=None):
        root=Path(root).resolve();tool_registry=tool_registry or DEFAULT_TOOL_REGISTRY
        prompt_registry=prompt_registry or DEFAULT_PROMPT_REGISTRY
        active_path=root/'active.json'
        try:active=json.loads(active_path.read_text(encoding='utf-8'))
        except (OSError,UnicodeError,json.JSONDecodeError) as exc:raise SkillRegistryError('cannot read active skill versions') from exc
        if not isinstance(active,dict) or not active or not all(isinstance(key,str) and isinstance(value,str) for key,value in active.items()):
            raise SkillRegistryError('invalid active skill versions')
        specs=[];required={
            'id','version','description','instructions_path','instructions_sha256','allowed_tools',
            'prompt_version','input_requirements','output_constraints','input_contract','output_contract',
            'timeout_seconds','max_model_calls',
        }
        for manifest_path in sorted(root.glob('**/skill.json')):
            try:raw=json.loads(manifest_path.read_text(encoding='utf-8'))
            except (OSError,UnicodeError,json.JSONDecodeError) as exc:raise SkillRegistryError(f'cannot read skill: {manifest_path.parent.name}') from exc
            if not isinstance(raw,dict) or set(raw)!=required:raise SkillRegistryError(f'invalid skill entry: {manifest_path.parent.name}')
            relative=manifest_path.relative_to(root)
            if raw['id']!=relative.parts[0]:raise SkillRegistryError('skill ID does not match its directory')
            for key in ('id','version','description','instructions_path','instructions_sha256','input_contract','output_contract'):
                if not isinstance(raw[key],str) or not raw[key]:raise SkillRegistryError(f'invalid skill field: {key}')
            for key in ('allowed_tools','input_requirements','output_constraints'):
                if not isinstance(raw[key],list) or not raw[key] or not all(isinstance(item,str) and item for item in raw[key]):
                    raise SkillRegistryError(f'invalid skill field: {key}')
                if len(set(raw[key]))!=len(raw[key]):raise SkillRegistryError(f'duplicate skill field value: {key}')
            for key in ('timeout_seconds','max_model_calls'):
                if not isinstance(raw[key],int) or isinstance(raw[key],bool) or raw[key]<0:raise SkillRegistryError(f'invalid skill field: {key}')
            if raw['timeout_seconds']<=0:raise SkillRegistryError('skill timeout must be positive')
            if raw['prompt_version'] is not None and (not isinstance(raw['prompt_version'],str) or not raw['prompt_version']):
                raise SkillRegistryError('invalid prompt version')
            instructions_path=(manifest_path.parent/raw['instructions_path']).resolve()
            try:instructions_path.relative_to(manifest_path.parent.resolve())
            except ValueError as exc:raise SkillRegistryError('skill instructions path escapes its directory') from exc
            try:instructions=normalized_text(instructions_path)
            except PromptRegistryError as exc:raise SkillRegistryError(f'cannot read skill instructions: {raw["id"]}') from exc
            digest=content_sha256(instructions)
            if digest!=raw['instructions_sha256']:raise SkillRegistryError(f'skill hash mismatch: {raw["id"]}@{raw["version"]}')
            try:
                for tool in raw['allowed_tools']:tool_registry.require(tool)
                if raw['prompt_version'] is not None:prompt_registry.require(raw['prompt_version'])
            except (ToolFailure,PromptRegistryError) as exc:raise SkillRegistryError(f'invalid skill dependency: {raw["id"]}') from exc
            specs.append(SkillSpec(
                id=raw['id'],version=raw['version'],description=raw['description'],
                instructions_path=raw['instructions_path'],instructions_sha256=digest,instructions=instructions,
                allowed_tools=frozenset(raw['allowed_tools']),prompt_version=raw['prompt_version'],
                input_requirements=tuple(raw['input_requirements']),output_constraints=tuple(raw['output_constraints']),
                input_contract=raw['input_contract'],output_contract=raw['output_contract'],
                timeout_seconds=raw['timeout_seconds'],max_model_calls=raw['max_model_calls'],
            ))
        return cls(specs,active)

    @property
    def ids(self):return frozenset(self._active_versions)

    @property
    def active_versions(self):return dict(self._active_versions)

    def require(self,skill_id,version=None):
        selected=version if version is not None else self._active_versions.get(skill_id)
        spec=self._specs.get((skill_id,selected))
        if spec is None:raise SkillRegistryError(f'unknown skill: {skill_id}@{selected or "*"}')
        return spec

    def resolve(self,skill_id,version,spec_sha256,instructions_sha256):
        spec=self.require(skill_id,version)
        if spec.spec_sha256!=spec_sha256 or spec.instructions_sha256!=instructions_sha256:
            raise SkillRegistryError(f'skill hash mismatch: {skill_id}@{version}')
        return spec


DEFAULT_SKILL_REGISTRY=SkillRegistry.from_directory(Path(__file__).resolve().parent)
