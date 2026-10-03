import unittest
from decimal import Decimal
from pydantic import ValidationError
from chain_eye.domain.contracts import Fact,Assumptions
from chain_eye.domain.scenario import baseline,compute,DomainError

def fact(metric,value):
 return Fact(id=metric,company='CATL',metric=metric,segment='power_battery',statement_scope='consolidated',period_kind='annual_flow',period_start='2025-01-01',period_end='2025-12-31',value=str(value),unit='CNY',raw_value=str(Decimal(str(value))/1000),raw_unit='CNY_thousand',status='verified',evidence_ids=['e1'])
def a(s='0.2',x='-0.2',k='0.5'):
 return Assumptions(cost_exposure=s,effective_price_shock=x,customer_pass_through=k,basis='user_assumption',acknowledged=True)
class Tests(unittest.TestCase):
 def test_half_pass(self):
  o=compute(fact('revenue',100),fact('cost_of_sales',80),a()); self.assertEqual(Decimal(o['gross_profit']),Decimal('21.6'))
 def test_zero_shock(self):
  self.assertEqual(Decimal(compute(fact('revenue',100),fact('cost_of_sales',80),a(x='0'))['gross_profit']),20)
 def test_zero_exposure(self):
  self.assertEqual(Decimal(compute(fact('revenue',100),fact('cost_of_sales',80),a(s='0'))['delta_gross_profit']),0)
 def test_full_pass(self):
  o=compute(fact('revenue',100),fact('cost_of_sales',80),a(k='1'));self.assertEqual(Decimal(o['gross_profit']),20);self.assertGreater(Decimal(o['gross_margin']),Decimal('.2'))
 def test_no_pass(self):
  self.assertEqual(Decimal(compute(fact('revenue',100),fact('cost_of_sales',80),a(k='0'))['gross_profit']),Decimal('23.2'))
 def test_rise(self):
  self.assertEqual(Decimal(compute(fact('revenue',100),fact('cost_of_sales',80),a(x='0.2'))['gross_profit']),Decimal('18.4'))
 def test_scope(self):
  c=fact('cost_of_sales',80).model_copy(update={'segment':'group'})
  with self.assertRaises(DomainError):compute(fact('revenue',100),c,a())
 def test_unreviewed(self):
  c=fact('cost_of_sales',80).model_copy(update={'status':'extracted'})
  with self.assertRaises(DomainError):compute(fact('revenue',100),c,a())
 def test_bounds(self):
  with self.assertRaises(ValidationError):a(x='-0.6')
 def test_nonfinite(self):
  with self.assertRaises(ValidationError):a(s='NaN')
 def test_zero_revenue(self):
  with self.assertRaises(DomainError):compute(fact('revenue',0),fact('cost_of_sales',80),a())
 def test_negative_revenue_result(self):
  with self.assertRaises(DomainError):compute(fact('revenue',1),fact('cost_of_sales',100),a(s='1',x='-0.5',k='1'))
 def test_required_acknowledgement(self):
  with self.assertRaises(ValidationError):Assumptions(cost_exposure='0.2',effective_price_shock='-0.2',customer_pass_through='0.5',basis='user_assumption',acknowledged=False)
 def test_missing(self):
  with self.assertRaises(ValidationError):fact('revenue',100).model_dump() and Fact(**{**fact('revenue',100).model_dump(),'status':'missing'})
 def test_baseline_is_canonical(self):
  self.assertEqual(baseline(fact('revenue',100),fact('cost_of_sales',80)),{'revenue':'100','cost_of_sales':'80','gross_profit':'20','gross_margin':'0.2'})
 def test_documented_27_grid(self):
  for s in ('0.05','0.10','0.20'):
   for x in ('-0.20','0','0.20'):
    for k in ('0','0.5','1'):
     output=compute(fact('revenue',100),fact('cost_of_sales',80),a(s,x,k))
     self.assertEqual(Decimal(output['delta_gross_profit']),(Decimal(k)-1)*Decimal('80')*Decimal(s)*Decimal(x))
