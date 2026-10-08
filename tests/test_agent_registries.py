import json
import shutil
import tempfile
import unittest
from pathlib import Path

from chain_eye.prompts import registry as prompt_module
from chain_eye.prompts.registry import DEFAULT_PROMPT_REGISTRY,PromptRegistry,PromptRegistryError,content_sha256
from chain_eye.skills import registry as skill_module
from chain_eye.skills.registry import DEFAULT_SKILL_REGISTRY,SkillRegistry,SkillRegistryError
from chain_eye.tools.registry import DEFAULT_TOOL_REGISTRY,TOOL_NAMES,ToolRegistry
from chain_eye.tools.spec import ToolContext,ToolFailure,ToolSpec


class AgentRegistries(unittest.TestCase):
    def test_default_tool_registry_is_the_single_six_tool_source(self):
        self.assertEqual(TOOL_NAMES,frozenset({
            'search_documents','get_evidence','get_facts','compute_financials',
            'compute_scenario','validate_claims',
        }))
        self.assertEqual(DEFAULT_TOOL_REGISTRY.names,TOOL_NAMES)
        self.assertIn('mcp',DEFAULT_TOOL_REGISTRY.require('get_facts').allowed_callers)
        self.assertNotIn('mcp',DEFAULT_TOOL_REGISTRY.require('compute_financials').allowed_callers)
        with self.assertRaises(ValueError):ToolRegistry([])

    def test_tool_registry_rejects_duplicates_callers_and_skill_escape(self):
        spec=ToolSpec('read','1','read',frozenset({'agent'}),1,'read',lambda context:None)
        with self.assertRaises(ValueError):ToolRegistry([spec,spec])
        context=ToolContext(None,None,None,'run','dataset',1,lambda:0)
        registry=ToolRegistry([spec])
        with self.assertRaises(ToolFailure):registry.call('read',{},context,caller='mcp')
        with self.assertRaises(ToolFailure):registry.call('read',{},context,allowed_tools=frozenset())

    def test_prompt_registry_loads_content_and_fails_closed_on_tamper(self):
        prompt=DEFAULT_PROMPT_REGISTRY.require('r4-claims-v3','claims')
        self.assertEqual(prompt.sha256,content_sha256(prompt.content))
        self.assertEqual(prompt.sha256,'9878a716ef0ac5b4c4affba50ce9800de7510fd87f0468bea4e4b02f6fe61dfa')
        self.assertIn('verified Fact.value',prompt.content)
        with self.assertRaises(PromptRegistryError):DEFAULT_PROMPT_REGISTRY.require('missing')
        with self.assertRaises(PromptRegistryError):PromptRegistry([])
        source=Path(prompt_module.__file__).resolve().parent
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'prompts';shutil.copytree(source,target)
            path=target/'claims'/'v3.md';path.write_text(path.read_text(encoding='utf-8')+'tampered',encoding='utf-8')
            with self.assertRaises(PromptRegistryError):PromptRegistry.from_directory(target)

    def test_skill_registry_loads_three_executable_policies(self):
        self.assertEqual(DEFAULT_SKILL_REGISTRY.ids,frozenset({
            'evidence_bound_research','financial_diagnosis','scenario_impact',
        }))
        research=DEFAULT_SKILL_REGISTRY.require('evidence_bound_research')
        self.assertEqual(research.prompt_version,'r4-claims-v3')
        self.assertEqual(research.instructions_sha256,content_sha256(research.instructions))
        self.assertEqual(research.instructions_sha256,'3da83f018e4be9be1f021a15dfbb218baa51d8807461f6a5831a5e7349ee5eb9')
        self.assertEqual(research.allowed_tools,frozenset({
            'get_facts','get_evidence','search_documents','validate_claims',
        }))
        with self.assertRaises(SkillRegistryError):DEFAULT_SKILL_REGISTRY.require('missing')

    def test_skill_registry_rejects_unknown_tool_and_instruction_tamper(self):
        source=Path(skill_module.__file__).resolve().parent
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'skills';shutil.copytree(source,target)
            manifest=target/'evidence_bound_research'/'skill.json'
            body=json.loads(manifest.read_text(encoding='utf-8'));body['allowed_tools'].append('open_url')
            manifest.write_text(json.dumps(body,ensure_ascii=False),encoding='utf-8')
            with self.assertRaises(SkillRegistryError):SkillRegistry.from_directory(target)
        with tempfile.TemporaryDirectory() as tmp:
            target=Path(tmp)/'skills';shutil.copytree(source,target)
            instructions=target/'financial_diagnosis'/'SKILL.md'
            instructions.write_text(instructions.read_text(encoding='utf-8')+'tampered',encoding='utf-8')
            with self.assertRaises(SkillRegistryError):SkillRegistry.from_directory(target)


if __name__=='__main__':unittest.main()
