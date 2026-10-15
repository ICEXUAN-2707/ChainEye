# P2 G7 OCR POC 验收记录

日期：2026-10-15

分支：`chore/p2-ocr-poc`

基线：`develop@459d250`（PR #24 合并提交）

状态：G7.0 工程 POC 已落地；真实扫描评测集、第二候选同集对比、第二位开发者复现和互审未完成，不得标记 G7 完成。

## 已验证

|检查|真实结果|
|---|---|
|RapidOCR 3.9.2 / EVE 2025 第 9 页 144 DPI|104 行；初始化 1.492 秒，推理 37.084 秒；四点框存在|
|RapidLayout 1.2.1 / PP-DocLayoutV3|20 区域、3 个 table；主表分数 0.9756；初始化 23.669 秒，推理 8.544 秒|
|RapidTable 3.0.0 / SLANet Plus 主表裁剪|11 × 5、55 cells；初始化 6.518 秒，流水线 24.285 秒；HTML/cell polygon/logic point 存在|
|模型完整性|5 个 ONNX 文件的实际 SHA256 与 `data/ocr_model_manifest.json` 相符|
|基础依赖 + OCR 可选依赖|同一 Python 3.12 `.venv` 安装成功，`pip check` 无破损依赖|
|POC 安全边界|工具不读答案、不写数据库；旋转页无已验证变换时输出 null PDF 坐标|

## 仓库门禁

|命令/检查|结果|
|---|---|
|`python -m unittest discover -s tests -v`（UTF-8 环境）|214 项通过，180.330 秒|
|`python tools/verify_baseline.py`|30 条 fixture、4 项 margin、文件哈希和契约引用通过；不等于 OCR 准确率|
|契约导出、TypeScript 生成与生成物 diff|OpenAPI/Schema 0.5.0；零漂移|
|`npm ci --prefix frontend` + `npm run build --prefix frontend`|41 项逻辑测试 + 3 项组件测试、TypeScript、Vite 构建通过|
|`python tools/preflight.py`|Python 3.12.10、Node 24.13.0、npm 11.6.2、UTF-8、依赖、目录和端口通过|
|`python -m pip check`|`No broken requirements found.`|
|`python tools/smoke_local.py`|隔离真实 HTTP、上传/提取/复核/情景/Run、日志与无付费模型边界通过|
|最终 `tools/ocr_poc.py` 全链路|104 OCR 行、20 layout 区域、55 table cells、5 个选定模型哈希验证通过|

第一次全量测试未设置 `PYTHONUTF8=1`，preflight 按设计报告 `utf8_mode=0, stdout=gbk`，结果为 214 项中的 2 项失败，不能记为成功。按仓库规定补齐 UTF-8 环境后完整重跑，最终 214 项通过；没有修改或放宽预检规则。

## 必须保留的限制

- 样本是原生文本年报渲染图，不是真实扫描件；这些结果只证明迁移接口可用，不计算 OCR 联合准确率。
- PP-DocLayoutV3 约 124.46 MiB；普通 CI 只跑纯逻辑/manifest 测试，不下载大型权重。
- 权重再分发许可待人工确认；仓库未提交模型、PDF 或 `.runtime` 输出。
- G7 最终门禁仍是独立至少 20 页/60 字段，联合准确率 ≥95%、页定位 100%，并覆盖真实扫描、表格、混合、旋转和低清。
- 团队人工财务签核、第二位开发者复现、PR 互审不能由本记录代签。
