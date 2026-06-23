import { Activity, BellRing, Bot, BrainCircuit, CheckCircle2, Database, FlaskConical, Gauge, KeyRound, Layers3, Lock, RadioTower, Settings, ShieldAlert, Sparkles, TerminalSquare, WalletCards, X } from "lucide-react";
import { useEffect, useState } from "react";
import type { ReactNode } from "react";
import { getAgentManifest, getProductDashboard, getProductRoadmap, listAgentCapabilities, listExperimentSnapshots, listIntegrations, listMarketplaceTemplates, listNotificationChannels } from "@/lib/api";
import type { AgentCapability, AgentManifest, ExperimentSnapshot, IntegrationStatus, MarketplaceTemplate, NotificationChannel, ProductDashboard, ProductRoadmap } from "@/lib/types";

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

function formatPct(value?: number | null): string {
  return typeof value === "number" ? `${(value * 100).toFixed(1)}%` : "待生成";
}

type ConsoleSection = "dashboard" | "bots" | "ai" | "backtest" | "portfolio" | "settings";

export function ProductConsole({ onClose, onUsePrompt, onOpenPaperTrading }: ProductConsoleProps) {
  const [activeSection, setActiveSection] = useState<ConsoleSection>("dashboard");
  const [dashboard, setDashboard] = useState<ProductDashboard | null>(null);
  const [experiments, setExperiments] = useState<ExperimentSnapshot[]>([]);
  const [marketplace, setMarketplace] = useState<MarketplaceTemplate[]>([]);
  const [integrations, setIntegrations] = useState<IntegrationStatus[]>([]);
  const [agents, setAgents] = useState<AgentCapability[]>([]);
  const [notifications, setNotifications] = useState<NotificationChannel[]>([]);
  const [manifest, setManifest] = useState<AgentManifest | null>(null);
  const [roadmap, setRoadmap] = useState<ProductRoadmap[]>([]);
  const [loading, setLoading] = useState(true);

  const consoleNav: Array<{ id: ConsoleSection; label: string; detail: string; icon: ReactNode }> = [
    { id: "dashboard", label: "Dashboard", detail: "总览", icon: <Gauge size={15} /> },
    { id: "bots", label: "Trading Bots", detail: "模板孵化", icon: <Bot size={15} /> },
    { id: "ai", label: "AI Analysis", detail: "Agent/MCP", icon: <BrainCircuit size={15} /> },
    { id: "backtest", label: "Backtest", detail: "实验快照", icon: <FlaskConical size={15} /> },
    { id: "portfolio", label: "Portfolio", detail: "模拟盘", icon: <WalletCards size={15} /> },
    { id: "settings", label: "Settings", detail: "集成与通知", icon: <Settings size={15} /> },
  ];

  const focusCopy: Record<ConsoleSection, { title: string; body: string; stat: string }> = {
    dashboard: { title: "私有量化操作台", body: "把 QuantDinger 的一体化工作台结构转译为 QuantPartner 的公测控制塔：研究、回测、模拟盘、Agent 和审计在同一屏完成闭环。", stat: "paper-only" },
    bots: { title: "策略模板孵化", body: "模板市场先服务研究和模拟盘验证，趋势、价值、网格、DCA 都会落到受控 StrategySpec，不开放无人值守实盘。", stat: `${marketplace.length} templates` },
    ai: { title: "Agent/MCP 安全网关", body: "Codex、Claude Code、Cursor 可以读取工作区、提交回测和创建模拟盘订单；实盘交易 scope 保持关闭并写审计。", stat: `${manifest?.tools.length ?? 0} tools` },
    backtest: { title: "可复现实验中心", body: "每次回测绑定策略 hash、数据快照、费用模型和核心指标，用实验快照替代口头判断。", stat: `${experiments.length} runs` },
    portfolio: { title: "模拟盘运行面板", body: "从策略信号到模拟订单的运营视图，适合做路演后的公测验证和小规模用户训练。", stat: "live off" },
    settings: { title: "集成与告警矩阵", body: "数据源、Broker、通知、Agent 能力集中展示；缺失凭据、队列降级和高风险通道都显式暴露。", stat: `${integrations.length} integrations` },
  };

  const botRows = marketplace.slice(0, 4);
  const activeFocus = focusCopy[activeSection];

  useEffect(() => {
    let cancelled = false;
    Promise.all([
      getProductDashboard(),
      listExperimentSnapshots(),
      listMarketplaceTemplates(),
      listIntegrations(),
      listAgentCapabilities(),
      listNotificationChannels(),
      getAgentManifest(),
      getProductRoadmap(),
    ]).then(([nextDashboard, nextExperiments, nextMarketplace, nextIntegrations, nextAgents, nextNotifications, nextManifest, nextRoadmap]) => {
      if (cancelled) return;
      setDashboard(nextDashboard);
      setExperiments(nextExperiments);
      setMarketplace(nextMarketplace);
      setIntegrations(nextIntegrations);
      setAgents(nextAgents);
      setNotifications(nextNotifications);
      setManifest(nextManifest);
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
            <section className="console-operating-deck">
              <nav className="console-os-nav" aria-label="产品化模块">
                <div className="console-os-brand">
                  <Sparkles size={17} />
                  <span><strong>QP OS</strong><small>Public Beta</small></span>
                </div>
                {consoleNav.map(item => (
                  <button type="button" className={activeSection === item.id ? "active" : ""} key={item.id} onClick={() => setActiveSection(item.id)}>
                    {item.icon}
                    <span><strong>{item.label}</strong><small>{item.detail}</small></span>
                  </button>
                ))}
              </nav>

              <div className="console-os-stage">
                <div className="console-os-hero">
                  <div>
                    <p className="eyebrow">SELF-HOSTED QUANT STACK</p>
                    <h2>{activeFocus.title}</h2>
                    <p>{activeFocus.body}</p>
                  </div>
                  <aside>
                    <span>{activeFocus.stat}</span>
                    <strong>{manifest?.live_trading_enabled ? "LIVE ENABLED" : "LIVE LOCKED"}</strong>
                    <small>Agent 默认只允许研究、回测和模拟盘。</small>
                  </aside>
                </div>

                <div className="console-os-kpis">
                  {(dashboard?.metrics ?? []).map(metric => (
                    <article className={metric.tone} key={metric.label}>
                      <span>{metric.label}</span>
                      <strong>{metric.value}</strong>
                      <small>{metric.hint}</small>
                    </article>
                  ))}
                </div>

                <div className="console-os-table">
                  <header>
                    <span><Activity size={14} /> Strategy Market Mode Status</span>
                    <button type="button" onClick={onOpenPaperTrading}><WalletCards size={14} />模拟盘</button>
                  </header>
                  <div>
                    {botRows.map((template, index) => (
                      <button type="button" key={template.id} onClick={() => onUsePrompt(template.prompt)} disabled={template.status === "planned"}>
                        <span><strong>{template.name}</strong><small>{template.category}</small></span>
                        <code>{template.markets.join("/")}</code>
                        <em>{index % 2 === 0 ? "Signal" : "Paper"}</em>
                        <b className={template.status}>{statusLabel(template.status)}</b>
                      </button>
                    ))}
                  </div>
                </div>
              </div>
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
                      <span><strong>{item.market} · {item.status}</strong><small>{item.stage} · {item.benchmark}</small></span>
                      <code>收益 {formatPct(item.annual_return)} · 回撤 {formatPct(item.max_drawdown)} · Sharpe {item.sharpe?.toFixed(2) ?? "待生成"}</code>
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

            <section className="console-grid">
              <article className="console-card wide">
                <header><TerminalSquare size={16} /><h3>Agent Gateway</h3><em>paper-only</em></header>
                <div className="agent-gateway-summary">
                  <div><span>Base URL</span><strong>{manifest?.gateway ?? "/api/agent/v1"}</strong></div>
                  <div><span>执行模式</span><strong>{manifest?.mode === "paper_only" ? "研究 + 回测 + 模拟盘" : "未配置"}</strong></div>
                  <div><span>实盘权限</span><strong>{manifest?.live_trading_enabled ? "已启用" : "关闭"}</strong></div>
                  <div><span>审计</span><strong>{manifest?.audit_required ? "强制记录" : "未开启"}</strong></div>
                </div>
                <div className="agent-tool-list">
                  {manifest?.tools.map(tool => (
                    <div className={tool.status} key={tool.name}>
                      <code>{tool.method}</code>
                      <span><strong>{tool.name}</strong><small>{tool.path}</small></span>
                      <em>{statusLabel(tool.status)}</em>
                    </div>
                  ))}
                </div>
              </article>

              <article className="console-card">
                <header><BellRing size={16} /><h3>通知 / 告警</h3><em>P2</em></header>
                <div className="notification-list">
                  {notifications.map(channel => (
                    <div className={channel.status} key={channel.id}>
                      <span><strong>{channel.name}</strong><small>{channel.trigger}</small></span>
                      <p>{channel.description}</p>
                      <em>{statusLabel(channel.status)}</em>
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
