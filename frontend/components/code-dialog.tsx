"use client";

import { Check, Clipboard, Code2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";

interface CodeDialogProps {
  code: string;
  open: boolean;
  onClose: () => void;
}

export function CodeDialog({ code, open, onClose }: CodeDialogProps) {
  const closeButtonRef = useRef<HTMLButtonElement>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    if (!open) {
      setCopied(false);
      return;
    }
    closeButtonRef.current?.focus();
    const handleKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose, open]);

  if (!open) return null;

  const copyCode = async () => {
    try {
      await navigator.clipboard.writeText(code);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className="code-dialog-backdrop" role="presentation" onMouseDown={onClose}>
      <section
        className="code-dialog"
        role="dialog"
        aria-modal="true"
        aria-labelledby="strategy-code-title"
        onMouseDown={event => event.stopPropagation()}
      >
        <header>
          <div>
            <Code2 size={18} />
            <span><strong id="strategy-code-title">策略代码</strong><small>由结构化策略确定性生成 · 只读</small></span>
          </div>
          <div className="code-dialog-actions">
            <button className="secondary-button" onClick={copyCode}>
              {copied ? <Check size={14} /> : <Clipboard size={14} />}{copied ? "已复制" : "复制代码"}
            </button>
            <button ref={closeButtonRef} className="icon-button" aria-label="关闭策略代码" onClick={onClose}><X size={18} /></button>
          </div>
        </header>
        <pre><code>{code}</code></pre>
        <footer>代码仅用于解释策略逻辑；回测引擎执行经过校验的 StrategySpecV1，不执行任意模型代码。</footer>
      </section>
    </div>
  );
}
