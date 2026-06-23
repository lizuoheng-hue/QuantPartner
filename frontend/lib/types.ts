export type Operator = "GT" | "GTE" | "LT" | "LTE" | "EQ" | "CROSS_ABOVE" | "CROSS_BELOW";

export interface Condition {
  field: string;
  operator: Operator;
  value: number | string;
  params: Record<string, number | string>;
  enabled: boolean;
}

export interface StrategySpec {
  schema_version: "1.0";
  name: string;
  universe: { market: "CN_A" | "HK" | "US"; index: "000300.SH" | "HSI.HK" | "SPY.US"; filters: Condition[] };
  entry: { logic: "AND" | "OR"; conditions: Condition[] };
  exit: {
    logic: "AND" | "OR";
    conditions: Condition[];
    risk_controls: { stop_loss_pct?: number; take_profit_pct?: number; max_position_pct?: number };
  };
  backtest: {
    start_date: string;
    end_date: string;
    benchmark: "000300.SH" | "HSI.HK" | "SPY.US";
    initial_capital: number;
    rebalance: "daily" | "weekly" | "monthly" | "quarterly";
  };
}

export interface Template {
  id: string;
  name: string;
  spec: StrategySpec;
  code_preview: string;
}

export interface ParseResult {
  spec: StrategySpec | null;
  confidence: number;
  clarification_questions: string[];
  compliance_status: "safe" | "caution" | "blocked";
  message: string;
  provider: string;
  code_preview?: string;
}

export interface MetricSet {
  annual_return: number;
  max_drawdown: number;
  sharpe: number;
  win_rate: number;
  profit_loss_ratio: number;
  alpha: number;
  beta: number;
}

export interface SeriesPoint { date: string; value: number }
export interface Trade {
  date: string;
  symbol: string;
  name: string;
  side: "买入" | "卖出";
  price: number;
  quantity: number;
  fee: number;
}

export interface BacktestResult {
  summary: string;
  disclaimer: string;
  code_preview: string;
  metrics: MetricSet;
  equity_curve: SeriesPoint[];
  benchmark_curve: SeriesPoint[];
  drawdown_curve: SeriesPoint[];
  trades: Trade[];
  data_source: string;
  data_snapshot?: {
    id: string;
    provider: string;
    market: "CN_A" | "HK" | "US";
    symbol: string;
    vendor_symbol?: string;
    frequency: string;
    start_date: string;
    end_date: string;
    rows: number;
    snapshot_hash: string;
    storage_path: string;
    source: string;
    status: string;
    fetched_at: string;
  } | null;
  strategy_hash: string;
}

export interface BacktestTask {
  id: string;
  status: "queued" | "running" | "completed" | "failed" | "cancelled";
  progress: number;
  stage: string;
  result: BacktestResult | null;
  data_snapshot_id?: string | null;
  error?: string;
  created_at: string;
}

export interface VersionItem {
  id: string;
  label: string;
  created_at: string;
  spec?: StrategySpec;
}

export interface AuthSession {
  access_token?: string;
  user: { id: string; email: string; display_name: string };
  workspace: { id: string; name: string; slug: string; role: string };
}

export interface PaperOrder {
  id: string;
  account_type: "paper" | "live";
  market: "CN_A" | "HK" | "US";
  symbol: string;
  side: "buy" | "sell";
  order_type: "market" | "limit";
  quantity: number;
  limit_price?: number;
  status: "accepted" | "filled" | "cancelled" | "rejected";
  filled_quantity: number;
  average_price?: number;
  client_order_id: string;
  created_at: string;
}
