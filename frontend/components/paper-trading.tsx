"use client";

import { FormEvent, useEffect, useState } from "react";
import { CircleDollarSign, X } from "lucide-react";
import { cancelPaperOrder, createPaperOrder, listPaperOrders } from "@/lib/api";
import type { PaperOrder } from "@/lib/types";

export function PaperTrading({ onClose }: { onClose: () => void }) {
  const [orders, setOrders] = useState<PaperOrder[]>([]);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => { void listPaperOrders().then(setOrders).catch(() => setError("订单列表暂时不可用。")); }, []);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const form = event.currentTarget;
    setBusy(true);
    setError("");
    const data = new FormData(event.currentTarget);
    const orderType = String(data.get("order_type")) as "market" | "limit";
    try {
      const order = await createPaperOrder({
        market: String(data.get("market")) as "CN_A" | "HK" | "US", symbol: String(data.get("symbol")),
        side: String(data.get("side")) as "buy" | "sell", order_type: orderType,
        quantity: Number(data.get("quantity")), limit_price: orderType === "limit" ? Number(data.get("limit_price")) : undefined,
      });
      setOrders(previous => [order, ...previous]);
      form.reset();
    } catch {
      setError("订单未提交，请检查代码、数量和价格。" );
    } finally {
      setBusy(false);
    }
  }

  async function cancel(order: PaperOrder) {
    const updated = await cancelPaperOrder(order.id);
    setOrders(previous => previous.map(item => item.id === updated.id ? updated : item));
  }

  return (
    <div className="trade-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) onClose(); }}>
      <aside className="trade-drawer" role="dialog" aria-modal="true" aria-labelledby="paper-title">
        <header><div><CircleDollarSign size={19} /><span><strong id="paper-title">模拟交易</strong><small>所有订单仅在 QuantPartner 模拟账户中执行</small></span></div><button className="icon-button" onClick={onClose} aria-label="关闭"><X size={18} /></button></header>
        <form className="order-ticket" onSubmit={submit}>
          <label>市场<select name="market"><option value="CN_A">中国 A 股</option><option value="HK">港股</option><option value="US">美股</option></select></label>
          <label>证券代码<input name="symbol" required placeholder="例如 600519.SH / AAPL.US" /></label>
          <div className="ticket-row"><label>方向<select name="side"><option value="buy">买入</option><option value="sell">卖出</option></select></label><label>订单类型<select name="order_type"><option value="limit">限价</option><option value="market">市价</option></select></label></div>
          <div className="ticket-row"><label>数量<input name="quantity" required type="number" min="0.0001" step="any" /></label><label>限价<input name="limit_price" type="number" min="0.0001" step="any" /></label></div>
          {error ? <p className="auth-error">{error}</p> : null}
          <button className="primary-button" disabled={busy}>{busy ? "提交中…" : "确认提交模拟订单"}</button>
          <p>提交订单代表你已主动确认。本功能不连接实盘账户。</p>
        </form>
        <section className="order-list"><header><h2>最近订单</h2><span>{orders.length} 笔</span></header>{orders.length ? orders.map(order => <article key={order.id}><div><strong>{order.symbol}</strong><small>{order.market} · {order.order_type === "limit" ? `限价 ${order.limit_price}` : "市价"}</small></div><div><strong className={order.side === "buy" ? "negative" : "positive"}>{order.side === "buy" ? "买入" : "卖出"} {order.quantity}</strong><small>{order.status === "accepted" ? "已受理" : order.status === "cancelled" ? "已撤销" : order.status}</small></div>{order.status === "accepted" ? <button onClick={() => void cancel(order)}>撤单</button> : null}</article>) : <p className="empty-copy">还没有模拟订单。</p>}</section>
      </aside>
    </div>
  );
}
