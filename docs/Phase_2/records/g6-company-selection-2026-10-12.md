# G6 第二企业、契约与前端交接记录

日期：2026-10-12
分支：`feat/p2-company-core`
基线：`develop@0b26a54339d6dee7e6df751231ffde7e0c1f2db9`

## 冻结选择

- 第二企业：惠州亿纬锂能股份有限公司，`company_id=eve-energy`，`company_code=EVE`。
- 证券标识：深圳证券交易所 `300014`；巨潮资讯组织号 `9900008311`。
- 行业 profile：`battery-manufacturing-cn-v1`；企业 profile 版本 `1`。
- 2024 年报用于版式适配；2025 年报作为未见迁移材料。公告号、官方 URL、SHA256、字节数和页数见 `data/company_sources.json`。
- 官方公开披露原件只按需下载到 `.runtime/company-sources/`。仓库不在缺少明确再分发许可时提交 PDF；记录 URL、公告号和哈希用于复现与归因。

## 契约变化与兼容

HTTP/OpenAPI 从 `0.4.0` 提升到 `0.5.0`：

- `DatasetCreate.company` 与 `Dataset.company` 增加 `EVE`；Dataset 增加 `company_id`、`company_profile_version`、`industry_profile_id/version`、`report_type`、`identity_status`、`identity_confirmation_reason`。
- `Fact.raw_unit` 增加 `CNY_yuan`；API 规范金额仍是人民币元十进制字符串。CATL 原文千元继续以 `CNY_thousand` 保留并乘 1000；亿纬锂能源文元以 `CNY_yuan` 保留且不缩放。
- 新增 `GET /api/v1/companies`、`GET /api/v1/datasets/{id}/identity-candidates`、`POST /api/v1/datasets/{id}/identity-confirmations`、`GET /api/v1/datasets/{id}/capabilities`。
- 新增迁移 `003_company_identity.sql`，按企业与 profile 版本保留配置，并保存按 Dataset/version/source 绑定的候选身份和确认审计记录。旧 Dataset 经模型兼容校验映射到 `catl@1` 与行业 profile v1，旧快照不重写。
- 身份冲突或未确认时，Run/Scenario fail closed；人工确认要求 `expected_version`，成功后生成新 Dataset 快照。
- 能力查询必须显式传入 `industry_profile_version` 且与 Dataset 快照一致；不一致返回 `STALE_SNAPSHOT`，不能任意回显调用方版本。

## 前端负责人待办

生成文件已由 `tools/generate_ts.py` 更新，禁止手改。前端需要在自身分支：

1. 让 `FactTable` 的原始单位格式化支持 `CNY_yuan`，展示“元”且不做千倍换算。
2. 让 `ReviewForm` 的规范值/原始值换算支持 `CNY_yuan`：CNY 元值一比一；`CNY_thousand` 仍乘/除 1000；`percent` 仍除/乘 100。
3. 补三类测试：元值展示、人工更正往返不缩放、原有千元和百分比回归。
4. 复现 `npm ci --prefix frontend && npm run build --prefix frontend`；当前后端分支上的真实结果为前端 28 项测试通过，随后 TypeScript 在 `FactTable.tsx:13` 与 `ReviewForm.tsx:73` 各报 1 处 `CNY_yuan` 未覆盖错误。

这份记录只描述接口与影响，不代替前端实现、可见浏览器检查或另一名开发者互审。

## 2026-10-13 前端候选进展

- 从 `feat/p2-company-core@78858f8` 建立 `feat/p2-company-frontend`，没有手改 `frontend/src/api/generated.ts`。
- `FactTable` 已显示 `CNY_yuan` 为“元”；`ReviewForm` 使用十进制字符串移位实现元、千元和百分数双向联动，金额回写不经过 JSON 浮点数。
- 本地 34 项前端测试、TypeScript、Vite 构建、205 项后端测试、baseline、契约零漂移和隔离 HTTP smoke 已通过，真实命令与限制见 `../../../validation/P2-G6前端验收记录.md`。
- Chrome 无头真实页面验证了 EVE 13 条元值事实及双向一比一编辑；computer-use 可见浏览器 helper 初始化失败，因此可见人工浏览器复核、远端 CI、第二位开发者独立复现和互审仍未完成。
