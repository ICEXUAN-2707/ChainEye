import json
import unittest
from decimal import Decimal
from pathlib import Path

from chain_eye.application.financials import FinancialService
from chain_eye.domain.contracts import Fact
from chain_eye.domain.financials import FINANCIAL_METRIC_IDS

ROOT=Path(__file__).resolve().parents[1]

class Financials(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.facts=[Fact.model_validate(item) for item in json.loads((ROOT/'data/fixtures/facts.json').read_text(encoding='utf-8'))]

    def test_segment_metrics_use_verified_same_scope_facts(self):
        facts=[fact for fact in self.facts if fact.segment=='power_battery']
        values={item.formula_id:item for item in FinancialService().compute(facts,['revenue_yoy','gross_profit','gross_margin'])}
        self.assertEqual(values['revenue_yoy'].value,'0.2508089498436376029739362308222391347861')
        self.assertEqual(values['gross_profit'].value,'75441972000')
        self.assertEqual(values['gross_margin'].value,'0.2383584641230394956128039243342998889226')
        self.assertTrue(all(item.status=='computed' for item in values.values()))

    def test_group_change_and_gap_metrics(self):
        facts=[fact for fact in self.facts if fact.segment=='group']
        requested=['inventory_change','accounts_receivable_change','parent_adjusted_profit_gap']
        values={item.formula_id:item.value for item in FinancialService().compute(facts,requested)}
        self.assertEqual(values,{'inventory_change':'34690706000','accounts_receivable_change':'12267754000','parent_adjusted_profit_gap':'7693418000'})

    def test_incomplete_and_mixed_scope_are_not_computable(self):
        one=[fact for fact in self.facts if fact.id=='f-2025-power_battery-revenue']
        result=FinancialService().compute(one,['revenue_yoy'])[0]
        self.assertEqual(result.status,'not_computable');self.assertIsNone(result.value);self.assertTrue(result.reason)
        result=FinancialService().compute(self.facts,['gross_profit'])[0]
        self.assertEqual(result.status,'not_computable');self.assertEqual(result.reason,'ambiguous fact scope')

    def test_all_metric_ids_are_stable(self):
        self.assertEqual(len(FINANCIAL_METRIC_IDS),6)

    def test_service_persists_calculation_snapshots(self):
        class Repository:
            saved=None
            def save_calculations(self,calculations):self.saved=calculations
        repository=Repository();facts=[fact for fact in self.facts if fact.segment=='energy_storage']
        calculations=FinancialService(repository).compute(facts,['gross_profit'])
        self.assertIs(repository.saved,calculations);self.assertEqual(calculations[0].input_revisions,{'f-2025-energy_storage-revenue':1,'f-2025-energy_storage-cost_of_sales':1})
