"""Small generator for this OpenAPI JSON-schema subset. Fails on unsupported shapes."""
import json,re
from pathlib import Path
r=Path(__file__).resolve().parents[1];api=json.loads((r/'contracts/openapi.json').read_text(encoding='utf-8'))
def ident(s):return re.sub(r'[^a-zA-Z0-9_]','_',s)
def typ(s):
 if '$ref' in s:return ident(s['$ref'].split('/')[-1])
 if 'const' in s:return json.dumps(s['const'])
 if 'enum' in s:return ' | '.join(json.dumps(v) for v in s['enum'])
 if 'anyOf' in s:return ' | '.join(typ(v) for v in s['anyOf'])
 t=s.get('type')
 if isinstance(t,list):return ' | '.join(typ({**s,'type':v}) for v in t)
 if t=='string':return 'string'
 if t in ('integer','number'):return 'number'
 if t=='boolean':return 'boolean'
 if t=='null':return 'null'
 if t=='array':return f'Array<{typ(s["items"])}>'
 if t=='object':
  if not s.get('properties'):
   a=s.get('additionalProperties',True);return f'Record<string, {typ(a) if isinstance(a,dict) else "unknown"}>'
  req=s.get('required',[]);return '{ '+ '; '.join(json.dumps(k)+('' if k in req else '?')+': '+typ(v) for k,v in s['properties'].items())+' }'
 if not s:return 'unknown'
 raise ValueError(f'unsupported schema: {s}')
lines=['// GENERATED from contracts/openapi.json. Do not edit.',f'export const CONTRACT_VERSION = {json.dumps(api["info"]["version"])} as const;']
for name,s in api['components']['schemas'].items():lines.append(f'export type {ident(name)} = {typ(s)};')
lines.append('export type Operations = {')
for path,item in api['paths'].items():
 for method,op in item.items():
  if method not in ('get','post','patch','put','delete'):continue
  body=op.get('requestBody',{}).get('content',{}).get('application/json',{}).get('schema',{})
  ok=next((resp for code,resp in op['responses'].items() if code.startswith('2')),{});content=ok.get('content',{})
  out=content.get('application/json',{}).get('schema')
  outtype=typ(out) if out else 'Blob'
  lines.append(f'  {op["operationId"]}: {{ request: {typ(body)}; response: {outtype}; method: {json.dumps(method.upper())}; path: {json.dumps(path)} }};')
lines.append('};');target=r/'frontend/src/api/generated.ts';target.write_text('\n'.join(lines)+'\n',encoding='utf-8',newline='\n');print('generated',target)
