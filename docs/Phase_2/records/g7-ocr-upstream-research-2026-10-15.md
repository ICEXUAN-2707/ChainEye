# G7 OCR 上游尽调与 POC 记录

日期：2026-10-15

## 固定上游

|组件|仓库|固定版本/提交|实际入口|代码许可证|
|---|---|---|---|---|
|RapidOCR|https://github.com/RapidAI/RapidOCR|`v3.9.2` / `095232a4c94f7f0e6600ba5bba1177010ad696d4`|`RapidOCR(params=...)` → `boxes/txts/scores`|Apache-2.0|
|RapidTable|https://github.com/RapidAI/RapidTable|`v3.0.0` / `03cbe1e0e427629bd2ce584d9054b8c3fc40a9f1`|`RapidTable(RapidTableInput(...))` → `pred_htmls/cell_bboxes/logic_points`|Apache-2.0|
|RapidLayout|https://github.com/RapidAI/RapidLayout|PyPI `1.2.1`；尽调提交 `3f9b92213979488f4debd8a89fac72607b1e126f`|`RapidLayout(model_type="pp_doc_layoutv3")` → `boxes/class_names/scores`|Apache-2.0|

没有复制上游项目代码；迁移的是稳定 API 形状、模型配置和 adapter 设计。依赖与模型清单分别由 `backend/requirements-ocr.lock`、`data/ocr_model_manifest.json` 固定。RapidOCR 固定 tag 缺少较新主分支的 `MODEL_LICENSES.md`，所以包装器代码许可已确认、模型再分发许可未完成确认，两者不能混写。

## 同机 POC

- 环境：Windows 11、Python 3.12、ONNX Runtime CPU；OCR intra/inter threads = 2/1。
- 输入：亿纬锂能 2025 年报，官方文件 SHA256 `3bee0ca9a6232c60c53f195d078446a45fd4941bd997258b474cebe835eea3b8`，第 9 页，595.2 × 842.04 pt、rotation 0，以 144 DPI 渲染为 1191 × 1685 px；渲染图 SHA256 `28f643ae84ccf5e32e20bed05c2a053db6b40fff2d6a363e2b43ceeab758008`。
- RapidOCR：暖缓存初始化 1.492 秒、推理 37.084 秒、104 行。标题“五、主要会计数据和财务指标”及表内文字可读，输出为真实四点像素框。
- RapidLayout：初始化 23.669 秒、推理 8.544 秒、20 个区域；检出 3 个 table，分数分别为 0.9192、0.9756、0.9595。主表框 `[111,434,1089,818]` 与人工裁剪 `[110,435,1092,825]` 接近。
- RapidTable：对主表裁剪初始化 6.518 秒、流水线 24.285 秒，生成 11 行 × 5 列 HTML、55 个 cell 多边形和 `[row_start,row_end,col_start,col_end]` 逻辑坐标。
- 模型哈希：OCR det `090f04...f94f`、cls `e47ace...215c`、rec `6f3272...4884`；SLANet Plus `d57a94...14b`；PP-DocLayoutV3 `250dba...aa67`，均与固定上游清单相符。
- 基础依赖与 OCR 可选依赖在现有项目 `.venv` 同装后，`python -m pip check` 输出 `No broken requirements found.`。

## 可复现入口

先安装基础锁与可选锁；首次执行可能按固定 URL 下载模型到本地环境，普通 CI 不运行该步骤：

```powershell
python -m pip install -r backend/requirements.lock -r backend/requirements-ocr.lock
python tools/ocr_poc.py --input .runtime/company-sources/eve-2025.pdf --pages 9 --dpi 144 --run-ocr --run-layout --run-table --table-crop 110,435,1092,825
```

工具输出输入哈希、包版本、模型哈希、耗时、文字框、版面框、cell 坐标和 PDF 仿射。它不读取答案文件，也不写数据库、Dataset、Fact 或复核状态。非零旋转或非零 cropbox 原点页在 G7.0 明确将 PDF 坐标置空，避免伪坐标；完整旋转/裁剪变换属于 G7.2 产品实现。

## 未完成与否决边界

- 本次只有原生文本 PDF 的栅格化 POC；没有真实扫描文字、真实扫描财务表、混合、旋转、低清各 5 页，不能声称完成 G7.0 最终评测集。
- 没有 20 页/60 字段人工金标准、held-out split、p50/p95、峰值内存、Ubuntu 或第二机复现数据。
- 没有同集运行 PP-StructureV3，因此只做默认候选选择；若 held-out 门禁失败，必须回到同样本对比。
- OCR confidence 是引擎评分，不是校准后的正确概率；所有输出仍须人工复核。
