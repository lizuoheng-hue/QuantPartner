"use client";

import { FolderClock, LogOut, Settings, ShieldCheck, X } from "lucide-react";
import type { FormEvent } from "react";
import { useCallback, useEffect, useState } from "react";
import { BacktestProgress } from "@/components/backtest-progress";
import { AuthGate } from "@/components/auth-gate";
import { BrandMark } from "@/components/brand-mark";
import { ChatWorkspace } from "@/components/chat-workspace";
import { ResultsView } from "@/components/results-view";
import { PaperTrading } from "@/components/paper-trading";
import { ProductConsole } from "@/components/product-console";
import { StrategyHistoryPanel } from "@/components/strategy-history-panel";
import { StrategyInspector } from "@/components/strategy-inspector";
import { StrategySidebar } from "@/components/strategy-sidebar";
import { cancelBacktest, changePassword, createStrategy, getAccessToken, getBacktest, getMe, getTemplates, listVersions, parseStrategy, saveVersion, submitBacktest } from "@/lib/api";
import type { AuthSession, BacktestResult, BacktestTask, ParseResult, StrategyDetail, StrategySpec, Template, VersionDetail, VersionItem } from "@/lib/types";

const DEFAULT_INPUT = "沪深300里，EMA20上穿EMA60买入，跌破EMA20卖出，8%止损";
const WORKSPACE_KEY_PREFIX = "quantpartner:workspace:v2";

function workspaceKey(workspaceId: string): string {
  return `${WORKSPACE_KEY_PREFIX}:${workspaceId}`;
}

interface PersistedWorkspace {
  input?: string;
  spec?: StrategySpec;
  selectedId?: string;
  strategyId?: string;
  taskId?: string;
}

function readWorkspace(workspaceId: string): PersistedWorkspace | null {
  try {
    const raw = window.localStorage.getItem(workspaceKey(workspaceId));
    if (!raw) return null;
    const value = JSON.parse(raw) as PersistedWorkspace;
    if (value.spec && value.spec.schema_version !== "1.0") return null;
    return value;
  } catch {
    return null;
  }
}

export default function Home() {
  const [session, setSession] = useState<AuthSession | null>(null);
  const [authLoading, setAuthLoading] = useState(true);
  const [templates, setTemplates] = useState<Template[]>([]);
  const [selectedId, setSelectedId] = useState("ema-cross");
  const [spec, setSpec] = useState<StrategySpec | null>(null);
  const [code, setCode] = useState("");
  const [input, setInput] = useState(DEFAULT_INPUT);
  const [parseResult, setParseResult] = useState<ParseResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [task, setTask] = useState<BacktestTask | null>(null);
  const [backtestId, setBacktestId] = useState<string | null>(null);
  const [result, setResult] = useState<BacktestResult | null>(null);
  const [strategyId, setStrategyId] = useState<string | null>(null);
  const [versions, setVersions] = useState<VersionItem[]>([]);
  const [saving, setSaving] = useState(false);
  const [hydrated, setHydrated] = useState(false);
  const [historyOpen, setHistoryOpen] = useState(false);
  const [tradingOpen, setTradingOpen] = useState(false);
  const [productConsoleOpen, setProductConsoleOpen] = useState(false);
  const [settingsOpen, setSettingsOpen] = useState(false);
  const [passwordSaving, setPasswordSaving] = useState(false);
  const [passwordNotice, setPasswordNotice] = useState<{ type: "success" | "error"; text: string } | null>(null);

  useEffect(() => {
    if (!getAccessToken()) {
      setAuthLoading(false);
      return;
    }
    getMe().then(setSession).catch(() => setSession(null)).finally(() => setAuthLoading(false));
  }, []);

  useEffect(() => {
    if (!session) return;
    const workspaceId = session.workspace.id;
    getTemplates().then(items => {
      setTemplates(items);
      const saved = readWorkspace(workspaceId);
      const selected = items.find(item => item.id === saved?.selectedId) ?? items[0];
      const activeSpec = saved?.spec ?? selected?.spec;
      if (activeSpec && selected) {
        setSpec(activeSpec);
        setSelectedId(saved?.selectedId ?? selected.id);
        setCode(selected.code_preview);
        setInput(saved?.input ?? DEFAULT_INPUT);
        setStrategyId(saved?.strategyId ?? null);
        setParseResult({ spec: activeSpec, confidence: 1, clarification_questions: [], compliance_status: "safe", message: saved?.spec ? "已恢复上次工作区，可以继续修改或运行回测。" : "已载入双均线模板。你可以继续用自然语言修改，或直接确认右侧参数。", provider: "workspace", code_preview: selected.code_preview });
        if (saved?.strategyId) void refreshVersions(saved.strategyId);
        if (saved?.taskId) {
          setBacktestId(saved.taskId);
          void pollTask(saved.taskId, saved.strategyId);
        }
      }
    }).catch(() => {
      setParseResult({ spec: null, confidence: 0, clarification_questions: [], compliance_status: "caution", message: "API 暂时不可用，请启动 FastAPI 服务后重试。", provider: "client" });
    }).finally(() => { setLoading(false); setHydrated(true); });
  }, [session]);

  useEffect(() => {
    if (!hydrated || !session) return;
    const value: PersistedWorkspace = {
      input,
      spec: spec ?? undefined,
      selectedId,
      strategyId: strategyId ?? undefined,
      taskId: task?.id ?? backtestId ?? undefined,
    };
    window.localStorage.setItem(workspaceKey(session.workspace.id), JSON.stringify(value));
  }, [backtestId, hydrated, input, selectedId, session?.workspace.id, spec, strategyId, task?.id]);

  const refreshVersions = useCallback(async (id: string) => {
    setVersions(await listVersions(id));
  }, []);

  const handleTemplate = (template: Template) => {
    setSelectedId(template.id);
    setSpec(template.spec);
    setCode(template.code_preview);
    setResult(null);
    setParseResult({ spec: template.spec, confidence: 1, clarification_questions: [], compliance_status: "safe", message: `已载入“${template.name}”模板，请确认参数。`, provider: "template", code_preview: template.code_preview });
  };

  const handleParse = async () => {
    setLoading(true);
    try {
      const parsed = await parseStrategy(input);
      setParseResult(parsed);
      if (parsed.spec) {
        setSpec(parsed.spec);
        setCode(parsed.code_preview ?? "");
      }
    } catch {
      setParseResult({ spec: null, confidence: 0, clarification_questions: [], compliance_status: "caution", message: "解析服务暂时不可用，请稍后重试。你的输入已保留。", provider: "client" });
    } finally {
      setLoading(false);
    }
  };

  const pollTask = async (id: string, currentStrategyId?: string) => {
    for (let attempt = 0; attempt < 80; attempt += 1) {
      const next = await getBacktest(id);
      setTask(next);
      if (next.status === "completed" && next.result) {
        setResult(next.result);
        setTask(null);
        if (currentStrategyId) await refreshVersions(currentStrategyId);
        return;
      }
      if (["failed", "cancelled"].includes(next.status)) {
        setTask(null);
        setParseResult(previous => ({
          spec: previous?.spec ?? spec,
          confidence: previous?.confidence ?? 1,
          clarification_questions: previous?.clarification_questions ?? [],
          compliance_status: previous?.compliance_status ?? "safe",
          message: next.status === "failed" ? (next.error ?? "回测失败，请检查参数后重试。") : "回测已终止，策略编辑内容已保留。",
          provider: previous?.provider ?? "system",
          code_preview: previous?.code_preview,
        }));
        return;
      }
      await new Promise(resolve => setTimeout(resolve, 500));
    }
    setTask(null);
  };

  const handleRun = async () => {
    if (!spec) return;
    setLoading(true);
    try {
      let id = strategyId;
      if (!id) {
        const created = await createStrategy(spec);
        id = created.id;
        setStrategyId(id);
        await refreshVersions(id);
      }
      const createdTask = await submitBacktest(spec, id);
      setTask(createdTask);
      setBacktestId(createdTask.id);
      void pollTask(createdTask.id, id);
    } catch {
      setParseResult(previous => ({
        spec: previous?.spec ?? spec,
        confidence: previous?.confidence ?? 1,
        clarification_questions: previous?.clarification_questions ?? [],
        compliance_status: "caution",
        message: "回测服务暂时不可用，请稍后重试。策略编辑内容已保留。",
        provider: "system",
        code_preview: previous?.code_preview,
      }));
    } finally {
      setLoading(false);
    }
  };

  const handleCancel = async () => {
    if (!task) return;
    await cancelBacktest(task.id);
    setTask(null);
    setBacktestId(null);
    setParseResult(previous => previous ? { ...previous, message: "回测已终止，策略编辑内容已保留。" } : previous);
  };

  const handleSave = async () => {
    if (!spec) return;
    setSaving(true);
    try {
      let id = strategyId;
      if (!id) {
        const created = await createStrategy(spec);
        id = created.id;
        setStrategyId(id);
      }
      await saveVersion(id, spec);
      await refreshVersions(id);
    } finally {
      setSaving(false);
    }
  };

  const handleRestore = (version: VersionItem) => {
    if (version.spec) {
      setSpec(version.spec);
      setResult(null);
      setParseResult(previous => previous ? { ...previous, message: `已恢复 ${version.label}。` } : previous);
    }
  };

  const handleApplySuggestion = (patch: Record<string, unknown> | null | undefined, title: string) => {
    if (!spec) return;
    const next = structuredClone(spec);
    const riskPatch = patch?.risk_controls as { stop_loss_pct?: number } | undefined;
    const windows = patch?.windows as string[][] | undefined;
    if (riskPatch?.stop_loss_pct !== undefined) {
      next.exit.risk_controls.stop_loss_pct = riskPatch.stop_loss_pct;
    }
    if (windows?.[0]?.[0] && windows[0][1]) {
      next.backtest.start_date = windows[0][0];
      next.backtest.end_date = windows[0][1];
    }
    const entryPatch = patch?.entry_condition as { params?: Record<string, number | string> } | undefined;
    if (entryPatch?.params && next.entry.conditions[0]) {
      next.entry.conditions[0].params = { ...next.entry.conditions[0].params, ...entryPatch.params };
    }
    setSpec(next);
    setResult(null);
    setParseResult(previous => ({
      spec: next,
      confidence: previous?.confidence ?? 1,
      clarification_questions: previous?.clarification_questions ?? [],
      compliance_status: previous?.compliance_status ?? "safe",
      message: `已应用“${title}”为策略草稿，请确认条件后重新运行回测。`,
      provider: "diagnosis-suggestion",
      code_preview: previous?.code_preview,
    }));
  };

  const handleLoadVersion = async (strategy: StrategyDetail, version: VersionDetail) => {
    setStrategyId(strategy.id);
    setSpec(version.spec);
    setSelectedId(strategy.id);
    setCode(version.backtest?.code_preview ?? "");
    setResult(version.backtest ?? null);
    setBacktestId(version.backtest_id ?? null);
    setTask(null);
    setHistoryOpen(false);
    setParseResult({
      spec: version.spec,
      confidence: 1,
      clarification_questions: [],
      compliance_status: "safe",
      message: `已载入 ${strategy.name} / ${version.label}，可以查看详情或继续修改条件。`,
      provider: "version-history",
      code_preview: version.backtest?.code_preview,
    });
    await refreshVersions(strategy.id);
  };

  const handlePasswordChange = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setPasswordNotice(null);
    const form = event.currentTarget;
    const data = new FormData(form);
    const currentPassword = String(data.get("current_password") ?? "");
    const newPassword = String(data.get("new_password") ?? "");
    const confirmPassword = String(data.get("confirm_password") ?? "");

    if (newPassword.length < 10) {
      setPasswordNotice({ type: "error", text: "新密码至少需要 10 位。" });
      return;
    }
    if (newPassword !== confirmPassword) {
      setPasswordNotice({ type: "error", text: "两次输入的新密码不一致。" });
      return;
    }

    setPasswordSaving(true);
    try {
      await changePassword(currentPassword, newPassword);
      form.reset();
      setPasswordNotice({ type: "success", text: "密码已更新，其它设备上的旧会话已失效。" });
    } catch (reason) {
      const message = reason instanceof Error ? reason.message : "";
      setPasswordNotice({ type: "error", text: message.includes("当前密码") ? "当前密码不正确。" : "暂时无法修改密码，请稍后重试。" });
    } finally {
      setPasswordSaving(false);
    }
  };

  if (authLoading) {
    return <main className="auth-loading"><BrandMark /><span>正在检查安全会话…</span></main>;
  }

  if (!session) {
    return <AuthGate onAuthenticated={value => { setSession(value); setAuthLoading(false); }} />;
  }

  const marketLabel = spec?.universe.market === "HK" ? "港股" : spec?.universe.market === "US" ? "美股" : "沪深300";

  return (
    <div className="app-shell">
      <header className="topbar">
        <div className="brand"><BrandMark /><span>QuantPartner</span><small>量化伴侣</small></div>
        <div className="data-status"><span className="live-dot" /> 数据截至 2026-06-19 · {marketLabel}</div>
        <div className="workspace-switch"><button type="button" className="paper-button" onClick={() => setTradingOpen(true)}>模拟盘</button><button type="button" className="paper-button console-entry" onClick={() => setProductConsoleOpen(true)}>控制台</button><button type="button" className="paper-button history-entry" onClick={() => setHistoryOpen(true)}><FolderClock size={13} />我的策略</button><span><strong>{session.workspace.name}</strong><small>{session.user.display_name} · {session.workspace.role}</small></span><button type="button" className="icon-button" aria-label="设置" title="设置" data-testid="settings-button" onClick={() => setSettingsOpen(true)}><Settings size={17} /></button><a className="icon-button" aria-label="退出登录" title="退出登录" data-testid="logout-link" href="/logout"><LogOut size={17} /></a></div>
      </header>
      {result && spec ? (
        <div className="app-body result-layout">
          <StrategySidebar templates={templates} selectedId={selectedId} versions={versions} onSelect={handleTemplate} onRestore={handleRestore} />
          <ResultsView result={result} spec={spec} onEdit={() => { setResult(null); setBacktestId(null); }} onSave={handleSave} onApplySuggestion={handleApplySuggestion} saving={saving} />
        </div>
      ) : (
        <div className="app-body editor-layout">
          <StrategySidebar templates={templates} selectedId={selectedId} versions={versions} onSelect={handleTemplate} onRestore={handleRestore} />
          <ChatWorkspace input={input} message={parseResult?.message ?? "正在载入策略工作区…"} compliance={parseResult?.compliance_status} questions={parseResult?.clarification_questions ?? []} loading={loading} onInput={setInput} onSubmit={handleParse} />
          {spec ? <StrategyInspector spec={spec} code={code} onChange={setSpec} onRun={handleRun} busy={loading} /> : <aside className="inspector inspector-empty">等待一条可执行的策略描述</aside>}
        </div>
      )}
      {task ? <BacktestProgress task={task} onCancel={handleCancel} /> : null}
      {tradingOpen ? <PaperTrading onClose={() => setTradingOpen(false)} /> : null}
      {productConsoleOpen ? (
        <ProductConsole
          onClose={() => setProductConsoleOpen(false)}
          onOpenPaperTrading={() => { setProductConsoleOpen(false); setTradingOpen(true); }}
          onUsePrompt={(prompt) => { setInput(prompt); setProductConsoleOpen(false); setResult(null); }}
        />
      ) : null}
      {historyOpen ? <StrategyHistoryPanel activeStrategyId={strategyId} onClose={() => setHistoryOpen(false)} onLoadVersion={handleLoadVersion} /> : null}
      {settingsOpen ? (
        <div className="settings-backdrop" role="presentation" onMouseDown={(event) => { if (event.target === event.currentTarget) setSettingsOpen(false); }}>
          <section className="settings-panel" role="dialog" aria-modal="true" aria-labelledby="settings-title">
            <header>
              <div><Settings size={19} /><span><strong id="settings-title">工作区设置</strong><small>公测阶段配置中心</small></span></div>
              <button type="button" className="icon-button" aria-label="关闭设置" data-testid="settings-close" onClick={() => setSettingsOpen(false)}><X size={18} /></button>
            </header>
            <div className="settings-content">
              <section>
                <h2>账号与工作区</h2>
                <dl>
                  <div><dt>工作区</dt><dd>{session.workspace.name}</dd></div>
                  <div><dt>成员</dt><dd>{session.user.display_name}</dd></div>
                  <div><dt>邮箱</dt><dd>{session.user.email}</dd></div>
                  <div><dt>角色</dt><dd>{session.workspace.role}</dd></div>
                </dl>
              </section>
              <section>
                <h2>账号安全</h2>
                <form className="password-form" onSubmit={handlePasswordChange}>
                  <label>当前密码<input name="current_password" type="password" required autoComplete="current-password" placeholder="输入当前密码" /></label>
                  <label>新密码<input name="new_password" type="password" required minLength={10} maxLength={128} autoComplete="new-password" placeholder="至少 10 位" /></label>
                  <label>确认新密码<input name="confirm_password" type="password" required minLength={10} maxLength={128} autoComplete="new-password" placeholder="再次输入新密码" /></label>
                  {passwordNotice ? <p className={`settings-notice ${passwordNotice.type}`} role="status">{passwordNotice.text}</p> : null}
                  <button className="secondary-button" type="submit" disabled={passwordSaving}>
                    {passwordSaving ? <span className="spinner" /> : null}
                    {passwordSaving ? "正在更新" : "修改密码"}
                  </button>
                </form>
              </section>
              <section>
                <h2>运行模式</h2>
                <dl>
                  <div><dt>当前市场</dt><dd>{marketLabel}</dd></div>
                  <div><dt>行情</dt><dd>真实数据优先 · 本地缓存可追溯</dd></div>
                  <div><dt>交易</dt><dd>模拟盘启用 · 实盘关闭</dd></div>
                  <div><dt>回测快照</dt><dd>{result?.data_snapshot?.snapshot_hash ?? "完成回测后生成"}</dd></div>
                </dl>
              </section>
              <aside><ShieldCheck size={16} /> 当前设置入口为只读预览。后续会在这里接入数据源授权、成员权限、审计日志和通知偏好。</aside>
              <footer className="settings-danger-zone">
                <div><strong>退出当前账号</strong><span>清除本机会话并返回登录页，不会删除策略、版本或回测记录。</span></div>
                <a className="secondary-button danger-button" href="/logout"><LogOut size={15} />退出登录</a>
              </footer>
            </div>
          </section>
        </div>
      ) : null}
    </div>
  );
}
