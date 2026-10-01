import json
from pathlib import Path
from chain_eye.api.app import create_app
from chain_eye.domain import contracts as c
from tempfile import TemporaryDirectory
root=Path(__file__).resolve().parents[1]
with TemporaryDirectory() as t:api=create_app(Path(t)/'db.sqlite',seed=False).openapi()
(root/'contracts/openapi.json').write_text(json.dumps(api,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
for name in ('Fact','Evidence','Assumptions','ScenarioRequest','Calculation','Claim','ScenarioResult','ErrorBody','ScenarioBaseline','ScenarioOutputs','AssumptionRecord'):
 (root/'contracts'/f'{name}.schema.json').write_text(json.dumps(getattr(c,name).model_json_schema(),ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
print('Exported authoritative OpenAPI and schemas',api['info']['version'])
