# Phase 2 当前实现基线

核查日期：2026-10-08  
基线提交：`c7642185458a37719ca210a08b7cd8e18f3e129a`  
核查分支：`chore/p2-agent-baseline`  
执行环境：Windows 11 10.0.26200、Python 3.12.10、Node.js 24.13.0、npm 11.6.2、Intel i5-13500H、约 32 GiB RAM。

本记录描述代码现状，不把计划、人工待办或未执行能力写成已完成。Phase 1 的人工财务签核、第二位开发者独立复现和 PR 互审仍须由实际执行者确认。

## 能力核查

|能力|状态|真实实现位置|当前边界|
|---|---|---|---|
|Dataset 与不可变版本|implemented|`adapters/sqlite.py`、`domain/datasets.py`|Dataset、Fact revision、Run 均绑定显式版本；当前仅本机 owner `local`|
|PDF 上传与原件校验|implemented|`application/source_upload.py`、`api/app.py`|30 MiB、500 页、每数据包 5 份、SHA256 去重；仅 PDF|
|文本层解析与候选事实|partial|`adapters/pymupdf.py`、`application/extraction.py`|只适配宁德时代 2024/2025 冻结版式；扫描页明确 `needs_review`，无 OCR|
|人工复核|implemented|`application/fact_review.py`、`PATCH /api/v1/facts/{id}`|更正生成新 revision 与 Dataset version；自动流程无权写 `verified`|
|确定性财务计算|implemented|`application/financials.py`、`domain/financials.py`|六项冻结公式；缺输入返回不可计算，不由模型计算|
|产业链情景|implemented|`application/scenarios.py`、`domain/scenario.py`|静态毛利情景 `static-gross-profit-v1`；不是净利润预测|
|Run 编排|partial|`application/runs.py`|真实执行 plan→extract→validate→finance→research→scenario→verify→report，但节点、预算和恢复规则仍集中在一个服务类中|
|白名单 Tool|partial|`application/run_tools.py`|已有 6 个快照受限工具、90 秒预算和输入/输出哈希；没有统一 ToolSpec/Registry|
|Prompt|partial|`application/runs.py` 的 `r4-claims-v3`|有版本号和结构化输出约束，但正文内联，未独立文件化、未记录内容 SHA256|
|Skill|missing|无运行时目录或注册表|没有能被编排器加载并记录版本的 Skill；不能以纯说明文档冒充实现|
|LLM 适配器|partial|`adapters/deepseek.py`|支持 DeepSeek JSON claims，默认 `deepseek-flash`；真实调用依赖未提交的密钥，CI 不调用付费接口|
|回放|implemented|`application/runs.py`|复用同一数据快照上的已结束 Run，不调用模型；回放来自真实保存结果，不是 mock|
|Claim 校验|implemented|`application/run_tools.py`、`application/runs.py`|校验引用存在性、作用域和数字支持；语义支持仍需人工复核|
|Run 事件|partial|`run_events` 表、`GET /api/v1/runs/{id}/events`|节点和工具调用可追踪，工具事件含哈希；缺统一 JSONL 运维日志、脱敏策略和导出命令|
|报告|implemented|`application/reports.py`、`reporting/**`|完成 Run 可导出 JSON/Markdown/PDF；PDF 有 CJK 字体发现与子集嵌入|
|MCP|missing|无 `chain_eye.mcp`|没有 stdio server、资源、MCP 工具或协议测试|
|第二企业|missing|无 company profile|不得把 CATL 固定版式通过字符串替换伪装成多企业支持|
|OCR|missing|无 OCR port/adapter|扫描和混合 PDF 不进入真实 OCR|
|原生复现|partial|`README.md`、`tools/start_backend.py`、`.github/workflows/ci.yml`|现有 Ubuntu CI 与 Windows 本地门禁；缺跨平台 preflight/bootstrap/start_all、MCP smoke、回放复现和 trace 导出|
|Docker/Compose|out_of_scope|无实现|团队已决定本阶段不做容器打包；以 Windows 11 与 Ubuntu 原生复现替代|

## 现有 Agent 链路映射

```text
Run API
  -> SQLite 单 worker 领取任务
  -> plan
  -> get_facts / search_documents / get_evidence
  -> compute_financials / compute_scenario
  -> DeepSeek claims（可失败、可回放）
  -> validate_claims + 数字支持检查
  -> Report 快照与 JSON/Markdown/PDF
```

这是一条真实、受约束的 Agent 链路，但还不是比赛交付所需的显式 Agent Kernel：缺少可导出的图、节点声明、Skill 注册、Prompt 内容哈希和 MCP 入口。后续改造必须迁移并复用现有实现，不能再建平行 Run、Tool 或 DTO。

## 依赖与生成源

- Python 依赖锁：`backend/requirements.lock`，SHA256 `323A85F8581D3C7BDE5F0ED9BBA46B51358691BAE75667AE8F7EE594124ADFB4`。
- 前端依赖锁：`frontend/package-lock.json`，SHA256 `1E8809E1AD3478D32196FE49E572EC837F4D6A8705A40D977AFEB214B94CBA09`。
- HTTP 契约版本：OpenAPI `0.4.0`；权威源为后端路由、HTTP DTO 与领域模型。
- 生成物：`contracts/**` 与 `frontend/src/api/generated.ts`，仅由 `tools/export_contracts.py` 和 `tools/generate_ts.py` 更新。
- 当前数据库迁移：`001_initial.sql`、`002_unique_source_hash.sql`。

## 当前阶段结论

可以开始只改变内部结构且保持 HTTP 契约不变的 Agent Registry 与 Orchestrator 改造。MCP 只能在统一 Registry 落地后接入，且 MVP 对外只读。第二企业与 OCR 必须等待 Agent Kernel、MCP 和原生复现关口通过后再开发。

## 本分支自动化结果

- 后端：141 项测试通过，220.321 秒。
- 基线：30 条 fixture、4 项毛利检查、文件哈希与契约引用通过；不代表未见材料提取准确率。
- 契约：OpenAPI/Schema `0.4.0` 与 TypeScript 重新生成后零漂移。
- 前端：`npm ci` 在停止本项目遗留 Vite/esbuild 进程后通过；28 项测试、TypeScript 与 Vite 7.3.7 构建通过，44 个模块转换。
- 冒烟：真实本地 HTTP、前端 HTML、CORS、上传、15 条候选、复核版本、重复来源、9 条情景计算、Run/事件边界通过；未配置密钥时 Run 真实返回 `partial + MODEL_UNAVAILABLE`，报告返回 `REPORT_NOT_READY`。
- 未执行：本分支没有真实 DeepSeek 付费调用、Ubuntu 本地机执行、MCP smoke 或浏览器人工验收；这些能力或检查尚未落地/执行。
