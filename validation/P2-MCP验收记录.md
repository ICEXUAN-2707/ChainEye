# P2 G4 MCP MVP 验收记录

日期：2026-10-10
分支：`feat/p2-mcp-mvp`
基线：`develop@0d74837`
状态：本地实现与自动化检查通过；PR CI、第二位开发者独立复现和真实互审待执行。

## 本轮交付

- 使用官方 `mcp==2.3.0` 实现 `python -m chain_eye.mcp.server` stdio 入口，依赖及传递依赖精确写入 `backend/requirements.lock`。
- 对外只发布 `get_facts`、`get_evidence`、`search_documents`、`get_run_trace`、`get_report` 五个只读 Tool；与 Agent 共用同一 ToolRegistry。
- 发布 Dataset version、Evidence、Run trace、已持久化 Report、Skill metadata 五个资源模板，以及 `chain-eye://about` 静态资源。
- 发布 `evidence_bound_research` Prompt，返回现有 PromptRegistry/SkillRegistry 的版本、哈希和内容，不调用模型。
- 新增真实 stdio 子进程协议测试与 `tools/mcp_smoke.py`，同时覆盖库内调用层的范围、参数、脱敏、不可变性与错误边界。

## 交叉自检发现与处理

1. 初始实现把 MCP 的 ID/查询长度限制写入了既有 Evidence Tool handler，这会改变已排队 Run 绑定的 Tool 实现哈希。
2. 已将这些限制移至 MCP 协议边界，不改 Agent handler。与 `develop@0d74837` 的六个 Agent Tool 实现哈希逐项对比，结果全部一致，并将预期哈希固化为回归测试。
3. MCP 调用使用 `run_id=None` 的上下文，Registry 拒绝 MCP 带 Run 写入上下文；测试证明 trace/report 读取前后 Run event 数量和内容不变。
4. 输出限制为 262144 字节，精确敏感键会被移除；不暴露任意 shell、SQL、文件路径、网络或写工具。

## 实际执行与结果

PowerShell 执行时使用 `$env:PYTHONPATH="backend/src"`。

| 命令 | 真实结果 |
|---|---|
| `.venv\Scripts\python.exe -m unittest discover -s tests -v` | PASS，178 tests，201.758s |
| `.venv\Scripts\python.exe tools\verify_baseline.py` | PASS，30 fixture records、4 margin checks、文件哈希和契约引用通过 |
| `.venv\Scripts\python.exe tools\export_contracts.py` | PASS，导出 OpenAPI/Schema 0.4.0 |
| `.venv\Scripts\python.exe tools\generate_ts.py` | PASS，生成 TypeScript |
| `git diff --exit-code -- contracts frontend/src/api/generated.ts` | PASS，无生成物漂移 |
| `.venv\Scripts\python.exe -m pip check` | PASS，`No broken requirements found.` |
| `npm.cmd ci --prefix frontend` | PASS，22 packages audited，0 vulnerabilities |
| `npm.cmd test --prefix frontend -- --run` | PASS，28 tests |
| `npm.cmd run build --prefix frontend` | PASS，28 tests、TypeScript 检查和 Vite build 通过 |
| `.venv\Scripts\python.exe tools\smoke_local.py` | PASS，真实 HTTP、PDF、上传、15 条提取、复核、9 项情景计算、无密钥 `MODEL_UNAVAILABLE` 边界通过 |
| `.venv\Scripts\python.exe tools\mcp_smoke.py` | PASS，5 tools、5 resource templates、1 resource、1 prompt，版本化 Dataset/Evidence 真实读取，`paid_model_calls=false` |
| `.venv\Scripts\python.exe tools\mcp_smoke.py --db .runtime\mcp-full-smoke-20261010.sqlite --run-id df00bbea-ee28-40f4-be87-7289255469b0` | PASS，已持久化 Run trace/report 读取通过，`run_checks=passed`，`paid_model_calls=false` |

带 Run 的扩展 smoke 首次复跑曾失败：执行者只在父进程设置了 `CHAIN_EYE_DB`，但 `tools/mcp_smoke.py` 会根据其 `--db` 参数重建子进程环境，因此读到默认 smoke 库中不存在的 Run。改为显式 `--db` 后通过；该失败不记为产品成功。

## 未完成与人工待办

- 本轮未调用 DeepSeek，不验证线上密钥、余额或服务可用性。
- 本轮不包含 G5 统一 JSONL logging、preflight/bootstrap/start_all/replay/trace 复现链。
- 尚未由第二位开发者在独立环境复现，也不代签 PR 互审、财务签核或可见浏览器验收。
- 第二企业与 OCR 仍在 G6/G7，本轮未越界实现。
