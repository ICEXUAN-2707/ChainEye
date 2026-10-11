# P2 Agent Orchestrator 验收记录

日期：2026-10-09

分支：`feat/p2-agent-orchestrator`

基线：`develop@128f2c7`

状态：本地自动化通过，等待 PR CI、第二位开发者复现和真实互审。

## 实现边界

- 新增版本化 `AgentState`、`GraphSpec`、`NodeSpec`、transition 与 JSON 导出工具。
- live 路径 `plan→extract→validate→finance→research→scenario→verify→report` 和 replay 路径由同一 orchestrator 调度。
- execution manifest 升级为 schema v3，并绑定 graph id/version/spec SHA256；同版本规格变化在 Tool、计算和模型副作用前关闭执行。
- schema v2 历史 Run 映射到冻结的 `chain-eye-r5-compat@manifest-v2`，明确标记为兼容路径，保留 queued live 与 completed replay。
- 清单机制前的 completed/partial Run 使用 `chain-eye-legacy-artifact-replay@no-manifest-v1` 只复制已有产物，报告披露 provenance 不完整；未结束旧 Run fail closed 并返回排空/取消动作。
- 模型绑定新增 `generate()` 实现 ID 与 SHA256；相同 public config 但适配器实现变化时在副作用前拒绝执行。
- 节点事件新增 graph/node 版本、规格哈希、状态、耗时和错误码。恢复策略读取节点 recoverability，并保留研究、财务、情景与报告的既有安全条件。
- 未新增 HTTP DTO、数据库迁移或前端业务修改；模型仍不能写入 `verified`，权威金额仍由确定性 Tool 计算。

## 自动化结果

以下命令均在仓库根目录、项目 `.venv` 与当前分支执行。最终完整回归结果在兼容修复后重新运行；不得用本记录替代 CI 输出。

|检查|命令|真实结果|
|---|---|---|
|后端测试|`$env:PYTHONPATH='backend/src'; .\.venv\Scripts\python.exe -m unittest discover -s tests -v`|171 tests passed，耗时 277.944 秒|
|冻结基线|`$env:PYTHONPATH='backend/src'; .\.venv\Scripts\python.exe tools/verify_baseline.py`|PASS：30 fixture records、4 margin checks、文件哈希与契约引用|
|契约生成与漂移|`tools/export_contracts.py`、`tools/generate_ts.py`、`git diff --exit-code -- contracts frontend/src/api/generated.ts`|通过；OpenAPI/schema 版本仍为 0.4.0，无生成物漂移|
|前端依赖与构建|`npm.cmd ci --prefix frontend; npm.cmd run build --prefix frontend`|通过；28 tests passed，TypeScript 与 Vite build 成功|
|本地纵向 smoke|`$env:PYTHONPATH='backend/src'; .\.venv\Scripts\python.exe tools/smoke_local.py`|passed；真实 HTTP、上传、15 条候选、复核、9 项情景计算、Run 事件游标通过|
|图导出|`$env:PYTHONPATH='backend/src'; .\.venv\Scripts\python.exe tools/export_agent_graph.py`|可解析 JSON；默认图 10 nodes / 10 transitions|

## 已验证的关键失败与恢复语义

- schema v3 graph hash 不一致：`EXECUTION_VERSION_UNAVAILABLE`，且无 Tool、LLM 或 calculation 副作用。
- 总预算耗尽：plan 节点记录 `BUDGET_EXCEEDED` 与 graph/node 规格身份。
- research 中断且无 Claim：不自动重试；已有 Claim 时允许恢复既有后续步骤。
- partial replay：复制源产物、保持 partial、不调用模型、不生成报告。
- report 中断：恢复后仅生成一份报告；replay_copy 属安全恢复节点。
- schema v2 queued live 与 completed replay：使用冻结兼容图继续执行，trace 明确记录兼容图身份。
- base 形态、无 execution manifest 的 completed Run：legacy replay 完成且模型调用为 0，报告明确披露 provenance 不完整。
- 相同 adapter version/public config 但 `generate()` 实现改变：在 Tool、LLM 与 calculation 之前失败。

## 未执行与人工待办

- 未调用真实 DeepSeek 付费 API；测试和 smoke 使用受控 fake/无密钥失败边界。
- 未执行本轮可见浏览器验收、Windows/Ubuntu 两机干净安装、第二位开发者独立复现或人工财务签核。
- PR CI 和互审尚未发生，不得写成通过。
- G4 MCP、G5 JSONL 日志与原生复现脚本、第二企业和 OCR 均不在本轮实现范围。
