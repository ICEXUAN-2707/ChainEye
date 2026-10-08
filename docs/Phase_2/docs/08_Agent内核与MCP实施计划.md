# Agent 内核与 MCP 实施计划

状态：`baseline_ready_for_review`。本文是开发顺序和验收边界，不代表对应代码已经实现。

## 产品目标

链眼要交付的是一条证据约束的全链路金融研究 Agent：原件与 Dataset 快照确定输入，Agent 只通过白名单 Tool 读取事实和证据，金额与情景由确定性程序计算，LLM 只组织受引用约束的研究 Claim，最后经校验和人工复核形成可追溯报告。每次结果能够追到 `Run → Node → Skill → Tool → Prompt → Output`。

## 冻结决策

- 同时支持 Windows 11 与 Ubuntu 原生运行，不纳入 Docker/Compose。
- MCP 只做可演示、可测试的 MVP：stdio、协议初始化与列举、真实最小调用；不做 HTTP/SSE、公网托管或任意外部执行。
- 先完成 Agent Kernel、MCP 和复现链，再开发第二企业与 OCR。
- 支持 live 与 replay。live 需要真实 DeepSeek 密钥；replay 必须来自已保存的真实 Run，并清楚标识，不能用 mock 冒充。
- 使用自有 typed graph，不新增 LangGraph 等编排框架；只有赛方明确要求指定框架时再立 ADR。

## 敏捷开发批次

|批次/分支|交付|完成条件|
|---|---|---|
|A0 `chore/p2-agent-baseline`|现状映射、契约影响、交付结构、双系统矩阵、阶段顺序|文档与真实代码一致；全量门禁通过；不改变行为|
|A1 `refactor/p2-agent-registries`|ToolSpec/ToolRegistry、PromptRegistry、SkillRegistry；首批真实 Skill|6 个工具单一注册源；Prompt 有版本与 SHA256；至少 1 个 Skill 被运行时加载；HTTP 回归无变化|
|A2 `refactor/p2-agent-orchestrator`|显式 graph/state/node spec；`runs.py` 收敛为用例与 worker|图可导出 JSON；节点声明输入、Tool/Skill、预算、重试、失败与恢复；旧 Run/replay/报告回归通过|
|A3 `feat/p2-mcp-mvp`|stdio MCP server、resources、只读 tools、prompt metadata、协议测试与 smoke|真实读取 Dataset/Evidence/Run/Report；与内部 Agent 共用 Registry；跨快照和非法参数明确失败|
|A4 `feat/p2-native-reproduction`|结构化脱敏日志、preflight/bootstrap/start_all、核心流程复现、trace 导出|Windows 11 与 Ubuntu 命令一致；CI 不调用付费模型；replay/MCP smoke 可复现|
|B1 `feat/p2-company-core`|第二企业配置、身份确认、能力矩阵与真实原生 PDF 纵向流程|两企业数据隔离；不确定身份不发布公司事实；旧 CATL 流程不退化|
|B2 `feat/p2-ocr-core`|按页 native/ocr/hybrid 路由、PageArtifact、真实坐标、失败重试|真实扫描样本有量化记录；失败保留 warning/partial/failed；未复核不写 verified|
|C1 `feat/p2-research-skills`|M1/M2/M5 优先，再 M3/M4；能力状态、程序计算、检索、建议|关键数字 100% 绑定 Fact/Calculation/Assumption；不足模块明确缺口|
|C2 `release/phase2-v0.1`|评测、两机复现、未见材料、备份恢复、完整交付清单|验收项逐条有真实证据；无发布阻断；tag 与演示提交一致|

每个批次独立 PR、独立检查和互审。前一批次未合并时，后一批次不得绕过其 Registry/契约另建平行实现。

## A1 目标结构

```text
backend/src/chain_eye/
  agents/
    state.py
    graph.py
    nodes/
  tools/
    spec.py
    registry.py
    handlers/
  prompts/
    claims/v3.md
    manifest.json
  skills/
    schema.py
    registry.py
    evidence_bound_research/
      SKILL.md
      skill.json
```

首批 Skill 为 `evidence_bound_research`、`financial_diagnosis`、`scenario_impact`。Skill 必须具有可解析的 ID、版本、输入、允许 Tool、Prompt 引用和输出约束，并由运行时真正加载；只有 Markdown 说明而未被代码加载不算完成。

## A2 图约束

显式图保持当前主链：plan→extract→validate→finance→research→scenario_if_requested→verify→report。每个节点规范至少声明：输入/输出 state、允许 Skill/Tool、总预算和单工具预算、重试条件、可恢复错误、终止状态和事件字段。

模型无权：直接写 `verified`、执行权威财务计算、越过 Dataset version、修改原件、构造不存在引用或把缺失写成成功。确定性计算与引用校验仍由现有领域/应用服务负责。

## A3 MCP 安全边界

MCP server 通过 `python -m chain_eye.mcp.server` 启动，仅 stdio。协议测试覆盖 initialize、tools/list、resources/list、prompts/list、合法调用、作用域拒绝、未知版本、非法参数、敏感信息不外泄和进程正常退出。演示入口为 `python tools/mcp_smoke.py`。

外部 MCP 默认只读；内部 ToolRegistry 可以包含确定性计算工具，但 MCP allowlist 与 Agent allowlist 分开声明。禁止任意 shell/SQL/文件路径/网络工具，禁止直接接收或写入模型密钥，禁止代表人工完成 `verified`。

## A4 日志与复现

JSONL 日志至少包含 `timestamp`、`level`、`request_id`、`run_id`、`node`、`skill_id`、`tool_call_id`、`prompt_version`、`model`、`duration_ms`、`status`、`error_code`。禁止记录 API key、Authorization、完整环境变量、无界 PDF 文本或未经裁剪的完整模型请求。

计划统一命令：

```text
python tools/preflight.py
python tools/bootstrap.py
python tools/start_all.py
python tools/reproduce_core_flow.py --mode replay
python tools/mcp_smoke.py
```

Ubuntu CI 跑完整无付费门禁；Windows CI 至少跑依赖安装、后端测试、契约漂移、前端构建、MCP smoke 和 replay。Python 固定 3.12、Node 固定 24、UTF-8 显式开启。

## 进入第二企业/OCR的关口

- 显式图、6 个 Registry 工具、Prompt 文件与 SHA256、至少 1 个运行时 Skill 已真实落地。
- MCP stdio 能读取真实 Dataset/Evidence/Run trace/Report，且协议 smoke 通过。
- Windows 11 与 Ubuntu 的 replay 和 MCP smoke 有真实记录。
- 任一结果可追到 Run、Node、Skill、Tool、Prompt 与输出哈希。
- 旧 CATL 上传、复核、计算、Run、回放和报告没有回归。
- 不存在平行 DTO、重复 Tool 实现、假成功、假模型调用或代签人工验收。

