import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from chain_eye.api.app import create_app
from chain_eye.observability import JsonlLogger,MAX_LOG_LINE_BYTES,REQUIRED_CONTEXT_FIELDS


class StructuredObservability(unittest.TestCase):
    def test_jsonl_has_required_fields_and_redacts_nested_secrets(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'events.jsonl';logger=JsonlLogger(path)
            logger.emit(
                'security_test',request_id='req-1',status='failed',error_code='EXPECTED',
                authorization='Bearer should-not-appear',
                details={
                    'Api-Key':'sk-super-secret','nested':{'refresh-token':'token-value'},
                    'message':'password=hunter2 and Bearer abc.def',
                },
            )
            raw=path.read_text(encoding='utf-8');record=json.loads(raw)
        for field in ('timestamp','level','event',*REQUIRED_CONTEXT_FIELDS):self.assertIn(field,record)
        self.assertNotIn('should-not-appear',raw);self.assertNotIn('sk-super-secret',raw)
        self.assertNotIn('token-value',raw);self.assertNotIn('hunter2',raw);self.assertIn('[REDACTED]',raw)

    def test_jsonl_is_bounded_and_never_reprs_unknown_objects(self):
        class Unknown:pass
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'events.jsonl';logger=JsonlLogger(path)
            logger.emit('unknown',status='completed',unknown=Unknown(),nonfinite=float('nan'))
            logger.emit('bounded',status='completed',large=['x'*5000 for _ in range(200)])
            payload=path.read_bytes();records=[json.loads(line) for line in payload.splitlines()]
        self.assertTrue(all(len(line)<=MAX_LOG_LINE_BYTES for line in payload.splitlines()))
        self.assertEqual(records[0]['unknown'],{'omitted_type':'Unknown'})
        self.assertEqual(records[0]['nonfinite'],'[NON_FINITE]')
        self.assertTrue(records[1]['details']['truncated'])

    def test_http_boundary_writes_request_id_without_headers_or_query(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);logger=JsonlLogger(root/'api.jsonl')
            with patch.dict(os.environ,{'CHAIN_EYE_DISABLE_MODEL':'1'}):
                app=create_app(root/'api.sqlite',upload_dir=root/'sources',logger=logger)
                with TestClient(app,base_url='http://localhost',client=('127.0.0.1',50000)) as client:
                    response=client.get('/health?token=must-not-leak',headers={'Authorization':'Bearer must-not-leak'})
            self.assertEqual(response.status_code,200)
            records=[json.loads(line) for line in (root/'api.jsonl').read_text(encoding='utf-8').splitlines()]
        request=next(item for item in records if item['event']=='http_request')
        self.assertEqual(request['request_id'],response.headers['X-Request-ID'])
        self.assertEqual(request['path'],'/health');self.assertNotIn('must-not-leak',json.dumps(records))


if __name__=='__main__':unittest.main()
