"""Fail-closed loader for versioned prompt content."""
import hashlib
import json
from dataclasses import dataclass
from pathlib import Path


class PromptRegistryError(ValueError):
    pass


def normalized_text(path:Path):
    try:content=path.read_text(encoding='utf-8')
    except (OSError,UnicodeError) as exc:raise PromptRegistryError(f'cannot read prompt resource: {path.name}') from exc
    if content.endswith('\r\n'):content=content[:-2]
    elif content.endswith('\n'):content=content[:-1]
    if not content or '\x00' in content:raise PromptRegistryError(f'invalid prompt content: {path.name}')
    return content


def content_sha256(content:str):return hashlib.sha256(content.encode('utf-8')).hexdigest()


@dataclass(frozen=True)
class PromptSpec:
    id:str
    version:str
    path:str
    sha256:str
    content:str


class PromptRegistry:
    def __init__(self,specs):
        self._by_version={};self._by_identity={}
        for spec in specs:
            identity=(spec.id,spec.version)
            if spec.version in self._by_version or identity in self._by_identity:
                raise PromptRegistryError(f'duplicate prompt: {spec.id}@{spec.version}')
            self._by_version[spec.version]=spec;self._by_identity[identity]=spec
        if not self._by_version:raise PromptRegistryError('prompt registry is empty')

    @classmethod
    def from_directory(cls,root):
        root=Path(root).resolve();manifest_path=root/'manifest.json'
        try:manifest=json.loads(manifest_path.read_text(encoding='utf-8'))
        except (OSError,UnicodeError,json.JSONDecodeError) as exc:raise PromptRegistryError('cannot read prompt manifest') from exc
        if set(manifest)!={'prompts'} or not isinstance(manifest['prompts'],list):
            raise PromptRegistryError('invalid prompt manifest')
        specs=[]
        for raw in manifest['prompts']:
            if not isinstance(raw,dict) or set(raw)!={'id','version','path','sha256'}:
                raise PromptRegistryError('invalid prompt entry')
            if not all(isinstance(raw[key],str) and raw[key] for key in raw):
                raise PromptRegistryError('invalid prompt entry')
            path=(root/raw['path']).resolve()
            try:path.relative_to(root)
            except ValueError as exc:raise PromptRegistryError('prompt path escapes registry root') from exc
            content=normalized_text(path);digest=content_sha256(content)
            if digest!=raw['sha256']:raise PromptRegistryError(f'prompt hash mismatch: {raw["id"]}@{raw["version"]}')
            specs.append(PromptSpec(raw['id'],raw['version'],raw['path'],digest,content))
        return cls(specs)

    @property
    def versions(self):return frozenset(self._by_version)

    def require(self,version,prompt_id=None):
        spec=self._by_version.get(version)
        if spec is None or (prompt_id is not None and spec.id!=prompt_id):
            raise PromptRegistryError(f'unknown prompt: {prompt_id or "*"}@{version}')
        return spec


DEFAULT_PROMPT_REGISTRY=PromptRegistry.from_directory(Path(__file__).resolve().parent)
