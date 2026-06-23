import json
import re

import httpx

from .config import get_settings
from .schemas import ComplianceStatus, ParseResponse
from .templates import ema_template, momentum_template, value_template


BLOCKED_PATTERNS = re.compile(r"(翻倍|稳赚|必涨|保证收益|推荐.*股票|下个?月.*涨|未来.*收益)")
CAUTION_PATTERNS = re.compile(r"(看好|可能上涨|潜力|市场情绪)")
NUMBER = r"(\d+(?:\.\d+)?)"


def generate_code_preview(spec) -> str:
    entry = spec.entry.conditions[0]
    exit_condition = spec.exit.conditions[0]
    risk = spec.exit.risk_controls
    return f'''# 由 StrategySpecV1 确定性生成，仅供审阅
def strategy(context, data):
    universe = index_members("{spec.universe.index}")
    entry_signal = condition("{entry.field}", "{entry.operator.value}", {entry.value!r}, {entry.params!r})
    exit_signal = condition("{exit_condition.field}", "{exit_condition.operator.value}", {exit_condition.value!r}, {exit_condition.params!r})

    if entry_signal and not context.position:
        context.buy_next_open(max_position={risk.max_position_pct or 100} / 100)
    elif exit_signal or context.drawdown_from_entry >= {(risk.stop_loss_pct or 0)} / 100:
        context.sell_next_open()
'''


def _blocked_response() -> ParseResponse:
    return ParseResponse(
        spec=None,
        confidence=1,
        compliance_status=ComplianceStatus.BLOCKED,
        message="根据监管要求，无法提供个股收益预测或投资建议。你可以改为描述一条可验证的历史策略规则。",
        provider="compliance-rules",
    )


def _extract_json(content: str) -> dict:
    cleaned = content.strip()
    if cleaned.startswith("```"):
        cleaned = re.sub(r"^```(?:json)?\s*|\s*```$", "", cleaned, flags=re.I)
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("模型未返回 JSON")
    return json.loads(cleaned[start : end + 1])


def _llm_parse(text: str, *, provider: str, url: str, model: str, api_key: str) -> ParseResponse:
    system_prompt = """你是 QuantPartner 的策略结构化解析器。只返回一个 JSON 对象，不要 Markdown。
用户输入只能被转换为历史回测规则，禁止个股推荐、收益承诺和未来预测。
JSON 字段：spec, confidence, clarification_questions, message。
spec 必须符合 StrategySpecV1：schema_version 固定为 1.0；universe 仅允许 CN_A 和 000300.SH；
Condition.field 仅允许 CLOSE, OPEN, VOLUME, EMA, MA, MOMENTUM, PE_TTM, ROE；
operator 仅允许 GT, GTE, LT, LTE, EQ, CROSS_ABOVE, CROSS_BELOW；
四部分为 universe、entry、exit（含 risk_controls）、backtest。
默认回测区间 2019-01-01 至 2026-06-19，基准 000300.SH，初始资金 1000000，daily 调仓。
信息不足时保留最接近的安全模板并在 clarification_questions 中提问，不得编造参数。"""
    response = httpx.post(
        url,
        headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"},
        json={
            "model": model,
            "temperature": 0,
            "response_format": {"type": "json_object"},
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": text},
            ],
        },
        timeout=15,
    )
    response.raise_for_status()
    payload = _extract_json(response.json()["choices"][0]["message"]["content"])
    from .schemas import StrategySpecV1

    spec = StrategySpecV1.model_validate(payload["spec"])
    return ParseResponse(
        spec=spec,
        confidence=float(payload.get("confidence", 0.8)),
        clarification_questions=payload.get("clarification_questions", []),
        compliance_status=ComplianceStatus.CAUTION if CAUTION_PATTERNS.search(text) else ComplianceStatus.SAFE,
        message=payload.get("message", "已将想法转换为可执行策略，请确认参数。"),
        provider=provider,
        code_preview=generate_code_preview(spec),
    )


def _rule_parse(text: str) -> ParseResponse:
    if BLOCKED_PATTERNS.search(text):
        return _blocked_response()

    caution = bool(CAUTION_PATTERNS.search(text))
    normalized = text.upper().replace("上穿", " CROSS_ABOVE ").replace("下穿", " CROSS_BELOW ")

    if any(word in normalized for word in ["EMA", "均线", "双均线"]):
        spec = ema_template()
        ema_periods = [int(v) for v in re.findall(r"EMA\s*(\d+)", normalized)]
        if len(ema_periods) >= 2:
            fast, slow = sorted(ema_periods[:2])
            spec.entry.conditions[0].value = slow
            spec.entry.conditions[0].params = {"fast": fast, "slow": slow}
            spec.exit.conditions[0].params = {"period": fast}
        stop = re.search(NUMBER + r"\s*%?\s*止损", text)
        if stop:
            spec.exit.risk_controls.stop_loss_pct = float(stop.group(1))
        confidence = 0.95 if len(ema_periods) >= 2 else 0.78
        questions = [] if len(ema_periods) >= 2 else ["请确认快线和慢线周期，例如 EMA20 与 EMA60。"]
    elif any(word in text for word in ["PE", "市盈率", "ROE", "价值"]):
        spec = value_template()
        pe = re.search(r"(?:PE|市盈率)\s*(?:低于|<|小于)\s*" + NUMBER, text, re.I)
        roe = re.search(r"ROE\s*(?:高于|>|大于)\s*" + NUMBER, text, re.I)
        if pe:
            spec.universe.filters[0].value = float(pe.group(1))
        if roe:
            spec.universe.filters[1].value = float(roe.group(1))
            spec.entry.conditions[0].value = float(roe.group(1))
        confidence = 0.9
        questions = []
    elif any(word in text for word in ["动量", "突破", "新高"]):
        spec = momentum_template()
        period = re.search(NUMBER + r"\s*日", text)
        if period:
            spec.entry.conditions[0].params["period"] = int(float(period.group(1)))
            spec.exit.conditions[0].params["period"] = int(float(period.group(1)))
            spec.name = f"{int(float(period.group(1)))}日动量"
        confidence = 0.86
        questions = []
    else:
        spec = ema_template()
        confidence = 0.45
        questions = ["你的描述还缺少明确的买入和卖出条件。要从双均线、动量或价值质量模板开始吗？"]

    status = ComplianceStatus.CAUTION if caution else ComplianceStatus.SAFE
    message = "已将想法转换为可执行策略，请在右侧确认参数。"
    if caution:
        message = "该描述含有推测性表达；已仅保留可验证的历史规则。"
    return ParseResponse(
        spec=spec,
        confidence=confidence,
        clarification_questions=questions,
        compliance_status=status,
        message=message,
        provider="deterministic-parser",
        code_preview=generate_code_preview(spec),
    )


def parse_strategy(text: str) -> ParseResponse:
    # 红线请求不发送给任何外部模型。
    if BLOCKED_PATTERNS.search(text):
        return _blocked_response()
    settings = get_settings()
    providers = [
        ("deepseek", settings.deepseek_api_url, settings.deepseek_model, settings.deepseek_api_key),
        ("kimi", settings.kimi_api_url, settings.kimi_model, settings.kimi_api_key),
    ]
    for provider, url, model, api_key in providers:
        if not api_key:
            continue
        try:
            return _llm_parse(text, provider=provider, url=url, model=model, api_key=api_key)
        except (httpx.HTTPError, KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
    return _rule_parse(text)
