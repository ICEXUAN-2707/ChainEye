import sqlite3, json, hashlib
from contextlib import contextmanager
from pathlib import Path
from datetime import datetime,timezone
from uuid import uuid4
from chain_eye.domain.datasets import Dataset,DatasetCreate
from chain_eye.domain.contracts import Fact,Evidence

class SQLiteRepository:
    def __init__(self,path,project_root):
        self.path=Path(path);self.root=Path(project_root);self.path.parent.mkdir(parents=True,exist_ok=True)
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
    def facts(self,id,version):
        with self.connect() as db:
            rows=db.execute('SELECT f.body FROM dataset_facts df JOIN facts f ON f.id=df.fact_id AND f.revision=df.revision WHERE df.dataset_id=? AND df.version=? ORDER BY f.id',(id,version)).fetchall()
        return [Fact.model_validate_json(row[0]) for row in rows]
    def source_path(self,id):
        with self.connect() as db:row=db.execute('SELECT content_path FROM sources WHERE id=?',(id,)).fetchone()
        if not row:return None
        p=(self.root/row[0]).resolve()
        if not p.is_relative_to((self.root/'data/raw').resolve()):raise RuntimeError('unsafe source path')
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
