"""Verify fixture integrity. Not a generic financial extraction benchmark."""
import json,hashlib,sys
from pathlib import Path
from decimal import Decimal
import fitz
from chain_eye.domain.contracts import Fact,Evidence
root=Path(__file__).resolve().parents[1]
manifest=json.loads((root/'data/source_manifest.json').read_text(encoding='utf-8'))
facts=[Fact.model_validate(f) for f in json.loads((root/'data/fixtures/facts.json').read_text(encoding='utf-8'))]
evs={e.id:e for e in map(Evidence.model_validate,json.loads((root/'data/fixtures/evidence.json').read_text(encoding='utf-8')))}
docs={}
for source in manifest:
 p=root/source['path'];assert hashlib.sha256(p.read_bytes()).hexdigest()==source['sha256']
 docs[source['id']]=fitz.open(p);assert len(docs[source['id']])==source['pages']
for f in facts:
 for eid in f.evidence_ids:
  e=evs[eid];p=docs[e.source_id][e.pdf_page-1]
  token=f"{int(f.raw_value):,}" if f.raw_unit=='CNY_thousand' else f.raw_value+'%'
  assert token in p.get_text(),(f.id,token)
  expected=Decimal(f.raw_value)*1000 if f.raw_unit=='CNY_thousand' else Decimal(f.raw_value)/100
  assert Decimal(f.value)==expected
for year in ('2024','2025'):
 for seg in ('power_battery','energy_storage'):
  fs={f.metric:f for f in facts if f.period_end.startswith(year) and f.segment==seg}
  gm=1-Decimal(fs['cost_of_sales'].value)/Decimal(fs['revenue'].value)
  assert abs(gm-Decimal(fs['reported_gross_margin'].value))*100<=Decimal('.005')
api=json.loads((root/'contracts/openapi.json').read_text(encoding='utf-8'));components=api['components']['schemas']
def walk(x):
 if isinstance(x,dict):
  if '$ref' in x:assert x['$ref'].split('/')[-1] in components,x['$ref']
  for v in x.values():walk(v)
 elif isinstance(x,list):
  for v in x:walk(v)
walk(api)
print(f'PASS: {len(facts)} fixture records, 4 margin checks, file hashes, contract references. Numeric presence is not row/column extraction accuracy.')
