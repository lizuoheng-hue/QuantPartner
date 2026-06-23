"use client";

import { ArrowRight, Bot, Database, Download, Github, Globe2, Landmark, LineChart, LogIn, ShieldCheck, Smartphone, Sparkles, WalletCards } from "lucide-react";
import { FormEvent, useState } from "react";
import { BrandMark } from "@/components/brand-mark";
import { loginAccount, registerAccount } from "@/lib/api";
import type { AuthSession } from "@/lib/types";

export function AuthGate({ onAuthenticated }: { onAuthenticated: (session: AuthSession) => void }) {
  const [mode, setMode] = useState<"register" | "login">("register");
  const [authOpen, setAuthOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const markets = [
    { icon: <Landmark size={22} />, title: "A股 / 沪深300", detail: "Tushare Pro · 000300.SH · 日线回测" },
    { icon: <Globe2 size={22} />, title: "港股", detail: "Twelve Data · 恒生指数 HSI · 演示/授权数据" },
    { icon: <LineChart size={22} />, title: "美股", detail: "Twelve Data · SPY / S&P 500 · 日线策略" },
    { icon: <Database size={22} />, title: "可追溯数据快照", detail: "CSV 缓存 · hash 校验 · 回测绑定快照" },
    { icon: <WalletCards size={22} />, title: "模拟盘交易", detail: "Paper Broker · 下单 / 撤单 / 审计事件" },
    { icon: <Bot size={22} />, title: "Agent Gateway", detail: "Codex / Cursor / Claude · 研究与模拟盘接口" },
    { icon: <ShieldCheck size={22} />, title: "实盘网关预留", detail: "Live Broker 默认关闭 · 合规验收后白名单" },
    { icon: <Sparkles size={22} />, title: "策略模板市场", detail: "趋势 / 价值质量 / 网格模拟 / DCA / 行业轮动" },
  ];

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    try {
      const session = mode === "register"
        ? await registerAccount({
            email: String(data.get("email")), password: String(data.get("password")),
            display_name: String(data.get("display_name")), workspace_name: String(data.get("workspace_name")),
          })
        : await loginAccount(String(data.get("email")), String(data.get("password")));
      onAuthenticated(session);
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "请求失败";
      setError(message.includes("已注册") ? "该邮箱已注册，请直接登录。" : message.includes("邮箱或密码") ? "邮箱或密码错误。" : "暂时无法完成，请稍后重试。");
    } finally {
      setBusy(false);
    }
  }

  function openAuth(nextMode: "register" | "login" = "register") {
    setMode(nextMode);
    setError("");
    setAuthOpen(true);
  }

  return (
    <main className="auth-shell">
      <header className="landing-nav">
        <a className="landing-brand" href="#" aria-label="QuantPartner 首页"><BrandMark /><strong>QuantPartner</strong></a>
        <nav aria-label="首页导航">
          <a href="#features">功能</a>
          <a href="#agent">AI Agent</a>
          <a href="#market">市场</a>
          <a href="#docs">文档</a>
          <a href="#faq">常见问题</a>
        </nav>
        <div className="landing-actions">
          <button type="button" className="locale-button"><Globe2 size={15} />中</button>
          <button type="button" className="app-button" onClick={() => openAuth("register")}><Smartphone size={15} />Get App<span>NEW</span></button>
          <button type="button" className="login-chip" onClick={() => openAuth("login")}><LogIn size={16} />登录</button>
        </div>
      </header>

      <section className="landing-hero">
        <div className="release-pill"><b>MCP · V0.1</b><span />面向 AI AGENT</div>
        <h1>
          <span>把交易想法，变成</span>
          <span><em>可验证</em>的策略。</span>
        </h1>
        <p className="auth-lead">自然语言策略生成、澄清地图、结构化条件、真实数据回测、模拟盘验证与审计追踪，一个平台全部打通。</p>
        <div className="hero-actions">
          <button type="button" className="hero-primary" onClick={() => openAuth("register")}>打开应用<ArrowRight size={21} /></button>
          <a className="hero-secondary" href="https://github.com/brokermr810/QuantDinger" target="_blank" rel="noreferrer"><Github size={18} />参考项目</a>
        </div>
        <div className="mobile-banner">
          <div><Smartphone size={22} /><span><strong>Now on mobile</strong><small>使用移动端 Web 查看回测、实验和模拟盘。</small></span></div>
          <div><button type="button" onClick={() => openAuth("register")}>Open Mobile Web</button><button type="button"><Download size={16} />Download APK</button></div>
        </div>
      </section>

      <section className="market-coverage" id="market">
        <div className="market-heading">
          <p>市场覆盖</p>
          <h2>值得验证的市场，一个都不少。</h2>
          <span>当前系统聚焦 A股、港股、美股三市场的策略研究与日线回测；模拟盘已启用，实盘交易保持关闭。</span>
        </div>
        <div className="market-grid">
          {markets.map(item => (
            <article key={item.title}>
              <div>{item.icon}</div>
              <span><strong>{item.title}</strong><small>{item.detail}</small></span>
            </article>
          ))}
        </div>
      </section>
      <section className="landing-feature-strip" id="features">
        {["策略澄清地图", "结构化条件", "可复现回测", "模拟盘订单", "Agent Gateway"].map(item => <span key={item}><Sparkles size={13} />{item}</span>)}
      </section>
      {authOpen ? (
        <div className="auth-modal-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setAuthOpen(false); }}>
          <section className="auth-panel auth-modal" id="auth-panel" role="dialog" aria-modal="true" aria-labelledby="auth-modal-title">
            <div className="auth-tabs">
              <button type="button" className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>创建账号</button>
              <button type="button" className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>登录</button>
            </div>
            <form onSubmit={submit}>
              <header><h2 id="auth-modal-title">{mode === "register" ? "创建你的策略工作区" : "欢迎回来"}</h2><p>{mode === "register" ? "公测期间所有交易功能默认为模拟盘。" : "继续管理策略、回测与模拟订单。"}</p></header>
              {mode === "register" ? <label>姓名<input name="display_name" required minLength={2} placeholder="怎么称呼你" /></label> : null}
              {mode === "register" ? <label>工作区名称<input name="workspace_name" required minLength={2} placeholder="例如：我的量化实验室" /></label> : null}
              <label>邮箱<input name="email" type="email" required autoComplete="email" placeholder="name@example.com" /></label>
              <label>密码<input name="password" type="password" required minLength={10} autoComplete={mode === "login" ? "current-password" : "new-password"} placeholder="至少 10 位" /></label>
              {error ? <p className="auth-error" role="alert">{error}</p> : null}
              <button className="primary-button auth-submit" disabled={busy}>{busy ? <span className="spinner" /> : null}{mode === "register" ? "进入 QuantPartner" : "登录"}<ArrowRight size={15} /></button>
            </form>
            <footer>继续即表示你理解：历史回测与模拟交易不构成投资建议。</footer>
          </section>
        </div>
      ) : null}
    </main>
  );
}
