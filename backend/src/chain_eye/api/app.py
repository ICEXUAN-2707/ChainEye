import os
import tempfile
from pathlib import Path
from uuid import uuid4
from typing import Annotated, Literal
from fastapi import FastAPI, Header, Query, UploadFile, File, Form, Request
from fastapi.responses import JSONResponse, FileResponse
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from chain_eye.api.dto import *
from chain_eye.domain.contracts import ScenarioRequest,ScenarioResult,Evidence,Calculation
from chain_eye.adapters.sqlite import SQLiteRepository
from chain_eye.application.errors import AppError
from chain_eye.application.source_upload import MAX_PDF_BYTES,SourceUploadService,sha256_file
from chain_eye.application.extraction import ExtractionService
from chain_eye.application.fact_review import FactReviewService
from chain_eye.application.scenarios import ScenarioExecutionService

ROOT=Path(__file__).resolve().parents[4]
RESPONSES={n:{'model':ErrorResponse,'description':t} for n,t in [(403,'local access only'),(404,'not found'),(409,'conflict'),(422,'invalid input'),(429,'budget exceeded'),(500,'internal failure'),(501,'not implemented in current slice'),(503,'provider unavailable')]}

def create_app(db_path=None,seed=True,upload_dir=None):
    if os.getenv('CHAIN_EYE_MODE','local')!='local': raise RuntimeError('R1 supports local mode only; public authentication not implemented')
    repo=SQLiteRepository(db_path or os.getenv('CHAIN_EYE_DB',str(ROOT/'.runtime/chain_eye.sqlite')),ROOT,upload_dir)
    if seed:repo.seed()
    uploader=SourceUploadService(repo);extraction=ExtractionService(repo);review=FactReviewService(repo);scenarios=ScenarioExecutionService(repo)
    app=FastAPI(title='Chain Eye API',version='0.2.0',description='R3 data, review, deterministic financial calculation, and conditional scenario workflow. Agent and report workflows are not implemented.')
    app.state.repository=repo
    app.add_middleware(CORSMiddleware,allow_origins=['http://localhost:5173','http://127.0.0.1:5173'],allow_methods=['GET','POST','PATCH'],allow_headers=['Content-Type','Idempotency-Key'],allow_credentials=False)
    def error(code,message,status,request_id,details=None,retryable=False):
        return JSONResponse(status_code=status,content=ErrorResponse(error=ErrorBody(code=code,message=message,details=details or {},retryable=retryable,request_id=request_id)).model_dump(mode='json'))
    @app.middleware('http')
    async def local_guard(request:Request,call_next):
        rid=str(uuid4());request.state.request_id=rid
        host=request.url.hostname;client=request.client.host if request.client else None
        if host not in ('localhost','127.0.0.1','::1') or client not in ('127.0.0.1','::1'):
            return error('LOCAL_ONLY','R1仅限本机访问',403,rid)
        origin=request.headers.get('origin')
        if origin and origin not in ('http://localhost:5173','http://127.0.0.1:5173','http://localhost:8000','http://127.0.0.1:8000'):
            return error('LOCAL_ONLY','Origin未允许',403,rid)
        response=await call_next(request);response.headers['X-Request-ID']=rid;return response
    @app.exception_handler(AppError)
    async def app_error(request,exc):return error(exc.code,exc.message,exc.status,request.state.request_id,exc.details,exc.retryable)
    @app.exception_handler(RequestValidationError)
    async def validation_error(request,exc):return error('INVALID_INPUT','请求未通过契约校验',422,request.state.request_id,{'fields':[{'loc':list(e['loc']),'message':e['msg'],'type':e['type']} for e in exc.errors()]})
    @app.exception_handler(StarletteHTTPException)
    async def http_error(request,exc):return error('NOT_FOUND' if exc.status_code==404 else 'HTTP_ERROR','资源不存在' if exc.status_code==404 else 'HTTP请求失败',exc.status_code,request.state.request_id)
    @app.exception_handler(Exception)
    async def unexpected(request,exc):return error('INTERNAL_ERROR','内部错误，请凭request_id检查服务日志',500,getattr(request.state,'request_id',str(uuid4())))
    def required_dataset(id,version=None):
        d=repo.get_dataset(id,version)
        if not d:raise AppError('NOT_FOUND','数据包或版本不存在',404)
        return d
    def required(table,id):
        v=repo.get(table,id)
        if not v:raise AppError('NOT_FOUND','资源不存在',404)
        return v
    def pending(round):raise AppError('NOT_IMPLEMENTED',f'该能力计划在{round}实现，当前交付块未执行该操作',501)
    @app.get('/health',operation_id='health')
    def health():return {'status':'ok','stage':'R3','mode':'local','schema_version':'0.2.0','data_basis':'reviewed_fixture_and_user_upload'}
    @app.post('/api/v1/datasets',response_model=Dataset,status_code=201,responses=RESPONSES,operation_id='createDataset')
    def create_dataset(body:DatasetCreate):return repo.create(body)
    @app.get('/api/v1/datasets',response_model=DatasetCollection,responses=RESPONSES,operation_id='listDatasets')
    def list_datasets(offset:int=Query(default=0,ge=0),limit:int=Query(default=50,ge=1,le=200)):
        items,next_offset=repo.list_datasets(offset,limit);return DatasetCollection(items=items,next_offset=next_offset)
    @app.get('/api/v1/datasets/{id}',response_model=Dataset,responses=RESPONSES,operation_id='getDataset')
    def get_dataset(id:str,version:int|None=Query(default=None,ge=1)):return required_dataset(id,version)
    @app.post('/api/v1/datasets/{id}/sources',response_model=SourceAttachment,status_code=201,responses=RESPONSES,operation_id='uploadSource')
    async def upload_source(id:str,file:UploadFile=File(),url:str|None=Form(default=None),published_date:str|None=Form(default=None)):
        required_dataset(id)
        staging=repo.upload_root.parent/'upload-staging';staging.mkdir(parents=True,exist_ok=True)
        staged=None
        try:
            with tempfile.NamedTemporaryFile(dir=staging,suffix='.upload',delete=False) as target:
                staged=Path(target.name);size=0
                while chunk:=await file.read(1024*1024):
                    size+=len(chunk)
                    if size>MAX_PDF_BYTES:raise AppError('INVALID_INPUT','PDF不能超过30 MiB',422,details={'reason':'FILE_TOO_LARGE','max_bytes':MAX_PDF_BYTES})
                    target.write(chunk)
            attachment=uploader.execute(id,staged,file.filename,file.content_type,url,published_date)
            return extraction.execute(attachment.dataset.id,attachment.source.id)
        finally:
            await file.close()
            if staged is not None and staged.exists():staged.unlink()
    @app.get('/api/v1/datasets/{id}/facts',response_model=FactCollection,responses=RESPONSES,operation_id='listFacts')
    def list_facts(id:str,version:int=Query(ge=1),status:Literal['extracted','needs_review','verified','missing','conflict']|None=None,segment:Literal['group','power_battery','energy_storage']|None=None):
        d=required_dataset(id,version);items=[f for f in repo.facts(id,version) if (status is None or f.status==status) and (segment is None or f.segment==segment)]
        return FactCollection(dataset_id=id,dataset_version=d.version,items=items)
    @app.patch('/api/v1/facts/{id}',response_model=Fact,responses=RESPONSES,operation_id='correctFact')
    def correct_fact(id:str,body:FactCorrection):return review.correct(id,body)
    @app.post('/api/v1/runs',response_model=Run,status_code=202,responses=RESPONSES,operation_id='createRun')
    def create_run(body:RunCreate,idempotency_key:Annotated[str,Header(min_length=8,max_length=128,alias='Idempotency-Key')]):
        required_dataset(body.dataset_id,body.dataset_version);pending('R4')
    @app.get('/api/v1/runs/{id}',response_model=Run,responses=RESPONSES,operation_id='getRun')
    def get_run(id:str):return required('runs',id)
    @app.get('/api/v1/runs/{id}/events',response_model=EventCollection,responses=RESPONSES,operation_id='getRunEvents')
    def events(id:str,after_seq:int=Query(default=0,ge=0),limit:int=Query(default=100,ge=1,le=200)):
        required('runs',id);pending('R4')
    @app.post('/api/v1/runs/{id}/resume',response_model=Run,status_code=202,responses=RESPONSES,operation_id='resumeRun')
    def resume(id:str,body:ResumeRequest):required('runs',id);pending('R4')
    @app.post('/api/v1/scenarios',response_model=ScenarioResult,status_code=201,responses=RESPONSES,operation_id='createScenario')
    def scenario(body:ScenarioRequest,idempotency_key:Annotated[str,Header(min_length=8,max_length=128,alias='Idempotency-Key')]):
        return scenarios.execute(body,idempotency_key)
    @app.get('/api/v1/evidence/{id}',response_model=Evidence,responses=RESPONSES,operation_id='getEvidence')
    def evidence(id:str):return required('evidence',id)
    @app.get('/api/v1/calculations/{id}',response_model=Calculation,responses=RESPONSES,operation_id='getCalculation')
    def calculation(id:str):return required('calculations',id)
    @app.get('/api/v1/sources/{id}',response_model=Source,responses=RESPONSES,operation_id='getSource')
    def source(id:str):return required('sources',id)
    @app.get('/api/v1/sources/{id}/content',response_class=FileResponse,responses={**RESPONSES,200:{'description':'Original file','content':{'application/pdf':{'schema':{'type':'string','format':'binary'}},'text/csv':{'schema':{'type':'string','format':'binary'}}}}},operation_id='getSourceContent')
    def content(id:str):
        s=required('sources',id);p=repo.source_path(id)
        if not p.exists():raise AppError('NOT_FOUND','来源原件不存在',404)
        if sha256_file(p)!=s['sha256']:raise AppError('SOURCE_HASH_MISMATCH','原件与保存的证据哈希不一致',409)
        return FileResponse(p,media_type=s['media_type'],filename=s['filename'],content_disposition_type='inline')
    @app.get('/api/v1/runs/{id}/report',response_model=Report,responses={**RESPONSES,200:{'content':{'application/json':{'schema':{'$ref':'#/components/schemas/Report'}},'text/markdown':{'schema':{'type':'string','format':'binary'}},'application/pdf':{'schema':{'type':'string','format':'binary'}}}}},operation_id='getReport')
    def report(id:str,format:Literal['json','markdown','pdf']='json'):required('runs',id);pending('R5')
    return app
