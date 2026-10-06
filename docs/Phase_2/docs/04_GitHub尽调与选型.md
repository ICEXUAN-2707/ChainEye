# GitHub检索、借鉴与选型任务

## 已有参考（2026-10-05网页与官方说明检索，未运行）
|仓库|参考点|采用前验证|
|---|---|---|
|https://github.com/AI4Finance-Foundation/FinRobot|金融工具、分阶段分析/报告工作流|读取真实实现、供应商及中国财报适配；不照搬美股数据源|
|https://github.com/docling-project/docling|版面、表格、OCR统一结构|中文行列/页坐标/CPU资源/Windows安装|
|https://github.com/PaddlePaddle/PaddleOCR|中文OCR及PP-Structure表格/坐标|不要混淆OCR与结构化模块，记录模型/引擎版本|
|https://github.com/RapidAI/RapidOCR|ONNX及CPU部署|适合基础OCR，不自动解决表格语义|
|https://github.com/opendatalab/MinerU|复杂文档Markdown/JSON及硬件档位|复杂度、资源、精确许可证和模型条款|

## Codex必须完成的尽调
对每个候选记录URL、commit/tag、检索日期、实际文件路径、接口/输入输出、依赖、代码许可证/模型权重条款、API/费用、硬件、能复用什么、为何不整仓迁移。README宣传与实际运行结果分栏；不能用stars代表准确率。
金融架构至少阅读FinRobot一个实际分析/工具/报告实现；OCR至少POC两个候选：RapidOCR与Docling或Paddle结构化方案。MinerU可作备选，不要求安装五套。
下载/复制代码前确认许可证；保留归属和NOTICE，权重许可另核对。固定commit/模型hash，避免开发时自动追latest。

## 解析POC样本
同一批20个页任务：原生文本5、真实扫描文字5、扫描财务表5、混合/旋转/低清5。尽可能来自两企业且真实扫描非空；合成扫描可补充但不能替代真实扫描验证。找不到真实扫描必须登记验收未过。
标注至少60个字段，包含数字/单位/年份、负数、括号负数、百分数、千元/万元、合并表头、上年列和脚注。POC样本用于选择引擎；另留未见测试页不调参。
记录冷启动/模型下载、暖运行耗时、峰值内存、安装失败、字段联合准确率、表格列正确率、页定位；同一硬件和配置比较。选择默认引擎并通过ADR记录权衡；如果失败保留人工复核降级，不宣称OCR解决。

## 设计原则
只借鉴模块和流程，不整体换框架；不需要自主训练模型；选型先看证据、口径和可复现结果。外部公开benchmark不是本项目财报准确率。
交付templates/repo-research.md、templates/ADR.md及原始POC结果，合入develop后再接入生产管线。
