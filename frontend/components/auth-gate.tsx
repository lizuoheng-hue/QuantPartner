"use client";

import { ArrowRight, ShieldCheck } from "lucide-react";
import { FormEvent, useState } from "react";
import { BrandMark } from "@/components/brand-mark";
import { loginAccount, registerAccount } from "@/lib/api";
import type { AuthSession } from "@/lib/types";

export function AuthGate({ onAuthenticated }: { onAuthenticated: (session: AuthSession) => void }) {
  const [mode, setMode] = useState<"register" | "login">("register");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

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

  return (
    <main className="auth-shell">
      <section className="auth-intro">
        <div className="brand auth-brand"><BrandMark /><span>QuantPartner</span><small>量化伴侣</small></div>
        <p className="eyebrow">OPEN BETA</p>
        <h1>
          <span>把交易想法，变成</span>
          <span>可验证的策略。</span>
        </h1>
        <p className="auth-lead">覆盖沪深300、港股与美股。策略、回测和模拟订单均隔离在你的工作区内。</p>
        <div className="auth-trust"><ShieldCheck size={16} /> LLM 不直接执行代码或提交订单</div>
      </section>
      <section className="auth-panel">
        <div className="auth-tabs">
          <button className={mode === "register" ? "active" : ""} onClick={() => setMode("register")}>创建账号</button>
          <button className={mode === "login" ? "active" : ""} onClick={() => setMode("login")}>登录</button>
        </div>
        <form onSubmit={submit}>
          <header><h2>{mode === "register" ? "创建你的策略工作区" : "欢迎回来"}</h2><p>{mode === "register" ? "公测期间所有交易功能默认为模拟盘。" : "继续管理策略、回测与模拟订单。"}</p></header>
          {mode === "register" ? <label>姓名<input name="display_name" required minLength={2} placeholder="怎么称呼你" /></label> : null}
          {mode === "register" ? <label>工作区名称<input name="workspace_name" required minLength={2} placeholder="例如：我的量化实验室" /></label> : null}
          <label>邮箱<input name="email" type="email" required autoComplete="email" placeholder="name@example.com" /></label>
          <label>密码<input name="password" type="password" required minLength={10} autoComplete={mode === "login" ? "current-password" : "new-password"} placeholder="至少 10 位" /></label>
          {error ? <p className="auth-error" role="alert">{error}</p> : null}
          <button className="primary-button auth-submit" disabled={busy}>{busy ? <span className="spinner" /> : null}{mode === "register" ? "进入 QuantPartner" : "登录"}<ArrowRight size={15} /></button>
        </form>
        <footer>继续即表示你理解：历史回测与模拟交易不构成投资建议。</footer>
      </section>
    </main>
  );
}
