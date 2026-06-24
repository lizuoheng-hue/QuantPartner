"use client";

import { ArrowRight, BarChart3, GitBranch, History, PlayCircle, ShieldCheck, X } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { getStrategy, listStrategies } from "@/lib/api";
import type { StrategyDetail, StrategySpec, StrategySummary, VersionDetail } from "@/lib/types";

function pct(value?: number | null) {
  return value === null || value === undefined ? "待回测" : `${(value * 100).toFixed(1)}%`;
}

function marketLabel(market: StrategySummary["market"]) {
  return market === "US" ? "美股" : market === "HK" ? "港股" : "A股";
}

function dateTime(value?: string | null) {
  return value ? new Date(value).toLocaleString("zh-CN", { hour12: false }) : "暂无";
}

function compactDateTime(value?: string | null) {
  if (!value) return "暂无";
  const date = new Date(value);
  return date.toLocaleString("zh-CN", { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false });
}

function enabledSummary(spec: StrategySpec) {
  const entry = spec.entry.conditions.filter(item => item.enabled).map(item => `${item.field} ${item.operator} ${item.value}`).join(" / ") || "未启用买入条件";
  const exit = spec.exit.conditions.filter(item => item.enabled).map(item => `${item.field} ${item.operator} ${item.value}`).join(" / ") || "未启用卖出条件";
  return { entry, exit };
}

interface StrategyHistoryPanelProps {
  activeStrategyId: string | null;
  onClose: () => void;
  onLoadVersion: (strategy: StrategyDetail, version: VersionDetail) => void;
}

export function StrategyHistoryPanel({ activeStrategyId, onClose, onLoadVersion }: StrategyHistoryPanelProps) {
  const [strategies, setStrategies] = useState<StrategySummary[]>([]);
  const [detail, setDetail] = useState<StrategyDetail | null>(null);
  const [selectedVersionId, setSelectedVersionId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    listStrategies()
      .then(async items => {
        if (cancelled) return;
        setStrategies(items);
        const selected = items.find(item => item.id === activeStrategyId) ?? items[0];
        if (selected) {
          const nextDetail = await getStrategy(selected.id);
          if (cancelled) return;
          setDetail(nextDetail);
          setSelectedVersionId(nextDetail.latest_version_id || nextDetail.versions[0]?.id || null);
        }
      })
      .catch(() => {
        if (!cancelled) setError("暂时无法读取历史策略，请稍后重试。");
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => { cancelled = true; };
  }, [activeStrategyId]);

  const selectedVersion = useMemo(() => {
    if (!detail) return null;
    return detail.versions.find(item => item.id === selectedVersionId) ?? detail.versions[0] ?? null;
  }, [detail, selectedVersionId]);

  const selectedSummary = selectedVersion ? enabledSummary(selectedVersion.spec) : null;

  const selectStrategy = async (strategy: StrategySummary) => {
    setLoading(true);
    setError("");
    try {
      const nextDetail = await getStrategy(strategy.id);
      setDetail(nextDetail);
      setSelectedVersionId(nextDetail.latest_version_id || nextDetail.versions[0]?.id || null);
    } catch {
      setError("暂时无法打开该策略。");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="history-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="history-panel" role="dialog" aria-modal="true" aria-labelledby="history-title">
        <header className="history-header">
          <div><History size={19} /><span><strong id="history-title">我的策略</strong><small>历史策略、版本历史与回测诊断</small></span></div>
          <button type="button" className="icon-button" aria-label="关闭历史策略" onClick={onClose}><X size={18} /></button>
        </header>

        {loading && !detail ? <div className="history-loading"><span className="spinner" />正在读取策略资产</div> : null}
        {error ? <p className="history-error" role="alert">{error}</p> : null}
        {!loading && !strategies.length ? (
          <div className="history-empty">
            <GitBranch size={24} />
            <strong>还没有保存过策略</strong>
            <span>完成一次回测或点击保存版本后，这里会出现你的历史策略和版本记录。</span>
          </div>
        ) : null}

        {strategies.length ? (
          <div className="history-layout">
            <aside className="history-strategies">
              <div className="history-column-title">策略列表</div>
              {strategies.map(strategy => (
                <button type="button" key={strategy.id} className={detail?.id === strategy.id ? "active" : ""} onClick={() => selectStrategy(strategy)}>
                  <span><strong>{strategy.name}</strong><small>{marketLabel(strategy.market)} · {strategy.version_count} 个版本 · {strategy.backtest_count} 次回测</small></span>
                  <em className={strategy.status}>{strategy.status === "backtested" ? "已回测" : "草稿"}</em>
                </button>
              ))}
            </aside>

            <aside className="history-versions">
              <div className="history-column-title">版本历史</div>
              {detail?.versions.map((version, index) => (
                <button type="button" key={version.id} className={selectedVersion?.id === version.id ? "active" : ""} onClick={() => setSelectedVersionId(version.id)}>
                  <span className="version-copy">
                    <span className="version-title">
                      <b>#{detail.versions.length - index}</b>
                      <strong>{version.label}</strong>
                      <em className={version.backtest ? "" : "draft"}>{version.backtest ? "已回测" : "草稿"}</em>
                    </span>
                    <span className="version-time">{compactDateTime(version.created_at)}</span>
                    <span className="version-note">{version.note ?? "版本快照"}</span>
                    {version.backtest ? <span className="version-metrics">收益 {pct(version.backtest.metrics.annual_return)} · 回撤 {pct(version.backtest.metrics.max_drawdown)}</span> : <span className="version-metrics">未绑定回测结果</span>}
                  </span>
                </button>
              ))}
            </aside>

            <main className="history-detail">
              {detail && selectedVersion ? (
                <>
                  <section className="history-detail-hero">
                    <div>
                      <span>{marketLabel(detail.market)} · {detail.benchmark}</span>
                      <h2>{detail.name}</h2>
                      <p>{selectedVersion.label} · {selectedVersion.note ?? "策略版本快照"} · {dateTime(selectedVersion.created_at)}</p>
                    </div>
                    <button type="button" className="primary-button" onClick={() => onLoadVersion(detail, selectedVersion)}>
                      基于此版本继续迭代 <ArrowRight size={15} />
                    </button>
                  </section>

                  <section className="history-metrics">
                    <article><span>年化收益</span><strong className={selectedVersion.backtest?.metrics.annual_return && selectedVersion.backtest.metrics.annual_return > 0 ? "positive" : ""}>{pct(selectedVersion.backtest?.metrics.annual_return)}</strong></article>
                    <article><span>最大回撤</span><strong className="negative">{pct(selectedVersion.backtest?.metrics.max_drawdown)}</strong></article>
                    <article><span>胜率</span><strong>{pct(selectedVersion.backtest?.metrics.win_rate)}</strong></article>
                    <article><span>成交记录</span><strong>{selectedVersion.backtest?.trades.length ?? 0}</strong></article>
                  </section>

                  <section className="history-version-grid">
                    <article>
                      <h3><ShieldCheck size={15} />策略条件快照</h3>
                      <dl>
                        <div><dt>买入</dt><dd>{selectedSummary?.entry}</dd></div>
                        <div><dt>卖出</dt><dd>{selectedSummary?.exit}</dd></div>
                        <div><dt>止损</dt><dd>{selectedVersion.spec.exit.risk_controls.stop_loss_pct ?? 0}%</dd></div>
                        <div><dt>回测区间</dt><dd>{selectedVersion.spec.backtest.start_date} 至 {selectedVersion.spec.backtest.end_date}</dd></div>
                      </dl>
                    </article>
                    <article>
                      <h3><BarChart3 size={15} />AI 诊断摘要</h3>
                      {selectedVersion.backtest?.diagnosis ? (
                        <div className="history-diagnosis">
                          <p>{selectedVersion.backtest.diagnosis.summary}</p>
                          {selectedVersion.backtest.diagnosis.suggestions.slice(0, 2).map(item => (
                            <span key={item.title}><strong>{item.title}</strong><small>{item.rationale}</small></span>
                          ))}
                        </div>
                      ) : <p className="history-muted">这个版本还没有绑定完成的回测结果。</p>}
                    </article>
                  </section>

                  <section className="history-trades">
                    <header><h3><PlayCircle size={15} />版本成交记录</h3><span>历史模拟成交 · 非真实订单</span></header>
                    <div>
                      {selectedVersion.backtest?.trades.length ? selectedVersion.backtest.trades.slice(0, 5).map((trade, index) => (
                        <p key={`${trade.date}-${index}`}><span>{trade.date}</span><strong>{trade.side}</strong><em>{trade.name}</em><code>¥ {trade.price.toFixed(2)}</code></p>
                      )) : <p className="history-muted">暂无成交记录。</p>}
                    </div>
                  </section>
                </>
              ) : null}
            </main>
          </div>
        ) : null}
      </section>
    </div>
  );
}
