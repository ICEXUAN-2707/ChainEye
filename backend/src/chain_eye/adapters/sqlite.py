import sqlite3, json, hashlib
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
from chain_eye.domain.datasets import Dataset,DatasetCreate,Source,SourceAttachment,DatasetSourceLimitError
from chain_eye.domain.contracts import Fact,Evidence,ScenarioResult
from chain_eye.domain.review import EvidenceScopeError,FactNotFoundError,FactRevisionConflictError,FactScopeError
from chain_eye.domain.scenario import (
    IdempotencyConflictError,ScenarioEvidenceNotFoundError,
    ScenarioEvidenceScopeError,ScenarioFactNotFoundError,ScenarioFactScopeError,
)

class SQLiteRepository:
    def __init__(self,path,project_root,upload_root=None):
        self.path=Path(path);self.root=Path(project_root);self.upload_root=Path(upload_root or self.root/'.runtime/sources')
        self.path.parent.mkdir(parents=True,exist_ok=True);self.upload_root.mkdir(parents=True,exist_ok=True)
        with self.connect() as db:
            db.execute('PRAGMA journal_mode=WAL')
            db.execute('CREATE TABLE IF NOT EXISTS migrations(name TEXT PRIMARY KEY, sha256 TEXT NOT NULL)')
            for p in sorted((self.root/'backend/migrations').glob('*.sql')):
                sha=hashlib.sha256(p.read_bytes()).hexdigest();row=db.execute('SELECT sha256 FROM migrations WHERE name=?',(p.name,)).fetchone()
                if row and row[0]!=sha: raise RuntimeError('applied migration modified')
                if not row:db.executescript(p.read_text(encoding='utf-8'));db.execute('INSERT INTO migrations VALUES (?,?)',(p.name,sha))
    @contextmanager
    def connect(self):
        db=sqlite3.connect(self.path,timeout=10);db.execute('PRAGMA foreign_keys=ON')
        try:
            with db:yield db
        finally:db.close()
    def create(self,request:DatasetCreate):
        d=Dataset(id=str(uuid4()),name=request.name,company=request.company,year=request.year,version=1,source_ids=[],created_at=datetime.now(timezone.utc).isoformat(),data_basis='empty')
        with self.connect() as db:
            db.execute('INSERT INTO datasets VALUES (?,?,?,?)',(d.id,'local',1,d.model_dump_json()))
            db.execute('INSERT INTO dataset_snapshots VALUES (?,?,?)',(d.id,1,d.model_dump_json()))
        return d
    def get_dataset(self,id,version=None):
        with self.connect() as db:
            row=db.execute('SELECT body FROM dataset_snapshots WHERE dataset_id=? AND version=?',(id,version)).fetchone() if version is not None else db.execute('SELECT body FROM datasets WHERE id=?',(id,)).fetchone()
        return Dataset.model_validate_json(row[0]) if row else None
    def list_datasets(self,offset,limit):
        with self.connect() as db: rows=db.execute('SELECT body FROM datasets ORDER BY id LIMIT ? OFFSET ?',(limit+1,offset)).fetchall()
        return [Dataset.model_validate_json(row[0]) for row in rows[:limit]],offset+limit if len(rows)>limit else None
    def get(self,table,id):
        if table not in ('sources','evidence','calculations','runs'):raise ValueError('unknown table')
        with self.connect() as db:row=db.execute(f'SELECT body FROM {table} WHERE id=?',(id,)).fetchone()
        return json.loads(row[0]) if row else None
    def get_source_by_sha256(self,sha256):
        with self.connect() as db:row=db.execute('SELECT body FROM sources WHERE sha256=?',(sha256,)).fetchone()
        return Source.model_validate_json(row[0]) if row else None
    def get_source(self,id):
        with self.connect() as db:row=db.execute('SELECT body FROM sources WHERE id=?',(id,)).fetchone()
        return Source.model_validate_json(row[0]) if row else None
    def attach_source(self,dataset_id,proposed_source,content_path,max_sources=5):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT current_version,body FROM datasets WHERE id=?',(dataset_id,)).fetchone()
            if not row:return None
            current=Dataset.model_validate_json(row[1])
            source_row=db.execute('SELECT body FROM sources WHERE sha256=?',(proposed_source.sha256,)).fetchone()
            source=Source.model_validate_json(source_row[0]) if source_row else proposed_source
            if source.id in current.source_ids:return SourceAttachment(dataset=current,source=source)
            if len(current.source_ids)>=max_sources:raise DatasetSourceLimitError(f'dataset source limit is {max_sources}')
            if not source_row:
                db.execute('INSERT INTO sources VALUES (?,?,?,?)',(source.id,source.sha256,content_path,source.model_dump_json()))
            new_version=current.version+1
            updated=current.model_copy(update={'version':new_version,'source_ids':[*current.source_ids,source.id],'data_basis':'user_uploaded'})
            db.execute('UPDATE datasets SET current_version=?,body=? WHERE id=?',(new_version,updated.model_dump_json(),dataset_id))
            db.execute('INSERT INTO dataset_snapshots VALUES (?,?,?)',(dataset_id,new_version,updated.model_dump_json()))
            db.execute('INSERT INTO dataset_sources(dataset_id,version,source_id) SELECT dataset_id,?,source_id FROM dataset_sources WHERE dataset_id=? AND version=?',(new_version,dataset_id,current.version))
            db.execute('INSERT INTO dataset_sources VALUES (?,?,?)',(dataset_id,new_version,source.id))
            db.execute('INSERT INTO dataset_facts(dataset_id,version,fact_id,revision) SELECT dataset_id,?,fact_id,revision FROM dataset_facts WHERE dataset_id=? AND version=?',(new_version,dataset_id,current.version))
        return SourceAttachment(dataset=updated,source=source)
    def facts(self,id,version):
        with self.connect() as db:
            rows=db.execute('SELECT f.body FROM dataset_facts df JOIN facts f ON f.id=df.fact_id AND f.revision=df.revision WHERE df.dataset_id=? AND df.version=? ORDER BY f.id',(id,version)).fetchall()
        return [Fact.model_validate_json(row[0]) for row in rows]
    def get_fact_for_snapshot(self,dataset_id,version,fact_id,revision):
        with self.connect() as db:
            exists=db.execute('SELECT 1 FROM facts WHERE id=?',(fact_id,)).fetchone()
            if exists is None:raise ScenarioFactNotFoundError('fact does not exist')
            row=db.execute('SELECT f.body FROM dataset_facts df JOIN facts f ON f.id=df.fact_id AND f.revision=df.revision WHERE df.dataset_id=? AND df.version=? AND df.fact_id=? AND df.revision=?',(dataset_id,version,fact_id,revision)).fetchone()
        if row is None:raise ScenarioFactScopeError('fact revision is outside the requested dataset snapshot')
        return Fact.model_validate_json(row[0])
    def validate_evidence_snapshot(self,dataset_id,version,evidence_ids):
        with self.connect() as db:
            for evidence_id in evidence_ids:
                row=db.execute('SELECT source_id FROM evidence WHERE id=?',(evidence_id,)).fetchone()
                if row is None:raise ScenarioEvidenceNotFoundError('assumption evidence does not exist')
                linked=db.execute('SELECT 1 FROM dataset_sources WHERE dataset_id=? AND version=? AND source_id=?',(dataset_id,version,row[0])).fetchone()
                if linked is None:raise ScenarioEvidenceScopeError('assumption evidence is outside the requested dataset snapshot')
    def save_calculations(self,calculations):
        with self.connect() as db:
            for calculation in calculations:
                db.execute('INSERT INTO calculations VALUES (?,?)',(calculation.id,calculation.model_dump_json()))
    def get_idempotent_scenario(self,scope,key,body_hash):
        with self.connect() as db:
            row=db.execute('SELECT body_hash,response_body,expires_at FROM idempotency WHERE scope=? AND key=?',(scope,key)).fetchone()
        if row and datetime.fromisoformat(row[2])>datetime.now(timezone.utc):
            if row[0]!=body_hash:raise IdempotencyConflictError('idempotency key reused')
            return ScenarioResult.model_validate_json(row[1])
        return None
    def save_scenario_idempotently(self,scope,key,body_hash,result,calculations,expires_at):
        now=datetime.now(timezone.utc)
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            row=db.execute('SELECT body_hash,response_body,expires_at FROM idempotency WHERE scope=? AND key=?',(scope,key)).fetchone()
            if row:
                expiry=datetime.fromisoformat(row[2])
                if expiry>now:
                    if row[0]!=body_hash:raise IdempotencyConflictError('idempotency key reused')
                    return ScenarioResult.model_validate_json(row[1])
                db.execute('DELETE FROM idempotency WHERE scope=? AND key=?',(scope,key))
            for calculation in calculations:
                db.execute('INSERT INTO calculations VALUES (?,?)',(calculation.id,calculation.model_dump_json()))
            response=result.model_dump_json()
            db.execute('INSERT INTO scenarios VALUES (?,?)',(result.scenario_id,response))
            db.execute('INSERT INTO idempotency VALUES (?,?,?,?,?)',(scope,key,body_hash,response,expires_at.isoformat()))
        return result
    @staticmethod
    def _fact_key(fact):
        return (fact.company,fact.metric,fact.segment,fact.period_end,fact.statement_scope)
    def apply_extraction(self,dataset_id,source_id,result):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            dataset_row=db.execute('SELECT body FROM datasets WHERE id=?',(dataset_id,)).fetchone()
            if dataset_row is None:return None
            current=Dataset.model_validate_json(dataset_row[0])
            linked=db.execute('SELECT 1 FROM dataset_sources WHERE dataset_id=? AND version=? AND source_id=?',(dataset_id,current.version,source_id)).fetchone()
            source_row=db.execute('SELECT body FROM sources WHERE id=?',(source_id,)).fetchone()
            if linked is None or source_row is None:raise FactScopeError('source is outside current dataset')
            source=Source.model_validate_json(source_row[0])
            status=result.parse_status
            if source.parse_status=='parsed' and status!='failed':status='parsed'
            updated_source=source.model_copy(update={'parse_status':status})
            db.execute('UPDATE sources SET body=? WHERE id=?',(updated_source.model_dump_json(),source_id))

            rows=db.execute('SELECT f.body FROM dataset_facts df JOIN facts f ON f.id=df.fact_id AND f.revision=df.revision WHERE df.dataset_id=? AND df.version=?',(dataset_id,current.version)).fetchall()
            existing_facts=[Fact.model_validate_json(row[0]) for row in rows]
            existing={}
            for existing_fact in existing_facts:existing.setdefault(self._fact_key(existing_fact),[]).append(existing_fact)
            candidates=[]
            for fact in result.facts:
                if fact.status=='verified':raise ValueError('automatic extraction cannot verify facts')
                key=self._fact_key(fact);prior=existing.get(key,[])
                if not prior:
                    candidates.append(fact);existing[key]=[fact]
                elif fact.status!='missing' and not any((item.value,item.unit)==(fact.value,fact.unit) for item in prior):
                    conflict=Fact.model_validate({**fact.model_dump(),'status':'conflict'})
                    candidates.append(conflict);existing[key].append(conflict)
            evidence_by_id={item.id:item for item in result.evidence}
            needed={evidence_id for fact in candidates for evidence_id in fact.evidence_ids}
            if not needed.issubset(evidence_by_id):raise EvidenceScopeError('candidate references unknown evidence')
            for evidence_id in needed:
                evidence=evidence_by_id[evidence_id]
                if evidence.source_id!=source_id:raise EvidenceScopeError('evidence source mismatch')
                prior=db.execute('SELECT body FROM evidence WHERE id=?',(evidence.id,)).fetchone()
                if prior:
                    if Evidence.model_validate_json(prior[0])!=evidence:raise EvidenceScopeError('evidence id collision')
                else:db.execute('INSERT INTO evidence VALUES (?,?,?)',(evidence.id,evidence.source_id,evidence.model_dump_json()))
            for fact in candidates:
                prior=db.execute('SELECT body FROM facts WHERE id=? AND revision=?',(fact.id,fact.revision)).fetchone()
                if prior:
                    if Fact.model_validate_json(prior[0])!=fact:raise FactScopeError('fact id collision')
                else:db.execute('INSERT INTO facts VALUES (?,?,?)',(fact.id,fact.revision,fact.model_dump_json()))
            if not candidates:return SourceAttachment(dataset=current,source=updated_source)

            new_version=current.version+1
            updated=current.model_copy(update={'version':new_version,'data_basis':'user_uploaded'})
            db.execute('UPDATE datasets SET current_version=?,body=? WHERE id=?',(new_version,updated.model_dump_json(),dataset_id))
            db.execute('INSERT INTO dataset_snapshots VALUES (?,?,?)',(dataset_id,new_version,updated.model_dump_json()))
            db.execute('INSERT INTO dataset_sources(dataset_id,version,source_id) SELECT dataset_id,?,source_id FROM dataset_sources WHERE dataset_id=? AND version=?',(new_version,dataset_id,current.version))
            db.execute('INSERT INTO dataset_facts(dataset_id,version,fact_id,revision) SELECT dataset_id,?,fact_id,revision FROM dataset_facts WHERE dataset_id=? AND version=?',(new_version,dataset_id,current.version))
            for fact in candidates:db.execute('INSERT INTO dataset_facts VALUES (?,?,?,?)',(dataset_id,new_version,fact.id,fact.revision))
        return SourceAttachment(dataset=updated,source=updated_source)
    def get_current_fact_context(self,fact_id):
        with self.connect() as db:
            rows=db.execute('SELECT d.body,f.body FROM datasets d JOIN dataset_facts df ON df.dataset_id=d.id AND df.version=d.current_version JOIN facts f ON f.id=df.fact_id AND f.revision=df.revision WHERE df.fact_id=?',(fact_id,)).fetchall()
        if not rows:return None
        if len(rows)!=1:raise FactScopeError('fact belongs to multiple current datasets')
        return Dataset.model_validate_json(rows[0][0]),Fact.model_validate_json(rows[0][1])
    def correct_fact(self,dataset_id,expected_revision,updated,reason):
        with self.connect() as db:
            db.execute('BEGIN IMMEDIATE')
            dataset_row=db.execute('SELECT body FROM datasets WHERE id=?',(dataset_id,)).fetchone()
            if dataset_row is None:raise FactNotFoundError()
            current=Dataset.model_validate_json(dataset_row[0])
            row=db.execute('SELECT f.body FROM dataset_facts df JOIN facts f ON f.id=df.fact_id AND f.revision=df.revision WHERE df.dataset_id=? AND df.version=? AND df.fact_id=?',(dataset_id,current.version,updated.id)).fetchone()
            if row is None:raise FactNotFoundError()
            previous=Fact.model_validate_json(row[0])
            if previous.revision!=expected_revision:raise FactRevisionConflictError(previous.revision)
            if updated.revision!=previous.revision+1:raise FactRevisionConflictError(previous.revision)
            if self._fact_key(updated)!=self._fact_key(previous) or updated.period_start!=previous.period_start or updated.period_kind!=previous.period_kind:
                raise FactScopeError('correction changed fact identity')
            for evidence_id in updated.evidence_ids:
                evidence_row=db.execute('SELECT source_id FROM evidence WHERE id=?',(evidence_id,)).fetchone()
                if evidence_row is None:raise EvidenceScopeError('evidence not found')
                linked=db.execute('SELECT 1 FROM dataset_sources WHERE dataset_id=? AND version=? AND source_id=?',(dataset_id,current.version,evidence_row[0])).fetchone()
                if linked is None:raise EvidenceScopeError('evidence source is outside current dataset')
            db.execute('INSERT INTO facts VALUES (?,?,?)',(updated.id,updated.revision,updated.model_dump_json()))
            new_version=current.version+1
            next_dataset=current.model_copy(update={'version':new_version})
            db.execute('UPDATE datasets SET current_version=?,body=? WHERE id=?',(new_version,next_dataset.model_dump_json(),dataset_id))
            db.execute('INSERT INTO dataset_snapshots VALUES (?,?,?)',(dataset_id,new_version,next_dataset.model_dump_json()))
            db.execute('INSERT INTO dataset_sources(dataset_id,version,source_id) SELECT dataset_id,?,source_id FROM dataset_sources WHERE dataset_id=? AND version=?',(new_version,dataset_id,current.version))
            db.execute('INSERT INTO dataset_facts(dataset_id,version,fact_id,revision) SELECT dataset_id,?,fact_id,revision FROM dataset_facts WHERE dataset_id=? AND version=? AND fact_id<>?',(new_version,dataset_id,current.version,updated.id))
            db.execute('INSERT INTO dataset_facts VALUES (?,?,?,?)',(dataset_id,new_version,updated.id,updated.revision))
            db.execute('INSERT INTO fact_corrections VALUES (?,?,?,?,?,?,?)',(str(uuid4()),updated.id,previous.revision,updated.revision,reason,'local',datetime.now(timezone.utc).isoformat()))
        return updated
    def source_path(self,id):
        with self.connect() as db:row=db.execute('SELECT content_path FROM sources WHERE id=?',(id,)).fetchone()
        if not row:return None
        stored=row[0]
        if stored.startswith('upload:'):
            p=(self.upload_root/stored.removeprefix('upload:')).resolve();allowed=self.upload_root.resolve()
        else:
            p=(self.root/stored).resolve();allowed=(self.root/'data/raw').resolve()
        if not p.is_relative_to(allowed):raise RuntimeError('unsafe source path')
        return p
    def seed(self):
        manifest=json.loads((self.root/'data/source_manifest.json').read_text(encoding='utf-8'))
        facts=[Fact.model_validate(v) for v in json.loads((self.root/'data/fixtures/facts.json').read_text(encoding='utf-8'))]
        evidence=[Evidence.model_validate(v) for v in json.loads((self.root/'data/fixtures/evidence.json').read_text(encoding='utf-8'))]
        for s in manifest:
            if hashlib.sha256((self.root/s['path']).read_bytes()).hexdigest()!=s['sha256']:raise RuntimeError('fixture source hash mismatch')
        d=Dataset(id='demo-catl-2025',name='宁德时代核对样本（非自动提取）',company='CATL',year=2025,version=1,source_ids=[s['id'] for s in manifest],created_at='2026-09-30T14:27:25+00:00',data_basis='reviewed_fixture')
        with self.connect() as db:
            if db.execute('SELECT 1 FROM datasets WHERE id=?',(d.id,)).fetchone():return
            db.execute('INSERT INTO datasets VALUES (?,?,?,?)',(d.id,'local',1,d.model_dump_json()));db.execute('INSERT INTO dataset_snapshots VALUES (?,?,?)',(d.id,1,d.model_dump_json()))
            for s in manifest:
                body=dict(id=s['id'],filename=Path(s['path']).name,sha256=s['sha256'],media_type='application/pdf',page_count=s['pages'],url=s['url'],published_date=s['published_date'],parse_status='parsed',data_basis='reviewed_fixture')
                db.execute('INSERT INTO sources VALUES (?,?,?,?)',(s['id'],s['sha256'],s['path'],json.dumps(body,ensure_ascii=False)));db.execute('INSERT INTO dataset_sources VALUES (?,?,?)',(d.id,1,s['id']))
            for f in facts:
                db.execute('INSERT INTO facts VALUES (?,?,?)',(f.id,f.revision,f.model_dump_json()));db.execute('INSERT INTO dataset_facts VALUES (?,?,?,?)',(d.id,1,f.id,f.revision))
            for e in evidence:db.execute('INSERT INTO evidence VALUES (?,?,?)',(e.id,e.source_id,e.model_dump_json()))
