# G7 OCR 评测与解析契约增量

状态：`design_frozen_pending_review`。本文只冻结后续实现边界；当前分支不修改路由、DTO、领域模型、迁移、OpenAPI、生成 TypeScript 或前端实现。

基线：`develop@b4377d070102a4f299ce68a12c7be21ea63132d0`，即 PR #25 合并提交。

当前 HTTP/OpenAPI 版本：`0.5.0`。实现本增量时拟提升为 `0.6.0`；这是新增解析资源和路由的向后兼容 minor 版本，不改变现有金额、Fact、Evidence、Dataset、Run、Scenario 或 Report 语义。

## 变更原因与非目标

现有上传流程只能同步处理受控文本层年报，扫描 PDF 返回 `needs_review`，没有可查询的解析作业、逐页方法、真实 OCR 坐标、取消/重试或部分失败记录。G7 需要在不建立第二套 Dataset/Fact/Evidence 的前提下增加按页解析审计链。

本增量不包含以下行为：

- 不把 OCR confidence 当作财务事实正确概率。
- 不允许 OCR、模型或自动提取把 Fact 写成 `verified`。
- 不修改既有金额字符串、千元原值、`ratio` 或 `pp` 规则。
- 不把模型权重、原始 PDF、渲染图或绝对本机路径放入 HTTP 响应或仓库。
- 不新增独立微服务、消息中间件、第二套 worker、第二套复核事务或平行 DTO。
- 不在普通 CI 下载大型权重或调用付费模型。

## 权威来源与复用映射

实现后契约单一来源仍是后端路由、`api/dto.py` 和 `domain/**`；`contracts/**` 与 `frontend/src/api/generated.ts` 只能由生成脚本更新。

|G7 语义|现有对象|决定|
|---|---|---|
|上传原件与哈希|`Source`、`SourceAttachment`|复用；`Source.sha256` 是解析输入哈希|
|绑定数据快照|`Dataset.id/version/source_ids`|复用；ParseJob 固定 `base_version`，不读取 latest 代替|
|页级解析结果|无|新增 `PageArtifact`，不伪装成 Evidence|
|表格单元格|无|新增 `TableCell`，必须保留页码与真实坐标|
|候选事实|`Fact`|复用；状态仅允许 `extracted/missing/conflict/needs_review`|
|事实定位|`Evidence`|复用；仅从有真实页码/坐标或明确页级定位的 PageArtifact 生成|
|人工更正|`PATCH /facts/{id}`|完全复用 revision/version/409 事务|
|作业执行|现有单 worker|复用调度线程；ParseJob 与 Run 是不同资源，但不得再建一个常驻 worker 系统|
|来源摘要状态|`Source.parse_status`|保留兼容投影；作业真相以 ParseJob 为准|

## 评测数据契约

后续 `data/ocr_eval_manifest.json` 使用独立 `schema_version: 1`。原件默认按 URL 下载到忽略目录；没有明确再分发许可时只提交元数据和人工标注，不提交 PDF 或页面图片。

### 清单字段

|字段|约束|
|---|---|
|`dataset_id`|稳定评测集 ID，例如 `g7-ocr-eval-v1`|
|`created_at`|ISO8601 含时区|
|`answer_policy_version`|人工答案与舍入规则版本|
|`documents[]`|公司、报告年度、报告类型、官方 URL、SHA256、页数、许可/再分发说明|
|`pages[]`|document ID、一基页码、split、类别标签、rotation、预期是否有坐标|
|`fields[]`|稳定 field ID、page ID、指标、期间、范围、原值、原单位、规范值、允许舍入与表格行列语义|

### 清单不变量

- 至少 20 个唯一页面、60 个必需字段，两家公司均有页面和字段。
- `native_text`、`scanned_text`、`scanned_financial_table`、`mixed`、`rotated`、`low_quality` 每类至少 5 页；同一页可有多个类别标签。
- `adaptation` 与 `held_out` 按 document/page 明确冻结；同一 field 不能跨 split。
- OCR/解析进程只接收原件、页号和配置，不接收 `fields[]` 或答案路径。
- 原始引擎输出先落盘并哈希，再由独立评分器读取答案。
- 联合准确率要求值、单位、期间和业务/范围同时正确；漏提、错列、错单位均计错。
- 页定位率以正确一基页码为分母；bbox 只在真实坐标存在时评估，不能用人工补框冒充引擎结果。
- 结果按企业、split、页面类别和指标类别拆分，并记录冷/暖启动、p50/p95、峰值内存和失败。

## HTTP 与领域模型

### ParseJobCreate

|字段|类型与约束|
|---|---|
|`dataset_id`|非空字符串|
|`base_version`|整数，`>=1`；必须包含 path 中的 source|
|`engine_profile_id`|首版只允许 `rapidai-cpu-onnx-v1`|
|`page_numbers`|`null` 表示全部页面；否则为已排序、去重、一基页码数组，最多 500 项|
|`retry_of_job_id`|默认 `null`；重试时必须引用同 dataset/source/base version/profile 的终态作业|

请求必须带 8—128 字符 `Idempotency-Key`。作用域为 dataset + source；同键同请求返回原 Job，同键不同请求返回 409。幂等记录至少保留 24 小时。

重试创建新的不可变 Job，不原地清空旧结果。`retry_of_job_id` 只能重试前序 `partial/failed/cancelled` 作业中未成功的页面；改变引擎或基础版本属于新作业，不得伪装成重试。

### ParseJob

|字段|类型与语义|
|---|---|
|`id`|稳定资源 ID|
|`dataset_id/base_version`|不可变快照绑定|
|`source_id/source_sha256`|不可变来源绑定|
|`engine_profile_id/profile_version`|已解析的引擎配置版本|
|`model_manifest_sha256/config_sha256`|实际模型清单和运行配置哈希|
|`page_numbers`|实际请求页；响应中始终展开为数组|
|`status`|`queued/running/completed/partial/failed/cancelled`|
|`cancel_requested`|布尔值；运行中取消是协作式，不伪造立即停止|
|`attempt/retry_of_job_id`|首个 attempt 为 1；重试链可追溯|
|`processed_pages/succeeded_pages/failed_pages/total_pages`|均为非负整数且满足计数不变量|
|`publication_status`|`pending/published/no_candidates/blocked_identity/blocked_stale/failed`|
|`result_dataset_version`|仅 `published` 时非 null，且大于 base version|
|`warnings`|结构化 `ParseWarning[]`|
|`error`|复用 `ErrorBody`，无错误为 null|
|`created_at/started_at/finished_at/updated_at`|ISO8601 含时区；不返回绝对路径|

状态只能按下列方向变化：

```text
queued -> running -> completed
                  -> partial
                  -> failed
                  -> cancelled
queued ----------------> cancelled
```

`completed` 表示所有请求页均得到可用页结果，不代表候选事实已经发布。部分页失败但至少一页可用为 `partial`；没有可用页为 `failed`。终态不可原地重新排队。

`processed_pages` 是已经进入终态的页数，必须等于 `succeeded_pages + failed_pages` 且不大于 `total_pages`。正常穷尽页面的 `completed/partial` 必须满足 `processed_pages == total_pages`；作业级致命失败或协作式取消可以小于 total，未开始页面不伪造 PageArtifact。

### ParseWarning

字段为 `code`、`message`、`retryable`、可选 `page_no` 和受限 `details`。details 不得包含环境变量、header、cookie、密钥、任意路径或无界原文。

### PageArtifactSummary 与 PageArtifact

列表接口只返回 Summary，避免一次返回整本 OCR 文本；单页详情接口返回完整 PageArtifact。

共有字段：`id`、`parse_job_id`、`source_id`、`source_sha256`、一基 `page_no`、`artifact_sha256`、`method`、`status`、`warnings`。

- `method`：`native/ocr/hybrid`。
- `status`：`completed/partial/failed/cancelled`。
- Summary 另外返回 `text_available`、`bbox_available`、`block_count`、`table_count`。
- 完整对象另外返回 `geometry`、`text`、`blocks`、`tables`。

`geometry` 固定包含：

- `width_pt/height_pt`：十进制字符串；
- `rotation`：`0/90/180/270`；
- `cropbox`：4 个十进制字符串；
- `render_width_px/render_height_px/dpi`：正整数；
- `pixel_to_pdf_matrix`：6 个十进制字符串或 null。

没有经过验证的旋转/cropbox 变换时，matrix 和所有 PDF polygon 必须为 null；不得用像素坐标冒充 PDF 坐标。

### TextBlock、TableArtifact 与 TableCell

TextBlock 包含稳定 ID、类型、文字、可选 OCR confidence、`polygon_px` 和 `polygon_pdf`。confidence 使用十进制字符串，保存引擎原始范围说明，不称为概率。

TableArtifact 包含稳定 table ID、页码、可选跨页组 ID、HTML（有严格大小上限）和 cells。

TableCell 字段冻结为：

- `id/table_id/source_page`；
- `row_start/row_end_exclusive/col_start/col_end_exclusive`，均为非负整数且 end 大于 start；
- `text`、可选 confidence；
- `polygon_px`、`polygon_pdf`；
- `header_cell_ids`；
- `continued_from_cell_id`，跨页时显式关联。

polygon 是四点数组，每个点的 x/y 均为普通十进制字符串。页面坐标使用 PDF point；前端不得自行猜测 DPI 或旋转。

### PageArtifactCollection

字段为 `parse_job_id`、`items`、`next_offset`。按 `page_no` 升序稳定分页，`offset>=0`，`1<=limit<=100`。

### ParseCancelRequest

字段仅为 `expected_status`（`queued/running`）。状态已变化或 Job 已终态时返回 409；Dataset 后续推进不能阻止用户停止旧 Job。queued Job 可立即取消；running Job 只设置 `cancel_requested=true`，worker 在安全页边界结束。

## HTTP 路由冻结

|动作|响应|语义|
|---|---|---|
|`POST /api/v1/sources/{source_id}/parse-jobs`|202 `ParseJob`|创建或幂等复用；校验 source 属于 base snapshot|
|`GET /api/v1/parse-jobs/{id}`|200 `ParseJob`|读取作业状态|
|`GET /api/v1/parse-jobs/{id}/pages`|200 `PageArtifactCollection`|仅页摘要，稳定分页|
|`GET /api/v1/parse-jobs/{id}/pages/{page_no}`|200 `PageArtifact`|读取单页全文、blocks、tables/cells|
|`POST /api/v1/parse-jobs/{id}/cancel`|202 `ParseJob`|幂等取消；使用 `ParseCancelRequest`|

在 worker 与持久化尚未实现时，路由若提前进入 OpenAPI，必须返回明确 501；禁止返回 queued 假成功。实现 PR 应一次性把可调用路由、worker 和测试闭环接通。

## 身份、版本与发布事务

- ParseJob 可以在身份未确认时生成无公司归属的 PageArtifact，便于确认后复用。
- 身份未确认或冲突时不得发布 Fact/Evidence；Job 可为 `completed + blocked_identity`。
- 页结果保存不增加 Dataset version。
- 候选发布必须在一个事务中比较当前 Dataset version 与 `base_version`、校验 source hash 和身份范围，并为该 Job 至多发布一个新 Dataset snapshot。
- 并发期间 Dataset 已推进时，不静默套用 latest；保存页结果并设 `blocked_stale`，由用户在新版本创建新 Job。
- 没有新候选时 `no_candidates`，不产生空快照。
- 重试可引用旧 Job 的成功 PageArtifact，但必须记录来源 Job；不得重复插入 Fact/Evidence 或重复增版。
- 自动候选只能进入 `extracted/missing/conflict/needs_review`；只有现有人工更正接口能写 `verified`。

`Source.parse_status` 继续作为兼容摘要：queued/running 投影为 `queued`，成功发布投影为 `parsed`，no_candidates/partial/cancelled/身份或 stale 阻断投影为 `needs_review`，无可用页失败投影为 `failed`。前端作业进度只读 ParseJob，不以 Source 摘要代替。

## 持久化方案

实现时新增 `004_parse_jobs.sql`，只追加以下表，不修改历史迁移：

- `parse_jobs`：不可变绑定、状态/计数、版本哈希与受限 JSON body；
- `parse_job_idempotency`：scope、key、request hash、job ID、expires_at；
- `page_artifacts`：`(parse_job_id,page_no)` 唯一、artifact hash 与 JSON body；
- `parse_table_cells`：按 job/page/table/cell 保存，避免整本单 JSON；
- `parse_publications`：job、from/to Dataset version、发布状态和事务结果，job 唯一。

所有表启用外键并建立 dataset/source/status/page 查询索引。页文字、blocks 和 cells 保存在 SQLite 受限 JSON 中；不保存重复 PDF 或渲染图。原件继续由现有受控上传目录管理，UI 通过现有 source content 路由取原件。

## 错误语义

|code|HTTP|retryable|说明|
|---|---:|---|---|
|`NOT_FOUND`|404|false|Job、source 或 page 不存在|
|`INVALID_INPUT`|422|false|页范围、profile 或请求结构非法|
|`SOURCE_SCOPE_MISMATCH`|409|false|source 不在 base snapshot|
|`SOURCE_HASH_MISMATCH`|409|false|原件与 Job 绑定哈希不一致|
|`IDEMPOTENCY_CONFLICT`|409|false|同键请求体变化|
|`PARSE_JOB_STATE_CONFLICT`|409|false|取消/重试状态竞争|
|`STALE_SNAPSHOT`|409|false|候选发布前 Dataset 已推进|
|`OCR_UNAVAILABLE`|503|true|可选 OCR 运行时不可用|
|`MODEL_INTEGRITY_FAILED`|503|false|模型哈希错误；修复模型前不得推理|
|`PARSE_TIMEOUT`|503|true|受控页或作业超时|

部分页错误通常进入 Job/PageArtifact 的 warnings/error，不把已有成功页丢弃后只返回一个 HTTP 500。

## 资源和安全上限

- 单 Job 最多 500 页，默认单并发。
- 分页接口最大 100 页摘要；单页详情设文字、block、table、cell 和 HTML 大小上限。
- 模型缺失时先下载到隔离目录并校验 manifest，任何引擎初始化前必须通过完整性验证。
- 原始 OCR 内容视为不可信数据，不作为 Prompt 指令；不记录 header、cookie、密钥、完整环境或任意路径。
- 普通 CI 使用小 fixture、假 Port 和受控坐标样本；真实模型集成另存结果、配置哈希与失败。

## 前端联调契约

- Claude 只使用生成的 `frontend/src/api/generated.ts`，不手写 ParseJob/PageArtifact 类型。
- 列表轮询键必须包含 dataset ID、base version、source ID、job ID；旧响应不得覆盖当前选择。
- 列表先取 Summary，用户选页后再取 PageArtifact；不得一次加载整本全文。
- `polygon_pdf=null` 时只显示页级定位。
- retry 创建新 Job，UI 保留旧 attempt，不把旧失败记录改成成功。
- 人工复核继续提交现有 Fact correction；ParseJob 页面不能直接写 `verified`。

## 实现与验收顺序

1. 先完成并互审评测 manifest/schema、标注规则和评分口径。
2. 再在独立 `feat/p2-parse-contracts` PR 中实现领域模型、迁移、路由 DTO、生成物和纯契约测试。
3. 契约 PR 合并后，Codex 开发 `feat/p2-parse-core`；Claude 从同一合并提交开发 `feat/p2-parse-review-ui`。
4. 受控真实 OCR 集成不进入普通 CI；最终独立集必须达到联合准确率 >=95%、页定位 100%。
5. 第二位开发者独立复现一条上传→解析→候选→原页/bbox→人工复核流程，并在合并前完成真实 review。

## 生成和回归门禁

实现 PR 必须运行仓库 `AGENTS.md` 的全部命令，并额外覆盖：

- 迁移升级与旧数据库读取；
- 路由 OpenAPI、Schema 和 TypeScript 生成零漂移；
- 幂等同请求复用、变体 409；
- source/dataset/company 跨范围拒绝；
- stale、取消、超时、部分页失败和 retry；
- 旋转/cropbox 仿射与 null bbox 失败闭合；
- 候选发布至多一个 Dataset 版本且绝不自动 verified；
- 旧 Run、replay、Scenario、Report 和 CATL/EVE 回归。

本文冻结后无待实现者自行决定的关键契约项。需要改变路由、状态、版本事务、坐标语义或金额语义时，必须先修改本文并完成双方评审，再开始代码变更。
