# ADR-G7-001：采用 RapidAI 模块化 OCR 栈作为 G7 默认候选

状态：accepted-for-poc；尚未通过 G7 产品验收。

背景与约束：链眼需要在 Windows 11 与 Ubuntu 的 CPU 环境中处理中文年报的扫描文字、财务表格和真实坐标，同时保持 OCR SDK 位于 adapter 边界之外。OCR 输出只能生成待复核候选，无权写入 `verified`。普通 CI 不下载大型权重；模型、配置、输入和结果必须可追溯。

候选与同样本实测：本轮检索并检查 RapidOCR、RapidTable、RapidLayout 的固定版本源代码。使用亿纬锂能 2025 年报第 9 页的 144 DPI 栅格化图像做可行性测试：RapidOCR 识别 104 行；RapidLayout 检出 3 个表格区域，主财务表分数 0.9756；对主表裁剪后，RapidTable 给出 11 行 × 5 列、55 个 cell 及行列逻辑坐标。该样本来自带文本层的原生 PDF，不是真实扫描件，不计入最终准确率。

决定与理由：G7.1/G7.2 默认候选为 RapidLayout 1.2.1（PP-DocLayoutV3）→ RapidOCR 3.9.2（PP-OCRv6 small）→ RapidTable 3.0.0（SLANet Plus），统一使用 ONNX Runtime 1.23.2 CPU。三部分可以独立替换；输出覆盖文字四点框、版面框、表格 cell 多边形与逻辑行列，适合映射到后续 `PageArtifact`/`TableCell`。选型是 POC 放行，不代表真实扫描验收通过。

许可证、锁版本、替换接口：三个包装器仓库代码均声明 Apache-2.0；Python 依赖固定于 `backend/requirements-ocr.lock`，权重名称、URL、字节数和 SHA256 固定于 `data/ocr_model_manifest.json`。适配器必须通过 Parser/OCR port 接入，领域层不得 import RapidAI SDK。RapidOCR v3.9.2 tag 没有当前主分支新增的模型许可证说明文件，因此权重再分发条款仍需人工法务确认；确认前只能按需下载到忽略目录，不提交或再分发权重。

成本与负面影响：本机单页 OCR 约 37.084 秒，布局推理约 8.544 秒，表格裁剪流水线约 24.285 秒；PP-DocLayoutV3 单个权重约 124.46 MiB。以上只是一次 Windows CPU 测量，没有峰值内存、p50/p95 或 Ubuntu 数据，不能用于容量承诺。

失败降级与回退：OCR 不可用、超时、非零旋转坐标尚未验证、任一模型哈希不符或 cell 坐标缺失时返回 warning/partial/`needs_review`，不得生成伪 bbox 或提升为 verified。若冻结 held-out 集未达到联合准确率 95%、页定位 100%，则在同一 port 后比较 PP-StructureV3；Docling + RapidOCR 只保留为统一版面备选，不在本 ADR 中引入。

团队评审/日期：Codex POC，2026-10-15；第二位开发者复现、真实互审、法务与财务签核待实际执行者确认。
