# 链眼 P2.1 多企业证据约束研究

R1基线冻结日期：2026-09-30。两名开发者从同一契约开始，Codex负责后端，Claude负责前端。
文档总入口为 `docs/README.md`。Phase 1 的历史PRD、Spec与交叉自检统一归档在 `docs/Phase_1/`；Phase 2 的设计资料统一放在 `docs/Phase_2/`。

## 实际完成范围
30条财报标注再次核对原件，未发现数值错误。R0的44项检查保留，不能视为自动提取准确率。
R1实现SQLite迁移与持久化、版本快照读取、核对样本seed、事实筛选、来源与证据查看、PDF服务、统一错误、生成契约及React工作台。
45项测试、干净Python环境安装、前端构建及真实HTTP联调通过。详细命令与限制见验收记录。
R2后端已在上传块之上实现PyMuPDF文本层解析、限定版式候选事实提取、PDF页码/bbox证据定位及人工更正的revision/version原子事务。自动候选只写`extracted`、`missing`或`conflict`，不会写`verified`。R3已启用六项确定性财务规则、条件情景及对应前端。R4后端启用冻结的Run创建、查询、事件游标和恢复接口：Run绑定不可变数据快照，由单工作线程领取SQLite作业，只能调用六个白名单工具；财务与情景数值仍由程序计算，模型候选Claim必须经过实际可见引用的存在性与数字对照检查，缺证据或引用不支持的数字会降级。回放复用已校验产物且不调用模型。R5后端已启用既有报告接口，完成的Run原子落库一份结构化Report，并从该记录导出JSON、Markdown和PDF；报告保留事实revision、计算输入、假设、证据与限制，证据不足或非法引用Claim不进入正文。未完成Run返回`REPORT_NOT_READY`，不会输出空报告。
价格仅一个日期两个不同系列，不能做历史均价或回测。标注仍是助手复核样本，团队人工签核待完成。

G6 后端在 R5 基础上新增 CATL/亿纬锂能版本化企业 profile、文档身份候选与人工确认、五模块能力矩阵和公司范围门禁；身份冲突会阻止 Run/Scenario，公司更正生成新 Dataset 快照且旧快照保持可读。HTTP/OpenAPI 版本为 `0.5.0`。PR #24 已适配 `CNY_yuan` 原始单位展示、双向编辑换算和服务端省略原值时的一比一推导；本地完整门禁与最新分支远端 CI workflow 已通过。可见浏览器人工复核、第二位开发者独立复现、真实互审及合并仍须由实际执行者确认，因此合并前不把 G6 记为正式交付。

## 安装与启动
Python 3.12、Node 24；本轮已在Linux及Windows PowerShell运行自动化检查。进入项目根：
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.lock
python tools/start_backend.py
```
`tools/start_backend.py`会显式加载仓库根目录的`.env`，但不会覆盖启动进程中已经设置的同名环境变量。复制`.env.example`为`.env`后填写`DEEPSEEK_API_KEY`即可；默认模型为`deepseek-flash`，密钥和`.env`不得提交。

DeepSeek 的真实调用链为：`tools/start_backend.py` 加载 `.env` → `api/app.py` 创建 `DeepSeekAdapter` → live Run 的 research 节点调用 `llm.generate()` → `adapters/deepseek.py` 向 `https://api.deepseek.com/chat/completions` 发起 POST。只有 live Run 到达 research 节点且存在密钥时才产生真实请求；replay 不调用模型，`tools/smoke_local.py` 会主动移除密钥并验证 `MODEL_UNAVAILABLE` 边界。官方 Chat Completions 与 JSON Output 文档当前均列出 `deepseek-flash`。本地无费用验证可运行 `python -m unittest tests.test_r4_runs.DeepSeekBoundary -v`；该测试 mock HTTP，不证明密钥、余额或线上服务可用。真实验证必须由人工配置密钥后创建 live Run，并在 Run events 中核对 `llm_call` 的 provider、model、request_id、usage、实现摘要与状态；真实调用可能产生费用，不进入普通 CI。

## MCP 只读接口

MCP MVP 使用官方 Python SDK 和 stdio 传输，与 Agent 共用 Tool Registry，不创建第二套业务实现。它只发布 `get_facts`、`get_evidence`、`search_documents`、`get_run_trace` 和 `get_report`；不暴露写操作、任意文件、SQL、shell、网络或模型调用。Dataset 读取必须指定版本，MCP 读取不写入 Run trace，也不会调用 DeepSeek。API 与 MCP 共用 `.runtime/chain_eye.sqlite` 默认路径；MCP 以 SQLite `mode=ro` 和 `query_only` 打开数据库，只校验迁移而不创建目录、数据库或迁移，缺库和版本不兼容会明确失败。外部 Run trace 按事件类型筛选字段，并对嵌套密钥、token、cookie、header 及常见 secret 值模式做防御性脱敏。

```bash
PYTHONPATH=backend/src python -m chain_eye.mcp.server
PYTHONPATH=backend/src python tools/mcp_smoke.py
```

Windows PowerShell 先设置 `$env:PYTHONPATH="backend/src"`。第一条命令由 MCP client 通过 stdio 管理，只读访问已由后端初始化且迁移完整的本地数据库，不自动 seed 演示数据，也不应在 stdout 写入其他日志；第二条会显式创建或复用隔离的 smoke 数据库，然后启动真实子进程，验证初始化、列举、版本化 Dataset/Evidence 读取、Prompt/Skill 元数据与正常退出。传入 `--run-id <已完成Run>` 时另外验证已持久化的 trace 和 report。

## G5 原生复现与结构化日志

G5 固定使用 Python 3.12、Node 24 和 UTF-8，提供 Windows 11 / Ubuntu 共用的原生命令链，不依赖 Docker。首次安装按顺序运行：

```bash
python tools/preflight.py
python tools/bootstrap.py
python tools/start_all.py
```

`preflight.py` 在不修改项目状态的前提下检查解释器、Node/npm、锁文件、依赖状态、运行目录和端口；未安装的项目依赖只给 warning，由 `bootstrap.py` 按锁文件安装并初始化核对样本。`start_all.py` 监督 API 和前端、核对实例 nonce、保存 `.runtime/native-stack/services.json`，普通模式移除凭据类环境变量并强制禁止模型调用；`--live-model` 必须由人工显式提供 `DEEPSEEK_API_KEY`，不得进入普通 CI。Ctrl+C 或 `--verify-only` 会停止两个进程并把状态写成 `stopped`。

无付费回放及 trace 导出：

```bash
python tools/reproduce_core_flow.py --mode replay
python tools/export_run_trace.py --run-id <run_id>
python tools/mcp_smoke.py
```

复现命令在隔离 SQLite 中真实执行一个禁用模型的 live Run；它在确定性计算后以 `MODEL_UNAVAILABLE` 进入 `partial`，随后创建绑定该已保存 Run 的 replay，验证 `model_calls=0` 并明确标记 `saved_run_artifacts_only`。它不伪造 completed/report 成功。导出的 JSONL trace 经 MCP 同一字段白名单和脱敏边界处理，同一 Run 重复导出字节稳定；API、Agent node、Tool 和 Run 生命周期日志具有统一字段、64 KiB 行上限，并移除密钥、Authorization、Cookie、完整环境、二进制正文和无界文本。

## G6 第二企业后端

第二企业冻结为深交所 `300014` 惠州亿纬锂能股份有限公司。官方披露元数据、公告号、哈希、页数和适配/未见样本角色记录在 `data/company_sources.json`；PDF 按需下载到忽略的 `.runtime/company-sources/`，仓库不在缺少明确再分发许可时复制原件。

```bash
PYTHONPATH=backend/src python tools/fetch_company_report.py --report eve-2024-annual-report
PYTHONPATH=backend/src python tools/fetch_company_report.py --report eve-2025-annual-report
PYTHONPATH=backend/src python tools/validate_company_report.py --report eve-2024-annual-report --api-flow
PYTHONPATH=backend/src python tools/validate_company_report.py --report eve-2025-annual-report --api-flow
```

2024 适配材料和 2025 未见迁移材料均为真实文本层年报。验证器检查官方清单哈希、页数、企业/年度识别、13 个目标事实、证据绑定及“原文元值不乘 1000”不变量；`--api-flow` 还执行真实 HTTP 上传、SQLite 快照落库和身份/事实/能力矩阵回读。这些自动检查不是第二位开发者的独立财务准确率签核。

另一个终端：
```bash
cd frontend
npm ci
npm run dev
```
访问 http://127.0.0.1:5173 ，API在 http://127.0.0.1:8000 ，接口文档 `/docs`。
Windows PowerShell激活 `.venv\Scripts\Activate.ps1`；运行下面测试时设置 `$env:PYTHONPATH="backend/src"`。Windows已验证全量测试、构建和真实本地HTTP冒烟；可见浏览器界面仍需人工复核。`tools/smoke_local.py` 会先拒绝已占用的 8000/5173 端口，在临时数据库和上传目录中运行，以启动 nonce 和子进程存活状态确认服务归属，并通过 `CHAIN_EYE_DISABLE_MODEL=1` 强制关闭付费模型；它不会写入默认 `.runtime/chain_eye.sqlite`。
只允许本机访问；R1不能直接部署公网。SQLite保存在 `.runtime/`，删除该目录会清除本地数据，不影响打包原件。

## 复核与契约生成
```bash
PYTHONPATH=backend/src python -m unittest discover -s tests -v
PYTHONPATH=backend/src python tools/verify_baseline.py
PYTHONPATH=backend/src python tools/export_contracts.py
python tools/generate_ts.py
npm run build --prefix frontend
python tools/preflight.py
python tools/bootstrap.py --check
python tools/reproduce_core_flow.py --mode replay
python tools/mcp_smoke.py
python tools/start_all.py --verify-only
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

当前确定性提取器支持仓库规格冻结的宁德时代与亿纬锂能 2024/2025 文本层年报版式，分别保留原文千元与元单位并统一输出人民币元十进制字符串。其他公司、年份、版式和扫描件不猜测数值，也不启用 OCR 或 LLM。人工复核继续使用既有`PATCH /api/v1/facts/{id}`契约；`expected_revision`冲突返回409，更正生成新Fact revision和Dataset版本，旧快照保持可读。

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
