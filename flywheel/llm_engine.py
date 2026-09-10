# -*- coding: utf-8 -*-
"""
llm_engine.py —— 真实大模型推理引擎（OpenAI 兼容 REST API，标准库直连）
------------------------------------------------------------------------
用 Python 标准库 urllib 直接调 OpenAI 兼容的 /chat/completions，
不依赖 openai SDK —— 彻底避开版本冲突（openai 3.x 内置的 aiohttp
传输层与新版 aiohttp 不兼容，属 openai 自身 bug）。

接入三步：
1. 注册拿 API Key（推荐智谱 GLM-4-Flash 免费：open.bigmodel.cn → API Keys）
2. export LLM_API_KEY=sk-xxx        # 不要贴进任何聊天窗口
3. python run_demo_llm.py [provider]

兼容：智谱 GLM / DeepSeek / 豆包（火山方舟）/ OpenAI（改 base_url + model 即可）。
"""
import json
import os
import urllib.error
import urllib.request
from pathlib import Path

from biostat_engine import BiostatEngine  # 复用资产加载与召回逻辑

ROOT = Path(__file__).resolve().parent

# OpenAI 兼容端点配置（按需切换 provider）
PROVIDERS = {
    # 智谱 GLM-4-Flash：免费、国内直连 —— demo 零成本首选
    "zhipu": {"base_url": "https://open.bigmodel.cn/api/paas/v4", "model": "glm-4-flash"},
    # DeepSeek：极低价、质量好
    "deepseek": {"base_url": "https://api.deepseek.com/v1", "model": "deepseek-chat"},
    # 豆包（火山方舟）：model 填你的"推理接入点 ID"(ep-xxx) 或模型名
    "doubao": {"base_url": "https://ark.cn-beijing.volces.com/api/v3", "model": "doubao-seed-1-6-250615"},
    "openai": {"base_url": "https://api.openai.com/v1", "model": "gpt-4o-mini"},
}

SYSTEM_TEMPLATE = """你是一位严谨的生物统计分析师，负责解答生存分析问题。你的回答必须：
1. 只使用【资产层】提供的事实与数值，不得编造或臆测任何统计量；数值必须与资产完全一致，禁止改写 HR/CI/p 的具体数字；
2. 按固定结构输出：结论 → 方法与口径 → 关键数值 → 方法学诊断 → 局限声明；
3. 资产中出现的每一个关键数值与变量列表（HR、95%CI、p 值、C-index、VIMP 排序、变量名单等）都必须完整出现在回答中，不得省略、改写或只给结论；
4. 结尾必须写【局限声明】：结合数据来源说明外推限制；若资产未提供数据概况，则明确写"数据概况未知"。

【标准回答示例】（请模仿其结构与完整度，把每个数值都列出来）
结论：激素治疗显著降低无复发生存风险。
方法与口径：多变量 Cox PH，调整 age/tsize/pnodes/estrec/progrec/menostat/tgrade。
关键数值：
- HR=0.707，95%CI 0.549–0.911，p=0.0073
- C-index=0.692；LR/Wald/Score 均 p<2e-16
方法学诊断：
- 主暴露 PH 成立（p=0.625）；GLOBAL 违反（p=0.0037）
- 独立预后因素：horTh/tsize/pnodes/progrec/tgrade.L；非独立：age(0.309)/estrec(0.661)/menostat(0.159)/tgrade.Q(0.099)
- estrec 与 progrec 共线（ρ=0.60），调整后信号被分走
- 稳健性：单变量 0.695 / 主模型 0.707 / 分层 0.699，三模型 HR≈0.70 且 CI 重叠
局限声明：GBSG2 为 686 例历史试验数据，外推需谨慎。

【口径字典】
{metrics}

【统计方法知识】
{knowledge}

【历史纠错提醒】
{fewshot}
"""


class LLMEngine(BiostatEngine):
    def __init__(self, asset_level="full", provider="zhipu",
                 api_key=None, temperature=0.2):
        super().__init__(asset_level)
        conf = PROVIDERS[provider]
        self.url = conf["base_url"].rstrip("/") + "/chat/completions"
        self.model = conf["model"]
        self.temperature = temperature
        self.api_key = api_key or os.environ.get("LLM_API_KEY", "")
        if not self.api_key:
            raise RuntimeError("未设置 API Key：export LLM_API_KEY=sk-xxx")

    def answer(self, query: str) -> str:
        """一次推理：召回资产 -> 注入 prompt -> LLM 生成（与确定性引擎同签名）。"""
        tags = self._tags_of(query)
        metrics = self._recall(self.metrics, tags)
        knowledge = self._recall(self.knowledge, tags)
        fewshot = self._recall(self.fewshot, tags)

        system = SYSTEM_TEMPLATE.format(
            metrics="\n".join(f"- {m['name']}：{m['definition']}" for m in metrics) or "（无）",
            knowledge="\n".join(f"- {k['factor']}：{k['detail']}" for k in knowledge) or "（无）",
            fewshot="\n".join(f"- {f['lesson']}" for f in fewshot) or "（无）",
        )
        payload = {
            "model": self.model,
            "temperature": self.temperature,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": query},
            ],
        }
        req = urllib.request.Request(
            self.url,
            data=json.dumps(payload).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.api_key}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "ignore")
            raise RuntimeError(f"API 请求失败 HTTP {e.code}: {body[:500]}")
        except urllib.error.URLError as e:
            raise RuntimeError(f"网络错误: {e.reason}")

        try:
            return data["choices"][0]["message"]["content"] or ""
        except (KeyError, IndexError):
            raise RuntimeError(f"响应格式异常: {json.dumps(data, ensure_ascii=False)[:500]}")
