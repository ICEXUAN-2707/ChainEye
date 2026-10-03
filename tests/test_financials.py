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

    def test_all_fixture_scope_outputs_match_independent_gold_values(self):
        expected={
            'group':{
                'revenue_yoy':'0.170406466069682213285896157070840145505',
                'gross_profit':'111318537000',
                'gross_margin':'0.2627284757044502195853133833732709308971',
            },
            'power_battery':{
                'revenue_yoy':'0.2508089498436376029739362308222391347861',
                'gross_profit':'75441972000',
                'gross_margin':'0.2383584641230394956128039243342998889226',
            },
            'energy_storage':{
                'revenue_yoy':'0.08988163125239350495702076750649235492262',
                'gross_profit':'16676131000',
                'gross_margin':'0.2670752574238682943032186832056850900595',
            },
        }
        for segment,gold in expected.items():
            facts=[fact for fact in self.facts if fact.segment==segment]
            actual={item.formula_id:item.value for item in FinancialService().compute(facts,list(gold))}
            self.assertEqual(actual,gold)

    def test_incomplete_and_mixed_scope_are_not_computable(self):
        one=[fact for fact in self.facts if fact.id=='f-2025-power_battery-revenue']
        result=FinancialService().compute(one,['revenue_yoy'])[0]
        self.assertEqual(result.status,'not_computable');self.assertIsNone(result.value);self.assertTrue(result.reason)
        result=FinancialService().compute(self.facts,['gross_profit'])[0]
        self.assertEqual(result.status,'not_computable');self.assertEqual(result.reason,'ambiguous fact scope')

    def test_stock_change_requires_comparable_point_in_time_dates(self):
        facts=[fact for fact in self.facts if fact.segment=='group' and fact.metric=='inventory']
        original=next(fact for fact in facts if fact.period_end=='2024-12-31')
        prior=Fact.model_validate({**original.model_dump(),'period_end':'2024-06-30','id':'inventory-midyear'})
        current=next(fact for fact in facts if fact.period_end=='2025-12-31')
        result=FinancialService().compute([prior,current],['inventory_change'])[0]
        self.assertEqual(result.status,'not_computable');self.assertEqual(result.reason,'comparable point-in-time dates are required')

    def test_latest_unverified_and_duplicate_periods_do_not_fall_back(self):
        revenues=[fact for fact in self.facts if fact.segment=='power_battery' and fact.metric=='revenue']
        prior=next(fact for fact in revenues if fact.period_end=='2024-12-31')
        latest=next(fact for fact in revenues if fact.period_end=='2025-12-31')
        unverified=latest.model_copy(update={'status':'needs_review'})
        result=FinancialService().compute([prior,unverified],['revenue_yoy'])[0]
        self.assertEqual(result.status,'not_computable');self.assertEqual(result.reason,'required facts are missing or not verified')
        duplicate=latest.model_copy(update={'id':'duplicate-revenue'})
        result=FinancialService().compute([*revenues,duplicate],['revenue_yoy'])[0]
        self.assertEqual(result.status,'not_computable');self.assertEqual(result.reason,'ambiguous facts for period')

    def test_all_metric_ids_are_stable(self):
        self.assertEqual(len(FINANCIAL_METRIC_IDS),6)

    def test_service_persists_calculation_snapshots(self):
        class Repository:
            saved=None
            def save_calculations(self,calculations):self.saved=calculations
        repository=Repository();facts=[fact for fact in self.facts if fact.segment=='energy_storage']
        calculations=FinancialService(repository).compute(facts,['gross_profit'])
        self.assertIs(repository.saved,calculations);self.assertEqual(calculations[0].input_revisions,{'f-2025-energy_storage-revenue':1,'f-2025-energy_storage-cost_of_sales':1})
