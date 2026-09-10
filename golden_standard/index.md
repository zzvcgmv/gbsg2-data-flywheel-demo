# golden_standard/ — 金标准接口目录

本目录是 R 侧（金标准生产）与 Python 侧（飞轮循环）之间的**接口**：R 按固定格式写，Python 评估器按固定格式读。

## 接口 Schema（字段约定）

每份文件是一个 JSON 对象：

| 字段 | 类型 | 含义 | 消费方 |
|---|---|---|---|
| `question_id` | string | 题号 | 评估器 |
| `question` | string | 题目全文 | AI 引擎 |
| `analysis_target` | string | 分析类型标签（cox / cox_stratified / cox_coding / rsf_vs_cox） | 评估器分组 |
| `golden_answer.method` | string | 金标准方法与模型设定 | 检查点比对 |
| `golden_answer.hr / ci95 / p` | number / array | 数值答案（Cox 系） | 数值核对 |
| `golden_answer.ph_test` | string | PH 假设结论 | 检查点比对 |
| `golden_answer.conclusion` | string | 一句话结论 | 参考 |
| `golden_answer.key_points` | string[] | 检查点清单 | **主评分依据** |

## 文件清单

| 文件 | 问题 | 检查点数 | 状态 |
|---|---|---|---|
| `q01.json` | 激素治疗调整后效应（主分析） | 7 | ✅ 真实运行 |
| `q02.json` | 独立预后因素 / estrec 掉队 | 4 | ✅ 真实运行 |
| `q03.json` | tgrade 编码选择（线性 vs 因子） | 5 | ✅ 真实运行 |
| `q04.json` | PH 违反处理（分层敏感性） | 5 | ✅ 真实运行 |
| `q05.json` | RSF vs Cox（C-index + VIMP） | 6 | ✅ 真实运行 |

合计：5 题 · 27 检查点。

## 来源与可复现性

- 数据：GBSG2（686 例，事件 299），R 加载，列名 `time` / `cens`（cens=1 为复发）
- 模型：R `survival` / `ranger`；`set.seed(42)` 固定保证可复现
- Q6（贝叶斯后验）待定：Colab/PyMC 或 R MCMCpack，作为二期资产，不阻塞飞轮
