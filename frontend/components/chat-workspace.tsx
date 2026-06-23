import { ArrowUp, Bot, CheckCircle2, CircleDashed, HelpCircle, Lightbulb, ListChecks, Sparkles, UserRound } from "lucide-react";

interface ChatWorkspaceProps {
  input: string;
  message: string;
  compliance?: "safe" | "caution" | "blocked";
  questions: string[];
  loading: boolean;
  onInput: (value: string) => void;
  onSubmit: () => void;
}

interface GuidanceStep {
  id: string;
  title: string;
  description: string;
  status: "done" | "missing" | "review";
  detected: string;
  prompt: string;
  suggestions: string[];
}

const DEFAULT_PROMPT = "沪深300里，EMA20上穿EMA60买入，跌破EMA20卖出，8%止损";

const TEMPLATE_SUGGESTIONS = [
  "沪深300里，EMA20上穿EMA60买入，跌破EMA20卖出，8%止损",
  "美股科技股中，近60日动量排名靠前买入，跌破20日均线卖出，10%止损",
  "沪深300里，PE低于30且ROE高于12%的股票，月度调仓，ROE跌破8%卖出",
];

function includesAny(text: string, words: string[]): boolean {
  return words.some(word => text.includes(word));
}

function detectGuidance(input: string, questions: string[]): GuidanceStep[] {
  const text = input.trim();
  const normalized = text.toUpperCase();
  const hasMarket = includesAny(text, ["沪深300", "A股", "中国", "港股", "恒生", "美股", "SPY", "纳斯达克"]) || includesAny(normalized, ["CN_A", "HK", "US"]);
  const hasUniverse = hasMarket || includesAny(text, ["科技股", "成长股", "价值股", "低估值", "股票池", "成分股"]);
  const hasSelection = includesAny(text, ["近60日涨幅", "涨幅排名", "趋势强", "动量", "PE", "ROE", "低于", "高于", "质量好", "估值低"]) || includesAny(normalized, ["MOMENTUM", "PE", "ROE"]);
  const hasEntry = includesAny(text, ["买入", "上穿", "突破", "新高"]) || includesAny(normalized, ["EMA", "MA", "CROSS_ABOVE"]);
  const hasExit = includesAny(text, ["卖出", "止损", "止盈", "跌破", "下穿", "回撤"]) || includesAny(normalized, ["CROSS_BELOW", "STOP"]);
  const hasRisk = includesAny(text, ["止损", "止盈", "仓位", "%", "最大回撤"]);
  const hasBacktest = includesAny(text, ["2019", "2020", "2021", "2022", "2023", "2024", "2025", "2026", "日线", "周线", "月度", "调仓", "回测"]);
  const needsMore = questions.length > 0 || text.length < 18;

  return [
    {
      id: "universe",
      title: "1. 明确股票池",
      description: "先确定在哪个市场和范围里找股票。",
      status: hasUniverse ? "done" : "missing",
      detected: hasUniverse ? "已识别市场/股票池线索" : "还没说明市场或股票池",
      prompt: "你想在哪个范围里选股？",
      suggestions: ["沪深300成分股", "美股科技股", "港股恒生指数成分股"],
    },
    {
      id: "selection",
      title: "2. 说清选股逻辑",
      description: "把“好股票”翻译成可计算指标。",
      status: hasSelection ? "done" : "missing",
      detected: hasSelection ? "已识别可计算的选股指标" : "缺少可计算的筛选条件",
      prompt: "你认为“好”主要指哪类特征？",
      suggestions: ["趋势强：近60日涨幅排名靠前", "质量好：ROE高于12%", "估值低：PE低于30"],
    },
    {
      id: "entry",
      title: "3. 定义买入触发",
      description: "什么时候从候选股里真正买入。",
      status: hasEntry ? "done" : "missing",
      detected: hasEntry ? "已包含买入或筛选触发" : "还没有明确买入规则",
      prompt: "满足什么条件才买入？",
      suggestions: ["EMA20上穿EMA60时买入", "近60日动量进入前20%买入", "PE低于30且ROE高于12%买入"],
    },
    {
      id: "exit",
      title: "4. 定义卖出与风控",
      description: "提前写清退出条件，避免只会买不会卖。",
      status: hasExit && hasRisk ? "done" : hasExit ? "review" : "missing",
      detected: hasExit ? (hasRisk ? "已包含卖出和风控" : "已有卖出规则，建议补止损/仓位") : "缺少卖出规则",
      prompt: "什么情况下退出？风险怎么限制？",
      suggestions: ["跌破EMA20卖出，8%止损", "跌出动量前40%卖出，10%止损", "ROE跌破8%卖出，单票不超过20%仓位"],
    },
    {
      id: "backtest",
      title: "5. 选择回测口径",
      description: "确认时间范围、频率和调仓方式。",
      status: hasBacktest ? "done" : needsMore ? "missing" : "review",
      detected: hasBacktest ? "已包含回测口径线索" : "默认使用2019年至今、日线回测",
      prompt: "是否需要固定回测区间和调仓频率？",
      suggestions: ["2019年至今，日线回测", "每周调仓", "每月调仓，初始资金100万"],
    },
  ];
}

function mergeSuggestion(input: string, suggestion: string): string {
  const trimmed = input.trim();
  if (!trimmed) return suggestion;
  if (trimmed.includes(suggestion)) return trimmed;
  const separator = /[。；;，,]$/.test(trimmed) ? "" : "；";
  return `${trimmed}${separator}${suggestion}`;
}

export function ChatWorkspace({ input, message, compliance, questions, loading, onInput, onSubmit }: ChatWorkspaceProps) {
  const guidance = detectGuidance(input, questions);
  const missingCount = guidance.filter(step => step.status === "missing").length;
  const blocked = compliance === "blocked";
  const nextStep = guidance.find(step => step.status === "missing") ?? guidance.find(step => step.status === "review");

  return (
    <main className="chat-workspace">
      <header className="chat-hero">
        <p className="eyebrow">STRATEGY CLARIFIER</p>
        <h1>先把想法拆清楚，再交给数据验证</h1>
        <p>我会把一句模糊想法拆成股票池、选股逻辑、买入、卖出风控和回测口径，帮你一步步补齐。</p>
      </header>

      <div className="conversation">
        <article className="message user-message">
          <header><span><UserRound size={15} /> 你</span><time>刚刚</time></header>
          <p>{input || DEFAULT_PROMPT}</p>
        </article>
        <article className={`message assistant-message ${blocked ? "blocked" : ""}`}>
          <header><span><Bot size={15} /> AI 策略教练</span><time>{blocked ? "合规拦截" : "澄清建议"}</time></header>
          <p>{blocked ? message : missingCount > 0 ? `我已理解你的方向，但还需要补齐 ${missingCount} 个关键规则，才能变成可回测策略。` : message}</p>
          {questions.map(question => <p className="question" key={question}><HelpCircle size={13} />{question}</p>)}
        </article>
      </div>

      {!blocked ? (
        <section className="clarifier-panel" aria-label="策略澄清步骤">
          <div className="clarifier-summary">
            <span><ListChecks size={15} /> 策略澄清地图</span>
            <strong>{5 - missingCount}/5</strong>
          </div>
          <div className="clarifier-steps">
            {guidance.map(step => (
              <article className={`clarifier-step ${step.status}`} key={step.id}>
                <header>
                  {step.status === "done" ? <CheckCircle2 size={16} /> : <CircleDashed size={16} />}
                  <span>{step.title}</span>
                </header>
                <p>{step.description}</p>
                <small>{step.detected}</small>
              </article>
            ))}
          </div>
          {nextStep ? (
            <div className="next-question">
              <div>
                <span><Lightbulb size={15} /> 下一步建议</span>
                <strong>{nextStep.prompt}</strong>
              </div>
              <div className="suggestion-chips">
                {nextStep.suggestions.map(suggestion => (
                  <button type="button" key={suggestion} onClick={() => onInput(mergeSuggestion(input, suggestion))}>
                    {suggestion}
                  </button>
                ))}
              </div>
            </div>
          ) : null}
          <div className="template-jump">
            <span>也可以直接套用一个完整起点：</span>
            {TEMPLATE_SUGGESTIONS.map(suggestion => (
              <button type="button" key={suggestion} onClick={() => onInput(suggestion)}>
                {suggestion.includes("动量") ? "动量科技股" : suggestion.includes("ROE") ? "价值质量" : "双均线"}
              </button>
            ))}
          </div>
        </section>
      ) : null}

      <div className="composer-wrap">
        <textarea value={input} onChange={event => onInput(event.target.value)} placeholder="例如：我想买美股里涨势较好的科技股…" maxLength={1000} onKeyDown={event => {
          if ((event.metaKey || event.ctrlKey) && event.key === "Enter") onSubmit();
        }} />
        <div className="composer-actions">
          <span>{input.length} / 1000 · ⌘ Enter</span>
          <button className="primary-button" onClick={onSubmit} disabled={loading || input.trim().length < 2}>
            {loading ? <span className="spinner" /> : <Sparkles size={16} />}
            {loading ? "解析中" : missingCount > 0 ? "继续澄清" : "生成策略"}<ArrowUp size={15} />
          </button>
        </div>
      </div>
    </main>
  );
}
