import { Activity, BarChart3, History, Plus, RotateCcw, TrendingUp } from "lucide-react";
import type { Template, VersionItem } from "@/lib/types";

interface StrategySidebarProps {
  templates: Template[];
  selectedId: string;
  versions: VersionItem[];
  onSelect: (template: Template) => void;
  onRestore: (version: VersionItem) => void;
}

const icons = [TrendingUp, BarChart3, Activity];

export function StrategySidebar({ templates, selectedId, versions, onSelect, onRestore }: StrategySidebarProps) {
  return (
    <aside className="strategy-sidebar">
      <div className="panel-heading">
        <h2>策略与版本</h2>
        <button className="icon-button" aria-label="新建策略"><Plus size={17} /></button>
      </div>
      <div className="strategy-list">
        {templates.map((template, index) => {
          const Icon = icons[index] ?? TrendingUp;
          return (
            <button key={template.id} className={`strategy-row ${selectedId === template.id ? "selected" : ""}`} onClick={() => onSelect(template)}>
              <Icon size={18} />
              <span>{template.name}</span>
              <span className="row-dot" />
            </button>
          );
        })}
      </div>
      <div className="version-heading"><History size={15} /><span>版本历史</span></div>
      <div className="version-timeline">
        {versions.length === 0 ? (
          <p className="empty-copy">运行回测后自动创建版本</p>
        ) : versions.map((version, index) => (
          <button key={version.id} className={`version-row ${index === 0 ? "current" : ""}`} onClick={() => onRestore(version)}>
            <span className="version-node" />
            <span><strong>{version.label}</strong><small>{new Date(version.created_at).toLocaleString("zh-CN", { hour12: false })}</small></span>
            {index === 0 ? <em>当前</em> : null}
          </button>
        ))}
      </div>
      <div className="sidebar-foot"><RotateCcw size={14} /> 演示数据可随时重置</div>
    </aside>
  );
}
