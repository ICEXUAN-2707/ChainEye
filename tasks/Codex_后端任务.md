# Codex 后端开发任务

项目基线 v0.2，R1骨架已实现。你负责backend、migrations、领域模型、工具、编排和契约生成。先读README、validation/R1验收记录.md、`docs/Phase_1/06_严格交叉自检.md`、`docs/Phase_1/01_PRD.md`和`docs/Phase_1/02_SPEC.md`。禁止重新设计一套模型或将fixture读取说成自动提取。

## 先执行复核
```bash
python -m pip install -r backend/requirements.lock
PYTHONPATH=backend/src python -m unittest discover -s tests -v
PYTHONPATH=backend/src python tools/verify_baseline.py
PYTHONPATH=backend/src python tools/export_contracts.py
python tools/generate_ts.py
```
PowerShell先设置 `$env:PYTHONPATH="backend/src"`，再省略命令前缀。运行前后contracts和generated.ts不得意外变化。独立本机执行安装和截图，补齐环境验收记录。

## 下一开发块 R2
只实现PDF上传、解析候选事实、来源定位、字段复核和revision/version事务。按现有SourceAttachment和FactCorrection接口实施；对其他功能保留明确501。
采用30MiB/500页/5文件限制；验证实际PDF签名和加密状态；只有文本型PDF支持自动候选提取，扫描件明确needs_review。字段提取必须识别表头、行名、列年、单位与合并范围，不能只是查数值是否出现。
候选字段默认extracted或needs_review；模型无权将其置verified。人工通过PATCH复核，更正原值和规范值须一致。字段缺失用missing+null+reason。
复核生成新Fact revision和Dataset版本；快照引用和更正日志原子落库。ID去重与source复用不能把其他数据包的上下文写进Source元数据。PDF原件哈希不可覆盖。
输出未人工更正的提取准确率和覆盖率；分业务基线关键字段必须全部正确。以30标注为调试集，额外保留未见材料验证。

## 文件所有权与协作
允许backend/**、tools/export_contracts.py、contracts/**、相关tests/**、后端验收记录。frontend/src/api/generated.ts只能由工具生成，不手改；通知Claude重新生成后构建。前端组件由Claude维护。
契约变更必须先提交说明，更新模型、生成规范、更新前端类型及测试。不得默默删单位/期间/证据字段。
每轮交付代码、命令、测试输出、接口变更、限制、下一轮阻塞；未通过项明确列出，不用截图替代数值测试。请另一开发者执行关键流程后再合并。
