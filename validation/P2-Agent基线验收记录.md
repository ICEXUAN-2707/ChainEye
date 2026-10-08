# P2 Agent 基线验收记录

日期：2026-10-08  
分支：`chore/p2-agent-baseline`  
基线：`main@c7642185458a37719ca210a08b7cd8e18f3e129a`  
环境：Windows 11 10.0.26200、Python 3.12.10、Node 24.13.0、npm 11.6.2。

## 变更范围

本分支只更新 Phase 2 现状、契约影响、Agent Kernel/MCP MVP 计划、跨平台复现矩阵与敏捷分支顺序。没有修改后端/前端业务、数据库迁移、HTTP DTO、OpenAPI、Schema 或生成 TypeScript。

## 自动化结果

|检查|真实结果|
|---|---|
|`$env:PYTHONPATH="backend/src"; .\.venv\Scripts\python.exe -m unittest discover -s tests -v`|141 项通过，220.321 秒|
|`.\.venv\Scripts\python.exe tools/verify_baseline.py`|30 条 fixture、4 项毛利检查、文件哈希与契约引用通过；输出明确不代表行列提取准确率|
|`tools/export_contracts.py`、`tools/generate_ts.py`|导出 OpenAPI/Schema `0.4.0`，生成 TypeScript 成功|
|`git diff --exit-code -- contracts frontend/src/api/generated.ts`|通过，生成物零漂移|
|`npm.cmd ci --prefix frontend`|首次失败：旧 Vite/esbuild 进程占用 `esbuild.exe`，Windows `EPERM`；确认 PID/命令行只属于本项目并停止后重跑通过，安装 21 个包|
|`npm.cmd run build --prefix frontend`|28 项测试通过；TypeScript 通过；Vite 7.3.7 构建通过，44 个模块转换|
|`.\.venv\Scripts\python.exe tools/smoke_local.py`|`status=passed`；真实 HTTP、前端 HTML、CORS、上传、15 条候选、revision/version、重复来源、9 条情景计算、Run 和事件游标通过|

smoke 未配置 DeepSeek 密钥，因此 live Run 的真实结果为 `partial + MODEL_UNAVAILABLE`，报告边界为 `REPORT_NOT_READY`；没有伪造成模型调用成功。

## 未执行与待办

- 本分支没有调用真实 DeepSeek 付费接口。
- Agent Registry、显式 graph、运行时 Skill、MCP server、MCP smoke 和 JSONL 日志尚未实现；本文档不能替代这些功能。
- Ubuntu 当前只由既有 GitHub Actions 覆盖旧门禁；新的 replay/MCP smoke 需 G4/G5 实现后再加入双系统 CI。
- 可见浏览器、团队财务签核、第二开发者独立复现和 PR 互审须由实际执行者确认，本记录不代签。

## 结论

G1 文档与现状基线可提交审查。只有本 PR 合并后，才从最新集成基线建立 G2 `refactor/p2-agent-registries`；不得直接跳到 MCP、第二企业或 OCR。

