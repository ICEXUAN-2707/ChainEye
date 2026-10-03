import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime,timedelta,timezone
from pathlib import Path
from uuid import uuid4

from chain_eye.adapters.sqlite import SQLiteRepository
from chain_eye.application.scenarios import ScenarioExecutionService
from chain_eye.domain.contracts import Calculation,ScenarioRequest
from chain_eye.domain.datasets import DatasetCreate

ROOT=Path(__file__).resolve().parents[1]

def request(dataset_id='demo-catl-2025',exposure='0.1'):
    return ScenarioRequest.model_validate({
        'dataset_id':dataset_id,'dataset_version':1,
        'revenue_fact_id':'f-2025-power_battery-revenue','cost_fact_id':'f-2025-power_battery-cost_of_sales',
        'revenue_revision':1,'cost_revision':1,'model_version':'static-gross-profit-v1',
        'assumptions':{'cost_exposure':exposure,'effective_price_shock':'-0.2','customer_pass_through':'0.5','basis':'user_assumption','acknowledged':True},
    })

class R3Persistence(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.repository=SQLiteRepository(Path(self.tmp.name)/'db.sqlite',ROOT,Path(self.tmp.name)/'sources');self.repository.seed()
        self.service=ScenarioExecutionService(self.repository)
    def tearDown(self):self.tmp.cleanup()

    def counts(self):
        with self.repository.connect() as db:
            return tuple(db.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] for table in ('scenarios','calculations','idempotency'))

    def test_concurrent_same_request_commits_one_atomic_result(self):
        with ThreadPoolExecutor(max_workers=8) as pool:
            results=list(pool.map(lambda _:self.service.execute(request(),'concurrent-key'),range(8)))
        self.assertEqual(len({item.scenario_id for item in results}),1)
        self.assertEqual(self.counts(),(1,9,1))

    def test_failed_calculation_insert_rolls_back_scenario_and_idempotency(self):
        first=self.service.execute(request(),'first-key')
        calculations=[Calculation.model_validate(self.repository.get('calculations',item)) for item in first.calculation_ids]
        duplicate_result=first.model_copy(update={'scenario_id':str(uuid4())})
        before=self.counts()
        with self.assertRaises(sqlite3.IntegrityError):
            self.repository.save_scenario_idempotently('scenario:demo-catl-2025','rollback-key','different-hash',duplicate_result,calculations,datetime.now(timezone.utc)+timedelta(hours=24))
        self.assertEqual(self.counts(),before)

    def test_expiry_is_at_least_24_hours_and_expired_key_can_be_reused(self):
        started=datetime.now(timezone.utc);first=self.service.execute(request(),'expiry-key')
        with self.repository.connect() as db:
            expiry=datetime.fromisoformat(db.execute('SELECT expires_at FROM idempotency WHERE scope=? AND key=?',('scenario:demo-catl-2025','expiry-key')).fetchone()[0])
            self.assertGreaterEqual(expiry,started+timedelta(hours=24))
            db.execute('UPDATE idempotency SET expires_at=? WHERE scope=? AND key=?',((started-timedelta(seconds=1)).isoformat(),'scenario:demo-catl-2025','expiry-key'))
        second=self.service.execute(request(exposure='0.2'),'expiry-key')
        self.assertNotEqual(first.scenario_id,second.scenario_id);self.assertEqual(self.counts(),(2,18,1))

    def test_same_key_is_scoped_by_dataset(self):
        other=self.repository.create(DatasetCreate(name='same facts, separate dataset',company='CATL',year=2025))
        with self.repository.connect() as db:
            db.execute('INSERT INTO dataset_sources(dataset_id,version,source_id) SELECT ?,1,source_id FROM dataset_sources WHERE dataset_id=? AND version=1',(other.id,'demo-catl-2025'))
            db.execute('INSERT INTO dataset_facts(dataset_id,version,fact_id,revision) SELECT ?,1,fact_id,revision FROM dataset_facts WHERE dataset_id=? AND version=1',(other.id,'demo-catl-2025'))
        one=self.service.execute(request(),'dataset-key');two=self.service.execute(request(other.id),'dataset-key')
        self.assertNotEqual(one.scenario_id,two.scenario_id);self.assertEqual(self.counts(),(2,18,2))
