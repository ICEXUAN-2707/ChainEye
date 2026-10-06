import runpy
import sys
import unittest
from pathlib import Path
from unittest.mock import patch


ROOT=Path(__file__).resolve().parents[1]


class StartBackend(unittest.TestCase):
    def test_loads_root_dotenv_without_overriding_process_environment(self):
        with patch('dotenv.load_dotenv') as load_dotenv,patch.object(sys,'path',sys.path.copy()):
            runpy.run_path(str(ROOT/'tools/start_backend.py'),run_name='chain_eye_test_start_backend')
        load_dotenv.assert_called_once_with(dotenv_path=ROOT/'.env',override=False)
