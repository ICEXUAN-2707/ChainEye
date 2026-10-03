import json
import unittest
from decimal import Decimal,localcontext
from pathlib import Path

from chain_eye.domain.contracts import Assumptions,Fact
from chain_eye.domain.scenario import baseline,compute

ROOT=Path(__file__).resolve().parents[1]

class R3Calibration(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.facts=[Fact.model_validate(item) for item in json.loads((ROOT/'data/fixtures/facts.json').read_text(encoding='utf-8'))]

    def fact(self,year,segment,metric):
        return next(item for item in self.facts if item.period_end==f'{year}-12-31' and item.segment==segment and item.metric==metric)

    def test_four_business_year_baselines_match_disclosed_margin_tolerance(self):
        for year in (2024,2025):
            for segment in ('power_battery','energy_storage'):
                revenue=self.fact(year,segment,'revenue');cost=self.fact(year,segment,'cost_of_sales');reported=self.fact(year,segment,'reported_gross_margin')
                result=baseline(revenue,cost)
                with localcontext() as ctx:
                    ctx.prec=40;expected=(Decimal(revenue.value)-Decimal(cost.value))/Decimal(revenue.value)
                    self.assertEqual(Decimal(result['gross_margin']),expected)
                    self.assertLessEqual(abs(expected-Decimal(reported.value))*100,Decimal('0.005'))

    def test_27_grid_on_both_real_2025_business_baselines(self):
        for segment in ('power_battery','energy_storage'):
            revenue=self.fact(2025,segment,'revenue');cost=self.fact(2025,segment,'cost_of_sales')
            with localcontext() as ctx:
                ctx.prec=40;r=Decimal(revenue.value);c=Decimal(cost.value);gp0=r-c;gm0=gp0/r
                for s in ('0.05','0.10','0.20'):
                    for x in ('-0.20','0','0.20'):
                        for k in ('0','0.5','1'):
                            assumptions=Assumptions(cost_exposure=s,effective_price_shock=x,customer_pass_through=k,basis='user_assumption',acknowledged=True)
                            output=compute(revenue,cost,assumptions);dc=c*Decimal(s)*Decimal(x);r1=r+Decimal(k)*dc;c1=c+dc;gp1=r1-c1
                            expected={'delta_cost':dc,'revenue':r1,'cost_of_sales':c1,'gross_profit':gp1,'gross_margin':gp1/r1,'delta_gross_profit':gp1-gp0,'delta_gross_margin_pp':(gp1/r1-gm0)*100}
                            self.assertEqual({name:Decimal(output[name]) for name in expected},expected)

