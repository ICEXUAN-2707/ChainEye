import json
import subprocess
import sys
import unittest
from dataclasses import replace
from pathlib import Path

from chain_eye.agents.graph import DEFAULT_AGENT_GRAPH,LEGACY_V2_AGENT_GRAPH
from chain_eye.agents.policy import can_recover_interrupted_node
from chain_eye.agents.spec import GraphSpec,NodeSpec,TransitionSpec
from chain_eye.agents.state import AGENT_STATE_FIELDS

ROOT=Path(__file__).resolve().parents[1]


class AgentGraphSpec(unittest.TestCase):
    def test_default_graph_declares_live_and_replay_paths(self):
        graph=DEFAULT_AGENT_GRAPH
        self.assertEqual(graph.initial_node,'plan')
        self.assertEqual(graph.state_fields,AGENT_STATE_FIELDS)
        self.assertEqual(set(graph.node_map),{
            'plan','extract','validate','finance','research','scenario','verify',
            'replay_validate','replay_copy','report',
        })
        edges={(edge.source,edge.target,edge.condition) for edge in graph.transitions}
        self.assertIn(('plan','extract','mode == live'),edges)
        self.assertIn(('plan','replay_validate','mode == replay'),edges)
        self.assertEqual(graph.require_node('research').max_retries,2)
        self.assertEqual(graph.require_node('research').recoverability,'unsafe')

    def test_graph_and_node_hashes_are_stable_and_content_bound(self):
        graph=DEFAULT_AGENT_GRAPH
        self.assertEqual(graph.spec_sha256,graph.spec_sha256)
        self.assertEqual(len(graph.spec_sha256),64)
        self.assertTrue(all(len(node.spec_sha256)==64 for node in graph.nodes))
        changed=replace(graph,nodes=(replace(graph.nodes[0],description='changed'),*graph.nodes[1:]))
        self.assertNotEqual(changed.spec_sha256,graph.spec_sha256)
        self.assertEqual(
            LEGACY_V2_AGENT_GRAPH.spec_sha256,
            '32fad023e9e89e0d71c6474d7312c030059e199916fcf5beda32fbe32291ef0b',
        )

    def test_graph_rejects_invalid_nodes_and_edges(self):
        node=NodeSpec('only','1','node',(),(),None,(),1,0,'safe',(),())
        with self.assertRaises(ValueError):
            GraphSpec('g','1','1',(), 'missing',(node,),())
        with self.assertRaises(ValueError):
            GraphSpec('g','1','1',(), 'only',(node,),(TransitionSpec('only','missing','always'),))

    def test_export_command_emits_the_authoritative_graph(self):
        result=subprocess.run(
            [sys.executable,str(ROOT/'tools/export_agent_graph.py')],cwd=ROOT,
            env={**__import__('os').environ,'PYTHONPATH':str(ROOT/'backend/src')},
            check=True,capture_output=True,text=True,encoding='utf-8',
        )
        exported=json.loads(result.stdout)
        self.assertEqual(exported,DEFAULT_AGENT_GRAPH.export())

    def test_recovery_policy_uses_graph_metadata_and_completion_markers(self):
        self.assertTrue(can_recover_interrupted_node(DEFAULT_AGENT_GRAPH,'extract',{}))
        self.assertFalse(can_recover_interrupted_node(DEFAULT_AGENT_GRAPH,'research',{'claims':[]}))
        self.assertTrue(can_recover_interrupted_node(DEFAULT_AGENT_GRAPH,'research',{'claims':[{'id':'c'}]}))
        self.assertFalse(can_recover_interrupted_node(DEFAULT_AGENT_GRAPH,'finance',{'calculation_ids':[]}))
        self.assertTrue(can_recover_interrupted_node(DEFAULT_AGENT_GRAPH,'finance',{'calculation_ids':['c-1']}))
        self.assertTrue(can_recover_interrupted_node(DEFAULT_AGENT_GRAPH,'replay_copy',{}))
        self.assertFalse(can_recover_interrupted_node(DEFAULT_AGENT_GRAPH,'unknown',{}))


if __name__=='__main__':unittest.main()
