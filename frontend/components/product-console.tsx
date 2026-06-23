import { Bot, CheckCircle2, Database, FlaskConical, KeyRound, Layers3, Lock, RadioTower, ShieldAlert, Sparkles, WalletCards, X } from "lucide-react";
import { useEffect, useState } from "react";
import { getProductDashboard, getProductRoadmap, listAgentCapabilities, listExperimentSnapshots, listIntegrations, listMarketplaceTemplates } from "@/lib/api";
import type { AgentCapability, ExperimentSnapshot, IntegrationStatus, MarketplaceTemplate, ProductDashboard, ProductRoadmap } from "@/lib/types";

interface ProductConsoleProps {
  onClose: () => void;
  onUsePrompt: (prompt: string) => void;
  onOpenPaperTrading: () => void;
}

function statusLabel(status: string): string {
  return {
    connected: "已连接",
    not_configured: "待配置",
    paper_only: "仅模拟盘",
    planned: "规划中",
    blocked: "已关闭",
    ready: "可用",
    preview: "预览",
    enabled: "已启用",
    partial: "部分完成",
    ui_only: "仅UI结构",
    implemented: "已完成",
  }[status] ?? status;
}

function shortHash(value?: string | null): string {
  return value ? value.slice(0, 10) : "—";
}

export function ProductConsole({ onClose, onUsePrompt, onOpenPaperTrading }: ProductConsoleProps) {
  const [dashboard, setDashboard] = useState<ProductDashboard | null>(null);
  const [experiments, setExperiments] = useState<ExperimentSnapshot[]>([]);
  const [marketplace, setMarketplace] = useState<MarketplaceTemplate[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationStatus[]>([]);
  const [agents, setAgents] = useState<AgentCapability[]>([]);
  const [roadmap, setRoadmap] = useState<ProductRoadmap[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getProductDashboard(),
      listExperimentSnapshots(),
      listMarketplaceTemplates(),
      listIntegrations(),
      listAgentCapabilities(),
      getProductRoadmap(),
    ]).then(([nextDashboard, nextExperiments, nextMarketplace, nextIntegrations, nextAgents, nextRoadmap]) => {
      if (cancelled) return;
      setDashboard(nextDashboard);
      setExperiments(nextExperiments);
      setMarketplace(nextMarketplace);
      setIntegrations(nextIntegrations);
      setAgents(nextAgents);
      setRoadmap(nextRoadmap);
    }).finally(() => {
      if (!cancelled) setLoading(false);
    });
    return () => { cancelled = true; };
  }, []);

  return (
    <div className="product-console-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) onClose(); }}>
      <section className="product-console" role="dialog" aria-modal="true" aria-labelledby="product-console-title">
        <header className="product-console-header">
          <div>
            <Sparkles size={18} />
            <span>
              <strong id="product-console-title">产品化控制台</strong>
              <small>复刻 QuantDinger 的能力结构，但保留 QuantPartner 的安全边界</small>
            </span>
          </div>
          <button type="button" className="icon-button" aria-label="关闭产品化控制台" onClick={onClose}><X size={17} /></button>
        </header>

        {loading ? <div className="product-console-loading"><span className="spinner" /> 正在同步产品化能力…</div> : (
          <div className="product-console-content">
            <section className="console-hero">
              <div>
                <p className="eyebrow">CONTROL TOWER</p>
                <h2>从路演 MVP 进入开放公测控制塔</h2>
                <p>这里集中展示实验快照、模板市场、数据源/Broker、Agent 权限、通知与高风险功能的 UI 结构。</p>
              </div>
              <button type="button" className="primary-button" onClick={onOpenPaperTrading}><WalletCards size={15} />打开模拟盘</button>
            </section>

            <section className="console-metrics">
              {dashboard?.metrics.map(metric => (
                <article className={`console-metric ${metric.tone}`} key={metric.label}>
                  <span>{metric.label}</span>
                  <strong>{metric.value}</strong>
                  <small>{metric.hint}</small>
                </article>
              ))}
            </section>

            <section className="console-grid">
              <article className="console-card wide">
                <header><FlaskConical size={16} /><h3>实验快照</h3><em>P1</em></header>
                <div className="experiment-list">
                  {experiments.length ? experiments.slice(0, 6).map(item => (
                    <div key={item.id}>
                      <span><strong>{item.status}</strong><small>{item.stage}</small></span>
                      <code>策略 {shortHash(item.strategy_hash)} · 数据 {shortHash(item.data_snapshot_hash)}</code>
                    </div>
                  )) : <p className="console-empty">完成一次回测后会生成可复现实验快照。</p>}
                </div>
              </article>

              <article className="console-card">
                <header><Database size={16} /><h3>系统状态</h3><em>P2</em></header>
                <div className="system-card-list">
                  {dashboard?.system_cards.map(card => (
                    <div key={card.title}><span>{card.title}</span><strong>{card.value}</strong><small>{statusLabel(card.status)}</small></div>
                  ))}
                </div>
              </article>
            </section>

            <section className="console-card">
              <header><Layers3 size={16} /><h3>策略模板市场</h3><em>P1</em></header>
              <div className="marketplace-grid">
                {marketplace.map(template => (
                  <article className={`marketplace-card ${template.status}`} key={template.id}>
                    <div><strong>{template.name}</strong><span>{template.category} · {statusLabel(template.status)}</span></div>
                    <p>{template.description}</p>
                    <small>{template.markets.join(" / ")} · 风险 {template.risk_level}</small>
                    <button type="button" onClick={() => onUsePrompt(template.prompt)} disabled={template.status === "planned"}>
                      {template.status === "planned" ? "规划中" : "套用到对话"}
                    </button>
                  </article>
                ))}
              </div>
            </section>

            <section className="console-grid">
              <article className="console-card">
                <header><RadioTower size={16} /><h3>数据源 / Broker / 通知</h3><em>P2</em></header>
                <div className="integration-list">
                  {integrations.map(item => (
                    <div className={item.status} key={item.id}>
                      <span>{item.category === "broker" ? <WalletCards size={14} /> : item.category === "data" ? <Database size={14} /> : item.category === "notification" ? <RadioTower size={14} /> : <Bot size={14} />}</span>
                      <div><strong>{item.name}</strong><small>{item.description}</small></div>
                      <em>{statusLabel(item.status)}</em>
                    </div>
                  ))}
                </div>
              </article>

              <article className="console-card">
                <header><KeyRound size={16} /><h3>Agent / MCP 权限</h3><em>P2</em></header>
                <div className="agent-list">
                  {agents.map(agent => (
                    <div className={agent.status} key={agent.id}>
                      {agent.status === "blocked" ? <Lock size={15} /> : <CheckCircle2 size={15} />}
                      <span><strong>{agent.name}</strong><small>{agent.scope}</small></span>
                    </div>
                  ))}
                </div>
              </article>
            </section>

            <section className="console-card">
              <header><ShieldAlert size={16} /><h3>第三优先级：只复刻前端功能结构</h3><em>UI-only</em></header>
              <div className="roadmap-grid">
                {roadmap.map(group => (
                  <article key={group.tier} className={group.status}>
                    <strong>{group.title}</strong>
                    <span>{statusLabel(group.status)}</span>
                    <ul>{group.items.map(item => <li key={item}>{item}</li>)}</ul>
                  </article>
                ))}
              </div>
            </section>
          </div>
        )}
      </section>
    </div>
  );
}
