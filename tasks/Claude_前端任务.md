# Claude 前端开发任务

项目基线 v0.2，R1本机工作台已能展示核对样本。负责frontend组件、页面状态、来源查看、交互和报告展示。先读README、PRD、Spec、docs/06_严格交叉自检.md以及contracts/openapi.json。使用frontend/src/api/generated.ts，不手写第二套Fact/ScenarioResult。

## 先复核
```bash
cd frontend
npm ci
npm run build
npm run dev
```
另一个终端在项目根运行 `python tools/start_backend.py`。前端固定127.0.0.1:5173，后端固定127.0.0.1:8000；端口冲突会报错，不自动切到未允许的端口。
检查样本30条、业务筛选、空数据、请求失败、证据打开、PDF页码跳转，截图并记录结果。不得把预置数据标成自动提取成功。

## 下一开发块 R2
实现上传、提取进度、原始值/规范值/单位/期间/业务/状态显示、缺失与冲突、人工复核表单。
使用SourceAttachment响应更新Dataset.version；查询事实显式携带version。PATCH带expected_revision和reason；409时提示重新读取，不覆盖别人的更正。
金额输入提交十进制字符串，参数同样字符串，不用parseFloat回写；前端只格式化，不计算权威财务结果。用户复核时同时展示原文，避免脱离证据改数字。
后端未实现返回501时呈现“尚待实现”，不能用虚构成功结果替代。禁止生成任意假引用或在前端猜测模型结果。

## 协作范围
允许frontend/**，但generated.ts必须通过tools/generate_ts.py生成。接口语义由后端模型生成；发现缺字段列出具体用户任务、请求和期望响应，先共同更新契约再写组件。
严禁触碰backend公式、数据库迁移、facts.json和金标准。后端测试通过后，至少人工验证一个输入到原文来源的流程，再合并前端PR。
交付构建结果、页面状态清单、桌面和窄屏截图、接口调用样例及未完成项。
