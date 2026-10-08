# P2 Agent Registry 验收记录

- 日期：2026-10-08
- 分支：`refactor/p2-agent-registries`
- 基线：`main@a9dceb01b72573365a9c31d339f3d755d69e7850`
- 范围：G2 Tool/Prompt/Skill Registry；不包含显式 graph、MCP、结构化 JSONL、第二企业、OCR 或前端业务改造。

## 实现核对

- 现有六个 Run Tool 迁入单一 `ToolRegistry`，原 `RunTools` 只保留兼容门面，不保留第二份 handler 实现。
- `ToolSpec` 声明版本、调用方、单工具超时、副作用类型与 handler；Registry 拒绝重复、未知、调用方越权和 Skill allowlist 越权。
- `r4-claims-v3` 从内联常量迁到版本化文件，manifest 固定 SHA256；加载时校验路径、内容和哈希。
- `evidence_bound_research`、`financial_diagnosis`、`scenario_impact` 以可解析清单和指令文件加载；依赖的 Tool 与 Prompt 必须存在且哈希一致。
- Run 运行时从 Skill 的 Prompt 引用加载实际 Prompt；Run 元数据、plan、tool_call 与 llm_call 事件记录对应版本和内容哈希。
- HTTP 0.4.0 DTO、OpenAPI、数据库表结构、金额口径和前端业务实现未改变。

## 自动化结果

以下命令均在仓库根目录执行，退出码均为 0。

```powershell
$env:PYTHONPATH="backend/src"
.\.venv\Scripts\python.exe -m unittest discover -s tests -v
```

结果：146 项通过，耗时 180.720 秒。

```powershell
.\.venv\Scripts\python.exe tools/verify_baseline.py
```

结果：`PASS: 30 fixture records, 4 margin checks, file hashes, contract references.`

```powershell
.\.venv\Scripts\python.exe tools/export_contracts.py
.\.venv\Scripts\python.exe tools/generate_ts.py
git diff --exit-code -- contracts frontend/src/api/generated.ts
```

结果：导出 OpenAPI/Schema 0.4.0，生成 TypeScript 后无生成物漂移。

```powershell
npm.cmd ci --prefix frontend
npm.cmd run build --prefix frontend
```

结果：按锁文件安装 21 个包；前端 28 项测试通过，TypeScript 检查和 Vite 生产构建通过。

```powershell
.\.venv\Scripts\python.exe tools/smoke_local.py
```

结果：`status=passed`；真实 HTTP、前端 HTML、CORS、上传、修订、场景、Run 事件游标均通过。未配置模型密钥时 Run 真实返回 `partial/MODEL_UNAVAILABLE`，没有伪造 live 模型成功。

## 尚未完成或需人工确认

- 未执行真实 DeepSeek 付费调用；本轮不以无密钥 smoke 替代 live 验收。
- 浏览器可视验收不是本轮自动化结果，smoke 明确保留 `visual_browser_check=separate check`。
- 另一位开发者独立复现、PR 互审和团队财务签核仍须由实际执行者确认，本记录不代签。
- G3 显式 graph、G4 MCP MVP、G5 原生复现与结构化日志仍未实现，不能因 G2 通过而宣称 Agent Kernel 全部完成。
