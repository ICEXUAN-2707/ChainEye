# 链眼 宁德时代 R5 可追溯报告

R1基线冻结日期：2026-09-30。两名开发者从同一契约开始，Codex负责后端，Claude负责前端。
文档总入口为 `docs/README.md`。Phase 1 的历史PRD、Spec与交叉自检统一归档在 `docs/Phase_1/`；Phase 2 的设计资料统一放在 `docs/Phase_2/`。

## 实际完成范围
30条财报标注再次核对原件，未发现数值错误。R0的44项检查保留，不能视为自动提取准确率。
R1实现SQLite迁移与持久化、版本快照读取、核对样本seed、事实筛选、来源与证据查看、PDF服务、统一错误、生成契约及React工作台。
45项测试、干净Python环境安装、前端构建及真实HTTP联调通过。详细命令与限制见验收记录。
R2后端已在上传块之上实现PyMuPDF文本层解析、限定版式候选事实提取、PDF页码/bbox证据定位及人工更正的revision/version原子事务。自动候选只写`extracted`、`missing`或`conflict`，不会写`verified`。R3已启用六项确定性财务规则、条件情景及对应前端。R4后端启用冻结的Run创建、查询、事件游标和恢复接口：Run绑定不可变数据快照，由单工作线程领取SQLite作业，只能调用六个白名单工具；财务与情景数值仍由程序计算，模型候选Claim必须经过实际可见引用的存在性与数字对照检查，缺证据或引用不支持的数字会降级。回放复用已校验产物且不调用模型。R5后端已启用既有报告接口，完成的Run原子落库一份结构化Report，并从该记录导出JSON、Markdown和PDF；报告保留事实revision、计算输入、假设、证据与限制，证据不足或非法引用Claim不进入正文。未完成Run返回`REPORT_NOT_READY`，不会输出空报告。
价格仅一个日期两个不同系列，不能做历史均价或回测。标注仍是助手复核样本，团队人工签核待完成。

## 安装与启动
Python 3.12、Node 22或24；本轮已在Linux及Windows PowerShell运行自动化检查。进入项目根：
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.lock
python tools/start_backend.py
```
`tools/start_backend.py`会显式加载仓库根目录的`.env`，但不会覆盖启动进程中已经设置的同名环境变量。复制`.env.example`为`.env`后填写`DEEPSEEK_API_KEY`即可；默认模型为`deepseek-flash`，密钥和`.env`不得提交。

DeepSeek 的真实调用链为：`tools/start_backend.py` 加载 `.env` → `api/app.py` 创建 `DeepSeekAdapter` → live Run 的 research 节点调用 `llm.generate()` → `adapters/deepseek.py` 向 `https://api.deepseek.com/chat/completions` 发起 POST。只有 live Run 到达 research 节点且存在密钥时才产生真实请求；replay 不调用模型，`tools/smoke_local.py` 会主动移除密钥并验证 `MODEL_UNAVAILABLE` 边界。官方 Chat Completions 与 JSON Output 文档当前均列出 `deepseek-flash`。本地无费用验证可运行 `python -m unittest tests.test_r4_runs.DeepSeekBoundary -v`；该测试 mock HTTP，不证明密钥、余额或线上服务可用。真实验证必须由人工配置密钥后创建 live Run，并在 Run events 中核对 `llm_call` 的 provider、model、request_id、usage、实现摘要与状态；真实调用可能产生费用，不进入普通 CI。

另一个终端：
```bash
cd frontend
npm ci
npm run dev
```
访问 http://127.0.0.1:5173 ，API在 http://127.0.0.1:8000 ，接口文档 `/docs`。
Windows PowerShell激活 `.venv\Scripts\Activate.ps1`；运行下面测试时设置 `$env:PYTHONPATH="backend/src"`。Windows已验证全量测试、构建和真实本地HTTP冒烟；可见浏览器界面仍需人工复核。
只允许本机访问；R1不能直接部署公网。SQLite保存在 `.runtime/`，删除该目录会清除本地数据，不影响打包原件。

## 复核与契约生成
```bash
PYTHONPATH=backend/src python -m unittest discover -s tests -v
PYTHONPATH=backend/src python tools/verify_baseline.py
PYTHONPATH=backend/src python tools/export_contracts.py
python tools/generate_ts.py
npm run build --prefix frontend
python tools/smoke_local.py
```
单一来源是后端路由、DTO及domain模型；`contracts/openapi.json`、Schema、`frontend/src/api/generated.ts`均为生成产物。不得手改第二套类型。
v0.2包含破坏性契约收紧，禁止与v0.1客户端混用。金额为人民币元十进制字符串；原文千元保留。所有财务结果由后端计算。

## R2 PDF上传与复核联调

先创建数据包，再以`multipart/form-data`上传。`file`必填，`url`和`published_date`可选：

```bash
curl -X POST http://127.0.0.1:8000/api/v1/datasets \
  -H "Content-Type: application/json" \
  -d '{"name":"上传测试","company":"CATL","year":2025}'

curl -X POST http://127.0.0.1:8000/api/v1/datasets/<dataset_id>/sources \
  -F "file=@report.pdf;type=application/pdf" \
  -F "url=https://example.com/report.pdf" \
  -F "published_date=2026-09-30"
```

响应沿用生成契约`SourceAttachment`，返回上传及同步确定性提取完成后的最新数据包版本。来源关联与新增候选事实分别形成不可变快照，因此首次支持的年报上传可能连续增加两个版本；前端必须始终使用响应中的`dataset.version`读取事实。同数据包同哈希重复上传不增加版本。限制为30 MiB、500页、每数据包5个来源，只接受未加密PDF；扫描件或不受支持的版式为`needs_review`。

当前确定性提取器只支持仓库规格冻结的宁德时代2024/2025文本层年报版式，要求同时识别报告年份、表头、行名、千元单位及合并口径。其他公司、年份、版式和扫描件不猜测数值，也不启用OCR或LLM。人工复核继续使用既有`PATCH /api/v1/facts/{id}`契约；`expected_revision`冲突返回409，更正生成新Fact revision和Dataset版本，旧快照保持可读。

## 协作与交付
`tasks/Codex_后端任务.md` 与 `tasks/Claude_前端任务.md`规定边界及R2要求。两人先各自复现R1，互审一个关键流程，再进入上传与复核闭环。
本轮是可运行基础包，Phase 1 产品交付及R2—R6门槛见 `docs/Phase_1/03_轮次任务与验收.md`。包内不含密钥、node_modules和本地数据库。

## 目录
- backend/: 分层源码、迁移及精确依赖锁。
- frontend/: React工作台、生成客户端类型、npm锁文件。
- contracts/: OpenAPI 3.1及JSON Schema。
- data/: 原始财报、来源哈希、30条标注与证据、价格样本。
- docs/Phase_1/：第一阶段需求、规格、交叉自检与协作记录。
- docs/Phase_2/：第二阶段已确认的PRD、Spec、任务与验收模板；尚未实现的能力不得写成现状。
- tasks/：Phase 1 历史开发任务书。
- tests/、tools/、validation/: 可复现检查、结果和验收记录。

公开PDF保留来源，第三方设计参考没有复制项目代码。生产部署、连续价格权限和赛事最终要求仍按各轮验收核实。
