import unittest,json
from pydantic import ValidationError
from chain_eye.domain.contracts import Fact,Assumptions,Calculation,ScenarioOutputs
from chain_eye.api.dto import RunCreate
from test_scenario import fact,a
class Contracts(unittest.TestCase):
 def test_raw_mismatch(self):
  with self.assertRaises(ValidationError):Fact.model_validate({**fact('revenue',100).model_dump(),'raw_value':'1'})
 def test_annual_partial(self):
  with self.assertRaises(ValidationError):Fact.model_validate({**fact('revenue',100).model_dump(),'period_start':'2025-04-01'})
 def test_bad_date(self):
  with self.assertRaises(ValidationError):Fact.model_validate({**fact('revenue',100).model_dump(),'period_end':'2025-02-30'})
 def test_ack_number(self):
  with self.assertRaises(ValidationError):Assumptions.model_validate({**a().model_dump(),'cost_exposure':'0.2','effective_price_shock':'-0.2','customer_pass_through':'0.5','acknowledged':1})
 def test_numeric_parameter(self):
  with self.assertRaises(ValidationError):Assumptions(cost_exposure=0.2,effective_price_shock='0',customer_pass_through='0.5',basis='user_assumption',acknowledged=True)
 def test_extra(self):
  with self.assertRaises(ValidationError):Fact.model_validate({**fact('revenue',100).model_dump(),'fake':'1'})
 def test_run_replay_no_source(self):
  with self.assertRaises(ValidationError):RunCreate(dataset_id='d',dataset_version=1,question='q',segment='power_battery',mode='replay')
 def test_run_live_replay_source(self):
  with self.assertRaises(ValidationError):RunCreate(dataset_id='d',dataset_version=1,question='q',segment='power_battery',mode='live',replay_run_id='r')
 def test_incomplete_result(self):
  with self.assertRaises(ValidationError):ScenarioOutputs(revenue='100',cost_of_sales='80')
 def test_calculation_revision_set(self):
  with self.assertRaises(ValidationError):Calculation(id='c',formula_id='x',formula_version='1',input_fact_ids=['f'],input_revisions={},assumption_snapshot={},value='1',unit='CNY',status='computed')
