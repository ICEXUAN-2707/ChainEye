import json
import shutil
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from chain_eye.prompts import registry as prompt_module
from chain_eye.prompts.registry import DEFAULT_PROMPT_REGISTRY,PromptRegistry,PromptRegistryError,content_sha256
from chain_eye.skills import registry as skill_module
from chain_eye.skills.registry import DEFAULT_SKILL_REGISTRY,SkillRegistry,SkillRegistryError
from chain_eye.skills.runtime import SkillPolicyError,SkillRuntimeGuard
from chain_eye.tools.registry import DEFAULT_TOOL_REGISTRY,TOOL_NAMES,ToolRegistry
from chain_eye.tools.spec import ToolContext,ToolFailure,ToolSpec


class AgentRegistries(unittest.TestCase):
    def test_default_tool_registry_is_the_single_agent_and_mcp_tool_source(self):
        self.assertEqual(TOOL_NAMES,frozenset({
            'search_documents','get_evidence','get_facts','compute_financials',
            'compute_scenario','validate_claims',
        }))
        self.assertEqual(DEFAULT_TOOL_REGISTRY.names,TOOL_NAMES|{'get_run_trace','get_report'})
        self.assertIn('mcp',DEFAULT_TOOL_REGISTRY.require('get_facts').allowed_callers)
        self.assertEqual(DEFAULT_TOOL_REGISTRY.require('get_report').allowed_callers,frozenset({'mcp'}))
        self.assertNotIn('mcp',DEFAULT_TOOL_REGISTRY.require('compute_financials').allowed_callers)
        with self.assertRaises(ValueError):ToolRegistry([])

    def test_mcp_boundary_does_not_change_existing_agent_tool_implementations(self):
        expected={
            'compute_financials':'390c7707e90eae88aa9f6fdcb39319d0988c22437994525a5f4101ac5be7b3b7',
            'compute_scenario':'9f8c293aabaac8bab3c749cab091a4508117a67e9865649e1747f5e12a922127',
            'get_evidence':'e5de190400ca5c0da383c1983c354052271f7cb1c058b1e77baac12fb6d99fac',
            'get_facts':'4cb30ad06e6a9257a3c16a6bd690825f9fcc69914eeaa63bbe0c7849a02faa9d',
            'search_documents':'9c77aa246678f5990c424787d482351536d73f2e3e8abecbadbbfd1accdb14be',
            'validate_claims':'6207cc282a7a0d97c2cffc7361e39a791412a5b24cc337cbd9f3f3db5bf39adf',
        }
        self.assertEqual({
            name:DEFAULT_TOOL_REGISTRY.require(name).implementation_sha256
            for name in expected
        },expected)

    def test_tool_registry_rejects_duplicates_callers_and_skill_escape(self):
        spec=ToolSpec('read','1','read',frozenset({'agent'}),1,'read',lambda context:None,'test.read.v1')
        with self.assertRaises(ValueError):ToolRegistry([spec,spec])
        context=ToolContext(None,None,None,'run','dataset',1,lambda:0)
        registry=ToolRegistry([spec])
        with self.assertRaises(ToolFailure):registry.call('read',{},context,caller='mcp')
        with self.assertRaises(ToolFailure):registry.call('read',{},context,allowed_tools=frozenset())

    def test_registries_resolve_historical_versions_and_exact_hashes(self):
        old_tool=DEFAULT_TOOL_REGISTRY.require('get_facts');new_tool=replace(old_tool,version='2')
        tools=ToolRegistry([old_tool,new_tool],active_versions={'get_facts':'2'})
        self.assertEqual(tools.require('get_facts').version,'2')
        self.assertEqual(tools.resolve('get_facts','1',old_tool.spec_sha256).version,'1')
        with self.assertRaises(ToolFailure):tools.resolve('get_facts','1','0'*64)

        old_skill=DEFAULT_SKILL_REGISTRY.require('financial_diagnosis');new_skill=replace(old_skill,version='2')
        skills=SkillRegistry([old_skill,new_skill],active_versions={'financial_diagnosis':'2'})
        self.assertEqual(skills.require('financial_diagnosis').version,'2')
        self.assertEqual(skills.resolve(
            old_skill.id,old_skill.version,old_skill.spec_sha256,old_skill.instructions_sha256,
        ).version,'1')
        with self.assertRaises(SkillRegistryError):skills.resolve(old_skill.id,'1','0'*64,old_skill.instructions_sha256)

    def test_same_tool_version_with_changed_handler_fails_closed(self):
        original=DEFAULT_TOOL_REGISTRY.require('get_facts')
        def changed_handler(context,**arguments):
            return []
        changed=replace(original,handler=changed_handler)
        self.assertEqual(changed.implementation_id,original.implementation_id)
        self.assertNotEqual(changed.implementation_sha256,original.implementation_sha256)
        self.assertNotEqual(changed.spec_sha256,original.spec_sha256)
        registry=ToolRegistry([changed])
        with self.assertRaises(ToolFailure):
            registry.resolve(
                original.name,original.version,original.spec_sha256,
                original.implementation_id,original.implementation_sha256,
            )

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

    def test_skill_runtime_rejects_missing_input_and_invalid_output(self):
        research=DEFAULT_SKILL_REGISTRY.require('evidence_bound_research')
        guard=SkillRuntimeGuard(lambda:0)
        with self.assertRaises(SkillPolicyError) as missing:
            guard.start(research,{'question':'研究','dataset_version':1,'verified_facts':[]},600)
        self.assertEqual(missing.exception.code,'SKILL_INPUT_INVALID')
        session=guard.start(research,{
            'question':'研究','dataset_version':1,
            'verified_facts':[type('FactLike',(),{'status':'verified'})()],
        },600)
        with self.assertRaises(SkillPolicyError) as invalid:
            session.validate_output({'claims':[]})
        self.assertEqual(invalid.exception.code,'SKILL_OUTPUT_INVALID')


if __name__=='__main__':unittest.main()
