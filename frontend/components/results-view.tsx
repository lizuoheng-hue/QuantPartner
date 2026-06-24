import { ArrowLeft, CheckCircle2, Code2, Copy, Download, Save, Share2, Sparkles } from "lucide-react";
import { useState } from "react";
import type { BacktestDiagnosis, BacktestResult, StrategySpec } from "@/lib/types";
import { CodeDialog } from "./code-dialog";
import { EquityChart } from "./equity-chart";

const metricLabels: Record<string, string> = {
  annual_return: "年化收益",
  max_drawdown: "最大回撤",
  sharpe: "夏普比率",
  win_rate: "胜率",
  profit_loss_ratio: "盈亏比",
  alpha: "Alpha",
  beta: "Beta",
};

function metricValue(key: string, value: number) {
  if (["annual_return", "max_drawdown", "win_rate"].includes(key)) return `${(value * 100).toFixed(1)}%`;
  if (key === "alpha") return value.toFixed(3);
  return value.toFixed(2);
}

function dataSourceLabel(result: BacktestResult) {
  if (result.data_snapshot) {
    const provider = result.data_snapshot.provider === "tushare" ? "Tushare" : result.data_snapshot.provider;
    return `${provider} · ${result.data_snapshot.symbol} · ${result.data_snapshot.rows.toLocaleString()}条`;
  }
  if (result.data_source.includes("fallback")) return "演示数据 · 已降级";
  if (result.data_source.includes("deterministic-demo")) return "演示数据";
  return result.data_source;
}

function csvCell(value: string | number) {
  const text = String(value);
  return /[",\n]/.test(text) ? `"${text.replaceAll("\"", "\"\"")}"` : text;
}

interface ResultsViewProps {
  result: BacktestResult;
  spec: StrategySpec;
  onEdit: () => void;
  onSave: () => void;
  onApplySuggestion: (patch: Record<string, unknown> | null | undefined, title: string) => void;
  saving: boolean;
}

export function ResultsView({ result, spec, onEdit, onSave, onApplySuggestion, saving }: ResultsViewProps) {
  const [codeOpen, setCodeOpen] = useState(false);
  const [copiedSuggestion, setCopiedSuggestion] = useState<string | null>(null);
  const [copiedReport, setCopiedReport] = useState(false);
  const visibleCode = result.code_preview || JSON.stringify(spec, null, 2);
  const diagnosis: BacktestDiagnosis = result.diagnosis ?? {
    summary: result.summary,
    disclaimer: result.disclaimer,
    items: [],
    suggestions: [],
  };
  const exportTrades = () => {
    const rows = [
      ["date", "symbol", "name", "side", "price", "quantity", "fee"],
      ...result.trades.map(trade => [trade.date, trade.symbol, trade.name, trade.side, trade.price, trade.quantity, trade.fee]),
    ];
    const csv = rows.map(row => row.map(csvCell).join(",")).join("\n");
    const blob = new Blob([`\uFEFF${csv}`], { type: "text/csv;charset=utf-8" });
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url;
    link.download = `quantpartner-trades-${result.strategy_hash}.csv`;
    link.click();
    URL.revokeObjectURL(url);
  };
  const copySuggestion = async (title: string, text: string) => {
    await navigator.clipboard.writeText(text);
    setCopiedSuggestion(title);
    window.setTimeout(() => setCopiedSuggestion(null), 1600);
  };
  const shareReport = async () => {
    const report = [
      `QuantPartner 回测摘要：${spec.name}`,
      "",
      `一、AI 一句话总结`,
      diagnosis.summary,
      "",
      "二、核心指标",
      ...Object.entries(result.metrics).map(([key, value]) => `${metricLabels[key] ?? key}: ${metricValue(key, value)}`),
      "",
      "三、改进建议",
      ...diagnosis.suggestions.map((item, index) => `${index + 1}. ${item.title}：${item.rationale}`),
      "",
      result.disclaimer,
    ].join("\n");
    await navigator.clipboard.writeText(report);
    setCopiedReport(true);
    window.setTimeout(() => setCopiedReport(false), 1600);
  };

  return (
    <main className="results-view">
      <header className="results-header">
        <div><h1>{spec.name} · 回测结果</h1><span className="complete-state"><CheckCircle2 size={14} /> 已完成</span></div>
        <div className="results-actions"><button className="secondary-button" onClick={onEdit}><ArrowLeft size={15} />继续迭代</button><button className="secondary-button" onClick={shareReport}><Share2 size={15} />{copiedReport ? "已复制" : "分享报告"}</button><button className="secondary-button" onClick={exportTrades} disabled={!result.trades.length}><Download size={15} />导出交易</button><button className="primary-button" onClick={onSave} disabled={saving}><Save size={15} />{saving ? "保存中" : "保存版本"}</button></div>
      </header>
      <nav className="result-flow" aria-label="回测结果结构">
        <span><b>1</b>一句话总结</span>
        <span><b>2</b>核心指标</span>
        <span><b>3</b>详细图表诊断</span>
        <span><b>4</b>保存 / 迭代 / 分享</span>
      </nav>
      <section className="ai-diagnosis">
        <header>
          <div><Sparkles size={17} /><span><strong>1. AI 一句话总结与改进建议</strong><small>{diagnosis.disclaimer}</small></span></div>
          <em>规则诊断 · 可追溯指标</em>
        </header>
        <p className="diagnosis-summary">{diagnosis.summary}</p>
        {diagnosis.items.length ? <div className="diagnosis-grid">
          {diagnosis.items.map(item => (
            <article className={`diagnosis-card ${item.level}`} key={item.title}>
              <span>{item.title}</span>
              <p>{item.explanation}</p>
              <small>{item.metric_refs.map(key => metricLabels[key] ?? key).join(" / ")}</small>
            </article>
          ))}
        </div> : null}
        {diagnosis.suggestions.length ? <div className="suggestion-list">
          <h2>改进建议</h2>
          {diagnosis.suggestions.map((suggestion, index) => {
            const copyText = `${suggestion.title}\n${suggestion.rationale}\n${suggestion.safety_note}`;
            return (
              <article key={suggestion.title}>
                <b>{index + 1}</b>
                <span><strong>{suggestion.title}</strong><p>{suggestion.rationale}</p><small>{suggestion.safety_note}</small></span>
                <div className="suggestion-actions">
                  <button type="button" onClick={() => onApplySuggestion(suggestion.patch, suggestion.title)}><ArrowLeft size={14} />应用为草稿</button>
                  <button type="button" onClick={() => copySuggestion(suggestion.title, copyText)}><Copy size={14} />{copiedSuggestion === suggestion.title ? "已复制" : "复制"}</button>
                </div>
              </article>
            );
          })}
        </div> : null}
      </section>
      <header className="result-section-title"><span>2. 核心指标</span><small>用于判断收益、风险和交易效率</small></header>
      <section className="metrics-rail">
        {Object.entries(result.metrics).map(([key, value]) => <div key={key}><span>{metricLabels[key]}</span><strong className={key === "max_drawdown" ? "negative" : key === "annual_return" || key === "alpha" ? "positive" : ""}>{metricValue(key, value)}</strong></div>)}
      </section>
      <div className="result-grid">
        <div className="result-main">
          <section className="chart-panel"><header><h2>3. 详细图表诊断</h2><span>{dataSourceLabel(result)}</span></header><EquityChart strategy={result.equity_curve} benchmark={result.benchmark_curve} drawdown={result.drawdown_curve} /><p className="chart-diagnosis-note">上方曲线用于对比策略净值、基准走势与回撤变化；请结合 AI 诊断中的收益能力、风险控制和稳定性结论继续验证。</p></section>
          <section className="trades-panel">
            <header><h2>回测成交记录</h2><span>历史模拟成交 · 非真实订单</span></header>
            <div className="table-scroll"><table><thead><tr><th>日期</th><th>标的</th><th>方向</th><th>成交价</th><th>数量</th><th>手续费</th></tr></thead><tbody>
              {result.trades.length ? result.trades.slice(0, 8).map((trade, index) => <tr key={`${trade.date}-${index}`}><td>{trade.date}</td><td>{trade.name}<small>{trade.symbol}</small></td><td className={trade.side === "买入" ? "buy" : "sell"}>{trade.side}</td><td>¥ {trade.price.toFixed(2)}</td><td>{trade.quantity.toLocaleString()}</td><td>¥ {trade.fee.toFixed(2)}</td></tr>) : <tr><td colSpan={6} className="empty-table">当前区间没有产生交易</td></tr>}
            </tbody></table></div>
          </section>
        </div>
        <aside className="result-summary">
          <h2>策略摘要</h2>
          <dl><div><dt>策略名称</dt><dd>{spec.name}</dd></div><div><dt>回测区间</dt><dd>{spec.backtest.start_date}<br />— {spec.backtest.end_date}</dd></div><div><dt>初始资金</dt><dd>¥ {spec.backtest.initial_capital.toLocaleString()}</dd></div><div><dt>止损比例</dt><dd>{spec.exit.risk_controls.stop_loss_pct}%</dd></div><div><dt>调仓频率</dt><dd>{spec.backtest.rebalance}</dd></div>{result.data_snapshot ? <><div><dt>行情快照</dt><dd>{result.data_snapshot.snapshot_hash}</dd></div><div><dt>数据文件</dt><dd>{result.data_snapshot.storage_path}</dd></div></> : null}<div><dt>策略指纹</dt><dd>{result.strategy_hash}</dd></div></dl>
          <button className="code-row" aria-expanded={codeOpen} onClick={() => setCodeOpen(true)}><Code2 size={15} />查看策略代码</button>
        </aside>
      </div>
      <CodeDialog code={visibleCode} open={codeOpen} onClose={() => setCodeOpen(false)} />
    </main>
  );
}
