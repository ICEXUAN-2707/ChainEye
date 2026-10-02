# 链眼 宁德时代 R2 上传块

R1基线冻结日期：2026-09-30。两名开发者从同一契约开始，Codex负责后端，Claude负责前端。
先读 `docs/06_严格交叉自检.md` 和 `validation/R1验收记录.md`，再读PRD、Spec及各自 `tasks/` 任务书。

## 实际完成范围
30条财报标注再次核对原件，未发现数值错误。R0的44项检查保留，不能视为自动提取准确率。
R1实现SQLite迁移与持久化、版本快照读取、核对样本seed、事实筛选、来源与证据查看、PDF服务、统一错误、生成契约及React工作台。
45项测试、干净Python环境安装、前端构建及真实HTTP联调通过。详细命令与限制见验收记录。
R2第一块已实现真实PDF上传、文件校验、SHA256去重、不可变数据包版本和来源读取。解析提取、人工更正、HTTP情景计算、Agent、DeepSeek和报告尚未实现；相应写入口返回501。纯Decimal计算内核可测试。
价格仅一个日期两个不同系列，不能做历史均价或回测。标注仍是助手复核样本，团队人工签核待完成。

## 安装与启动
Python 3.12、Node 22或24；本轮实测Linux。进入项目根：
```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -r backend/requirements.lock
python tools/start_backend.py
```
另一个终端：
```bash
cd frontend
npm ci
npm run dev
```
访问 http://127.0.0.1:5173 ，API在 http://127.0.0.1:8000 ，接口文档 `/docs`。
Windows PowerShell激活 `.venv\Scripts\Activate.ps1`；运行下面测试时设置 `$env:PYTHONPATH="backend/src"`。Windows尚未实机验证。
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

## R2 PDF上传联调

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

响应沿用生成契约`SourceAttachment`。前端必须用响应中的`dataset.version`刷新读取；同数据包同哈希重复上传不增加版本。限制为30 MiB、500页、每数据包5个来源，只接受未加密PDF。文本PDF状态是`queued`，扫描件是`needs_review`；当前块不生成候选事实，也不允许显示为提取或人工复核成功。

## 协作与交付
`tasks/Codex_后端任务.md` 与 `tasks/Claude_前端任务.md`规定边界及R2要求。两人先各自复现R1，互审一个关键流程，再进入上传与复核闭环。
本轮是可运行基础包，最终产品交付及R2—R6门槛见 `docs/03_轮次任务与验收.md`。包内不含密钥、node_modules和本地数据库。

## 目录
- backend/: 分层源码、迁移及精确依赖锁。
- frontend/: React工作台、生成客户端类型、npm锁文件。
- contracts/: OpenAPI 3.1及JSON Schema。
- data/: 原始财报、来源哈希、30条标注与证据、价格样本。
- docs/、tasks/: 需求、规格、严格自检及开发任务。
- tests/、tools/、validation/: 可复现检查、结果和验收记录。

公开PDF保留来源，第三方设计参考没有复制项目代码。生产部署、连续价格权限和赛事最终要求仍按各轮验收核实。
