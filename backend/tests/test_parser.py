from types import SimpleNamespace

import app.parser as parser
from app.parser import parse_strategy
from app.schemas import ComplianceStatus


def test_ema_parse_extracts_periods_and_stop_loss():
    result = parse_strategy("沪深300里，EMA20上穿EMA60买入，跌破EMA20卖出，8%止损")
    assert result.compliance_status == ComplianceStatus.SAFE
    assert result.spec is not None
    assert result.spec.entry.conditions[0].params == {"fast": 20, "slow": 60}
    assert result.spec.exit.risk_controls.stop_loss_pct == 8


def test_redline_request_is_blocked():
    result = parse_strategy("推荐下个月能翻倍的股票")
    assert result.compliance_status == ComplianceStatus.BLOCKED
    assert result.spec is None


def test_value_parse():
    result = parse_strategy("找出市盈率低于15且ROE大于10%的公司")
    assert result.spec.universe.filters[0].value == 15
    assert result.spec.universe.filters[1].value == 10


def test_kimi_is_used_when_deepseek_fails(monkeypatch):
    settings = SimpleNamespace(
        deepseek_api_url="deepseek",
        deepseek_model="deepseek-chat",
        deepseek_api_key="configured",
        kimi_api_url="kimi",
        kimi_model="kimi",
        kimi_api_key="configured",
    )
    monkeypatch.setattr(parser, "get_settings", lambda: settings)

    def fake_llm(text, *, provider, **kwargs):
        if provider == "deepseek":
            raise ValueError("temporary model failure")
        result = parser._rule_parse(text)
        return result.model_copy(update={"provider": "kimi"})

    monkeypatch.setattr(parser, "_llm_parse", fake_llm)
    result = parser.parse_strategy("EMA20上穿EMA60，8%止损")
    assert result.provider == "kimi"
