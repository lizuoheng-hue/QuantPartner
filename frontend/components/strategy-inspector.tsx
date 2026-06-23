import { ChevronDown, Code2, Play, ShieldCheck } from "lucide-react";
import type { StrategySpec } from "@/lib/types";

interface StrategyInspectorProps {
  spec: StrategySpec;
  code: string;
  onChange: (spec: StrategySpec) => void;
  onRun: () => void;
  busy: boolean;
}

function cloneSpec(spec: StrategySpec): StrategySpec {
  return structuredClone(spec);
}

function FieldRow({ label, children }: { label: string; children: React.ReactNode }) {
  return <label className="field-row"><span>{label}</span>{children}</label>;
}

export function StrategyInspector({ spec, code, onChange, onRun, busy }: StrategyInspectorProps) {
  const entry = spec.entry.conditions[0];
  const exit = spec.exit.conditions[0];
  const updateStopLoss = (value: number) => {
    const next = cloneSpec(spec);
    next.exit.risk_controls.stop_loss_pct = value;
    onChange(next);
  };
  const updateDate = (key: "start_date" | "end_date", value: string) => {
    const next = cloneSpec(spec);
    next.backtest[key] = value;
    onChange(next);
  };
  const updateMarket = (market: StrategySpec["universe"]["market"]) => {
    const next = cloneSpec(spec);
    const benchmarks = { CN_A: "000300.SH", HK: "HSI.HK", US: "SPY.US" } as const;
    next.universe.market = market;
    next.universe.index = benchmarks[market];
    next.backtest.benchmark = benchmarks[market];
    onChange(next);
  };
  const poolNames = { CN_A: "沪深300成分股", HK: "港股（恒生指数基准）", US: "美股（标普500基准）" };
  const currency = spec.universe.market === "HK" ? "HKD" : spec.universe.market === "US" ? "USD" : "CNY";

  return (
    <aside className="inspector">
      <div className="panel-heading inspector-title"><h2>策略条件</h2><span className="saved-state"><ShieldCheck size={14} /> 已校验</span></div>
      <div className="condition-sections">
        <section className="condition-section">
          <header><span>1. 选股条件</span><button aria-label="折叠"><ChevronDown size={16} /></button></header>
          <FieldRow label="市场"><select value={spec.universe.market} onChange={event => updateMarket(event.target.value as StrategySpec["universe"]["market"])}><option value="CN_A">中国 A 股</option><option value="HK">港股</option><option value="US">美股</option></select></FieldRow>
          <FieldRow label="股票池"><input value={poolNames[spec.universe.market]} disabled /></FieldRow>
          <FieldRow label="过滤条件"><input value={spec.universe.filters.length ? `${spec.universe.filters.length} 条基本面规则` : "无额外过滤"} disabled /></FieldRow>
        </section>
        <section className="condition-section">
          <header><span>2. 买入条件</span><button aria-label="折叠"><ChevronDown size={16} /></button></header>
          <FieldRow label="信号"><input value={`${entry.field} · ${entry.operator}`} disabled /></FieldRow>
          {entry.params.fast ? <FieldRow label="快线周期"><input type="number" value={entry.params.fast} onChange={() => undefined} /></FieldRow> : null}
          {entry.params.slow ? <FieldRow label="慢线周期"><input type="number" value={entry.params.slow} onChange={() => undefined} /></FieldRow> : null}
        </section>
        <section className="condition-section">
          <header><span>3. 卖出与风控</span><button aria-label="折叠"><ChevronDown size={16} /></button></header>
          <FieldRow label="卖出信号"><input value={`${exit.field} · ${exit.operator}`} disabled /></FieldRow>
          <FieldRow label="止损"><div className="input-unit"><input aria-label="止损比例" type="number" min="0" max="50" value={spec.exit.risk_controls.stop_loss_pct ?? 0} onChange={event => updateStopLoss(Number(event.target.value))} /><span>%</span></div></FieldRow>
          <FieldRow label="最大仓位"><div className="input-unit"><input type="number" value={spec.exit.risk_controls.max_position_pct ?? 100} onChange={() => undefined} /><span>%</span></div></FieldRow>
        </section>
        <section className="condition-section">
          <header><span>4. 回测范围</span><button aria-label="折叠"><ChevronDown size={16} /></button></header>
          <FieldRow label="开始日期"><input type="date" value={spec.backtest.start_date} onChange={event => updateDate("start_date", event.target.value)} /></FieldRow>
          <FieldRow label="结束日期"><input type="date" value={spec.backtest.end_date} onChange={event => updateDate("end_date", event.target.value)} /></FieldRow>
          <FieldRow label="初始资金"><input value={spec.backtest.initial_capital.toLocaleString("zh-CN", { style: "currency", currency, maximumFractionDigits: 0 })} disabled /></FieldRow>
        </section>
      </div>
      <details className="code-preview">
        <summary><Code2 size={16} /> 查看策略代码（只读）<ChevronDown size={15} /></summary>
        <pre>{code}</pre>
      </details>
      <button className="primary-button run-button" onClick={onRun} disabled={busy}><Play size={18} fill="currentColor" />{busy ? "正在提交…" : "运行回测"}</button>
    </aside>
  );
}
