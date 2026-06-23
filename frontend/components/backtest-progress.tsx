import { Square } from "lucide-react";
import type { BacktestTask } from "@/lib/types";

export function BacktestProgress({ task, onCancel }: { task: BacktestTask; onCancel: () => void }) {
  return (
    <div className="progress-overlay" role="dialog" aria-modal="true" aria-label="回测进度">
      <div className="progress-dialog">
        <div className="progress-orbit" style={{ "--progress": `${task.progress * 3.6}deg` } as React.CSSProperties}>
          <span>{task.progress}%</span>
        </div>
        <h2>{task.stage}</h2>
        <p>历史数据正在成为证据，而不是答案。</p>
        <div className="linear-progress"><span style={{ width: `${task.progress}%` }} /></div>
        <div className="progress-steps"><span className={task.progress >= 12 ? "active" : ""}>载入行情</span><span className={task.progress >= 36 ? "active" : ""}>计算指标</span><span className={task.progress >= 62 ? "active" : ""}>逐日推演</span><span className={task.progress >= 86 ? "active" : ""}>核算绩效</span></div>
        <button className="secondary-button" onClick={onCancel}><Square size={13} fill="currentColor" />终止回测</button>
      </div>
    </div>
  );
}
