import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from chain_eye.adapters.sqlite import SQLiteRepository
from chain_eye.api.app import create_app
from chain_eye.config import DEFAULT_DB_PATH,PROJECT_ROOT,database_path,upload_root
from chain_eye.mcp.context import build_repository


class RuntimeConfig(unittest.TestCase):
    def test_api_and_mcp_resolve_the_same_default_database(self):
        with patch.dict(os.environ,{},clear=False):
            os.environ.pop('CHAIN_EYE_DB',None)
            with patch('chain_eye.api.app.SQLiteRepository') as api_repository:
                create_app(seed=False)
            with patch('chain_eye.mcp.context.SQLiteRepository') as mcp_repository:
                build_repository(seed=False)
        self.assertEqual(api_repository.call_args.args[0],DEFAULT_DB_PATH)
        self.assertEqual(mcp_repository.call_args.args[0],DEFAULT_DB_PATH)
        self.assertTrue(mcp_repository.call_args.kwargs['read_only'])

    def test_environment_paths_are_explicit(self):
        with tempfile.TemporaryDirectory() as temporary:
            db=Path(temporary)/'custom.sqlite';sources=Path(temporary)/'sources'
            with patch.dict(os.environ,{'CHAIN_EYE_DB':str(db),'CHAIN_EYE_UPLOAD_DIR':str(sources)}):
                self.assertEqual(database_path(),db);self.assertEqual(upload_root(),sources)

    def test_default_mcp_reads_database_initialized_by_api(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'chain_eye.sqlite';sources=Path(temporary)/'sources'
            with (
                patch.dict(os.environ,{},clear=False),
                patch('chain_eye.config.DEFAULT_DB_PATH',path),
                patch('chain_eye.config.DEFAULT_UPLOAD_ROOT',sources),
            ):
                os.environ.pop('CHAIN_EYE_DB',None);os.environ.pop('CHAIN_EYE_UPLOAD_DIR',None)
                app=create_app()
                repository=build_repository(seed=False)
            self.assertEqual(app.state.repository.path,path)
            self.assertEqual(repository.path,path)
            self.assertEqual(repository.get_dataset('demo-catl-2025',1).version,1)

    def test_read_only_repository_never_creates_or_migrates(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);missing=root/'missing'/'chain_eye.sqlite'
            with self.assertRaises(FileNotFoundError):
                SQLiteRepository(missing,PROJECT_ROOT,read_only=True)
            self.assertFalse(missing.exists());self.assertFalse(missing.parent.exists())

            path=root/'chain_eye.sqlite'
            writable=SQLiteRepository(path,PROJECT_ROOT,root/'sources');writable.seed()
            before=path.read_bytes()
            with writable.connect() as db:
                before_counts=(
                    db.execute('SELECT COUNT(*) FROM migrations').fetchone()[0],
                    db.execute('SELECT COUNT(*) FROM datasets').fetchone()[0],
                    db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],
                )
            readonly=SQLiteRepository(path,PROJECT_ROOT,root/'unused-sources',read_only=True)
            self.assertEqual(readonly.get_dataset('demo-catl-2025',1).version,1)
            with readonly.connect() as db:self.assertEqual(db.execute('PRAGMA query_only').fetchone()[0],1)
            with self.assertRaises(sqlite3.OperationalError):
                readonly.create(writable.get_dataset('demo-catl-2025',1))
            self.assertEqual(path.read_bytes(),before)
            with writable.connect() as db:
                after_counts=(
                    db.execute('SELECT COUNT(*) FROM migrations').fetchone()[0],
                    db.execute('SELECT COUNT(*) FROM datasets').fetchone()[0],
                    db.execute('SELECT COUNT(*) FROM runs').fetchone()[0],
                )
            self.assertEqual(after_counts,before_counts)
            self.assertFalse((root/'unused-sources').exists())

    def test_read_only_repository_rejects_uninitialized_database(self):
        with tempfile.TemporaryDirectory() as temporary:
            path=Path(temporary)/'empty.sqlite';sqlite3.connect(path).close()
            with self.assertRaisesRegex(RuntimeError,'not initialized'):
                SQLiteRepository(path,PROJECT_ROOT,read_only=True)


if __name__=='__main__':unittest.main()
