import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from tools.bootstrap import install_commands
from tools.export_run_trace import export_trace
from tools.preflight import collect_checks
from tools.reproduce_core_flow import reproduce
from tools.start_all import service_specs,start_stack


class NativeReproduction(unittest.TestCase):
    def test_preflight_checks_pinned_installed_toolchain(self):
        result=collect_checks(skip_ports=True)
        failed=[item for item in result['checks'] if item['status']=='failed']
        self.assertEqual(failed,[])
        self.assertEqual(result['status'],'passed')

    def test_missing_frontend_dependencies_are_advisory_before_bootstrap(self):
        with patch('tools.preflight.Path.is_dir',return_value=False):
            result=collect_checks(skip_ports=True)
        frontend=next(item for item in result['checks'] if item['name']=='frontend_dependencies')
        self.assertEqual(frontend['status'],'warning')
        self.assertEqual(result['status'],'passed')

    def test_bootstrap_commands_are_argument_lists_without_shell_text(self):
        install=install_commands();check=install_commands(check=True)
        self.assertEqual(install[0][1:4],['-m','pip','install'])
        self.assertIn('backend/requirements.lock',install[0])
        self.assertIn('ci',install[1]);self.assertIn('pip',check[0])
        for command in install+check:self.assertIsInstance(command,list)

    def test_start_all_defaults_remove_model_credentials(self):
        with tempfile.TemporaryDirectory() as temporary,patch.dict(
            os.environ,{'DEEPSEEK_API_KEY':'must-not-propagate'},clear=False,
        ):
            specs=service_specs(Path(temporary),'nonce',live_model=False)
        backend=specs[0][3]
        self.assertNotIn('DEEPSEEK_API_KEY',backend)
        self.assertNotIn('DEEPSEEK_API_KEY',specs[1][3])
        self.assertEqual(backend['CHAIN_EYE_DISABLE_MODEL'],'1')
        self.assertEqual(backend['PYTHON_DOTENV_DISABLED'],'1')

    def test_start_all_rejects_an_occupied_required_port(self):
        with tempfile.TemporaryDirectory() as temporary,patch('tools.start_all._port_is_free',return_value=False):
            with self.assertRaisesRegex(RuntimeError,'8000'):
                start_stack(Path(temporary),timeout=.1)

    def test_start_all_live_model_requires_an_explicit_key(self):
        with tempfile.TemporaryDirectory() as temporary,patch.dict(os.environ,{},clear=True):
            with self.assertRaisesRegex(RuntimeError,'requires DEEPSEEK_API_KEY'):
                start_stack(Path(temporary),timeout=.1,live_model=True)

    def test_replay_uses_a_persisted_terminal_run_and_exports_safe_trace(self):
        with tempfile.TemporaryDirectory() as temporary:
            output=Path(temporary)/'reproduction';result=reproduce(output)
            persisted=json.loads((output/'result.json').read_text(encoding='utf-8'))
            replay_lines=(output/'replay-trace.jsonl').read_text(encoding='utf-8').splitlines()
            log_text=(output/'chain-eye.jsonl').read_text(encoding='utf-8')
            duplicate=export_trace(
                output/'reproduction.sqlite',result['replay_run_id'],output/'replay-trace-copy.jsonl',
            )
            with self.assertRaises(FileExistsError):
                export_trace(output/'reproduction.sqlite',result['replay_run_id'],output/'replay-trace.jsonl')
        self.assertEqual(result['status'],'passed');self.assertEqual(result['source_status'],'partial')
        self.assertEqual(result['source_error_code'],'MODEL_UNAVAILABLE')
        self.assertEqual(result['replay_status'],'partial');self.assertEqual(result['replay_model_calls'],0)
        self.assertFalse(result['paid_model_calls']);self.assertEqual(persisted['replay_disclosure'],'saved_run_artifacts_only')
        self.assertGreater(len(replay_lines),2);self.assertIn('agent_node',log_text);self.assertIn('tool_call',log_text)
        self.assertEqual(duplicate['sha256'],result['replay_trace_sha256'])
        combined='\n'.join(replay_lines)+log_text
        self.assertNotIn('authorization',combined.casefold())


if __name__=='__main__':unittest.main()
