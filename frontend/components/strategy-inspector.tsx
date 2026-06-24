import { ChevronDown, Code2, Play, ShieldCheck, Trash2 } from "lucide-react";
import { useState } from "react";
import type { Condition, Operator, StrategySpec } from "@/lib/types";

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

const operators: Operator[] = ["GT", "GTE", "LT", "LTE", "EQ", "CROSS_ABOVE", "CROSS_BELOW"];
const fields = ["CLOSE", "OPEN", "VOLUME", "EMA", "MA", "MOMENTUM", "PE_TTM", "ROE"];

export function StrategyInspector({ spec, code, onChange, onRun, busy }: StrategyInspectorProps) {
  const [diffNotice, setDiffNotice] = useState<string | null>(null);
  const entry = spec.entry.conditions[0];
  const exit = spec.exit.conditions[0];
  const notify = (message: string) => setDiffNotice(message);
  const updateCondition = (group: "filters" | "entry" | "exit", index: number, patch: Partial<Condition>) => {
    const next = cloneSpec(spec);
    const list = group === "filters" ? next.universe.filters : group === "entry" ? next.entry.conditions : next.exit.conditions;
    list[index] = { ...list[index], ...patch };
    notify("策略条件清单已更新，建议重新运行回测验证指标差异。");
    onChange(next);
  };
  const removeCondition = (group: "filters" | "entry" | "exit", index: number) => {
    const next = cloneSpec(spec);
    const list = group === "filters" ? next.universe.filters : group === "entry" ? next.entry.conditions : next.exit.conditions;
    if (group !== "filters" && list.length <= 1) {
      list[index].enabled = false;
      notify("核心买卖条件至少保留一条记录，已改为禁用状态。");
    } else {
      list.splice(index, 1);
      notify("已删除一条策略条件，当前策略结构已变更。");
    }
    onChange(next);
  };
  const renderConditionRows = (group: "filters" | "entry" | "exit", conditions: Condition[]) => (
    <div className="condition-list">
      {conditions.length ? conditions.map((condition, index) => (
        <div className={`condition-row ${condition.enabled ? "" : "disabled"}`} key={`${group}-${index}`}>
          <label className="condition-switch"><input type="checkbox" checked={condition.enabled} onChange={event => updateCondition(group, index, { enabled: event.target.checked })} /><span>{condition.enabled ? "启用" : "禁用"}</span></label>
          <select value={condition.field} onChange={event => updateCondition(group, index, { field: event.target.value })}>{fields.map(field => <option key={field} value={field}>{field}</option>)}</select>
          <select value={condition.operator} onChange={event => updateCondition(group, index, { operator: event.target.value as Operator })}>{operators.map(operator => <option key={operator} value={operator}>{operator}</option>)}</select>
          <input value={String(condition.value)} onChange={event => updateCondition(group, index, { value: Number.isNaN(Number(event.target.value)) || event.target.value.trim() === "" ? event.target.value : Number(event.target.value) })} />
          <button type="button" aria-label="删除条件" onClick={() => removeCondition(group, index)}><Trash2 size={13} /></button>
        </div>
      )) : <p className="condition-empty">暂无条件</p>}
    </div>
  );
  const updateStopLoss = (value: number) => {
    const next = cloneSpec(spec);
    const previous = spec.exit.risk_controls.stop_loss_pct ?? 0;
    next.exit.risk_controls.stop_loss_pct = value;
    setDiffNotice(`止损从 ${previous}% 调整为 ${value}%。风险边界已变化，建议重新运行回测确认最大回撤。`);
    onChange(next);
  };
  const updateMaxPosition = (value: number) => {
    const next = cloneSpec(spec);
    const previous = spec.exit.risk_controls.max_position_pct ?? 100;
    next.exit.risk_controls.max_position_pct = value;
    setDiffNotice(`最大仓位从 ${previous}% 调整为 ${value}%，资金暴露已变化。`);
    onChange(next);
  };
  const updateDate = (key: "start_date" | "end_date", value: string) => {
    const next = cloneSpec(spec);
    const previous = next.backtest[key];
    next.backtest[key] = value;
    setDiffNotice(`${key === "start_date" ? "开始" : "结束"}日期从 ${previous} 调整为 ${value}，样本区间变化会影响收益和胜率。`);
    onChange(next);
  };
  const updateMarket = (market: StrategySpec["universe"]["market"]) => {
    const next = cloneSpec(spec);
    const benchmarks = { CN_A: "000300.SH", HK: "HSI.HK", US: "SPY.US" } as const;
    const previous = spec.universe.market;
    next.universe.market = market;
    next.universe.index = benchmarks[market];
    next.backtest.benchmark = benchmarks[market];
    setDiffNotice(`市场从 ${previous} 切换到 ${market}，基准、币种与数据源都会同步切换。`);
    onChange(next);
  };
  const poolNames = { CN_A: "沪深300成分股", HK: "港股（恒生指数基准）", US: "美股（标普500基准）" };
  const currency = spec.universe.market === "HK" ? "HKD" : spec.universe.market === "US" ? "USD" : "CNY";

  return (
    <aside className="inspector">
      <div className="panel-heading inspector-title"><h2>策略条件</h2><span className="saved-state"><ShieldCheck size={14} /> 已校验</span></div>
      {diffNotice ? (
        <div className="diff-notice" role="status">
          <strong>参数变化</strong>
          <span>{diffNotice}</span>
          <button type="button" onClick={() => setDiffNotice(null)} aria-label="关闭参数变化提示">关闭</button>
        </div>
      ) : null}
      <div className="condition-sections">
        <section className="condition-section">
          <header><span>1. 选股条件</span><button aria-label="折叠"><ChevronDown size={16} /></button></header>
          <FieldRow label="市场"><select value={spec.universe.market} onChange={event => updateMarket(event.target.value as StrategySpec["universe"]["market"])}><option value="CN_A">中国 A 股</option><option value="HK">港股</option><option value="US">美股</option></select></FieldRow>
          <FieldRow label="股票池"><input value={poolNames[spec.universe.market]} disabled /></FieldRow>
          {renderConditionRows("filters", spec.universe.filters)}
        </section>
        <section className="condition-section">
          <header><span>2. 买入条件</span><button aria-label="折叠"><ChevronDown size={16} /></button></header>
          {renderConditionRows("entry", spec.entry.conditions)}
          {entry?.params.fast ? <FieldRow label="快线周期"><input type="number" value={entry.params.fast} onChange={event => updateCondition("entry", 0, { params: { ...entry.params, fast: Number(event.target.value) } })} /></FieldRow> : null}
          {entry?.params.slow ? <FieldRow label="慢线周期"><input type="number" value={entry.params.slow} onChange={event => updateCondition("entry", 0, { params: { ...entry.params, slow: Number(event.target.value) }, value: Number(event.target.value) })} /></FieldRow> : null}
        </section>
        <section className="condition-section">
          <header><span>3. 卖出与风控</span><button aria-label="折叠"><ChevronDown size={16} /></button></header>
          {renderConditionRows("exit", spec.exit.conditions)}
          <FieldRow label="止损"><div className="input-unit"><input aria-label="止损比例" type="number" min="0" max="50" value={spec.exit.risk_controls.stop_loss_pct ?? 0} onChange={event => updateStopLoss(Number(event.target.value))} /><span>%</span></div></FieldRow>
          <FieldRow label="最大仓位"><div className="input-unit"><input type="number" min="1" max="100" value={spec.exit.risk_controls.max_position_pct ?? 100} onChange={event => updateMaxPosition(Number(event.target.value))} /><span>%</span></div></FieldRow>
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
