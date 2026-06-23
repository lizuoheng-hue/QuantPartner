import { ArrowLeft, CheckCircle2, Code2, Save } from "lucide-react";
import { useState } from "react";
import type { BacktestResult, StrategySpec } from "@/lib/types";
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

interface ResultsViewProps {
  result: BacktestResult;
  spec: StrategySpec;
  onEdit: () => void;
  onSave: () => void;
  saving: boolean;
}

export function ResultsView({ result, spec, onEdit, onSave, saving }: ResultsViewProps) {
  const [codeOpen, setCodeOpen] = useState(false);
  const visibleCode = result.code_preview || JSON.stringify(spec, null, 2);

  return (
    <main className="results-view">
      <header className="results-header">
        <div><h1>{spec.name} · 回测结果</h1><span className="complete-state"><CheckCircle2 size={14} /> 已完成</span></div>
        <div className="results-actions"><button className="secondary-button" onClick={onEdit}><ArrowLeft size={15} />修改策略</button><button className="primary-button" onClick={onSave} disabled={saving}><Save size={15} />{saving ? "保存中" : "保存版本"}</button></div>
      </header>
      <section className="diagnosis"><p>{result.summary}</p><small>{result.disclaimer}</small></section>
      <section className="metrics-rail">
        {Object.entries(result.metrics).map(([key, value]) => <div key={key}><span>{metricLabels[key]}</span><strong className={key === "max_drawdown" ? "negative" : key === "annual_return" || key === "alpha" ? "positive" : ""}>{metricValue(key, value)}</strong></div>)}
      </section>
      <div className="result-grid">
        <div className="result-main">
          <section className="chart-panel"><header><h2>累计净值</h2><span>{dataSourceLabel(result)}</span></header><EquityChart strategy={result.equity_curve} benchmark={result.benchmark_curve} drawdown={result.drawdown_curve} /></section>
          <section className="trades-panel">
            <header><h2>最近交易</h2><span>按成交时间倒序</span></header>
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
