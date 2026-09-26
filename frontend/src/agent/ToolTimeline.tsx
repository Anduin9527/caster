import { CheckCircle, CircleNotch, WarningCircle } from "@phosphor-icons/react";
import type { ToolTrace } from "../agent";

export function ToolTimeline({ traces }: { traces: ToolTrace[] }) {
  if (!traces.length) return null;
  return (
    <section className="agent-tool-timeline" aria-label="工具调用过程">
      <div className="agent-tool-heading">
        <span className="eyebrow">AGENT TOOLS</span>
        <strong>已检索的过程</strong>
      </div>
      <ol>
        {traces.map((trace) => (
          <li className={"agent-tool-row " + trace.status} key={trace.call_id}>
            <span className="agent-tool-icon" aria-hidden="true">
              {trace.status === "running" ? (
                <CircleNotch className="spin" size={16} />
              ) : trace.status === "completed" ? (
                <CheckCircle size={16} weight="fill" />
              ) : (
                <WarningCircle size={16} weight="fill" />
              )}
            </span>
            <div className="agent-tool-body">
              <div>
                <strong>{trace.label}</strong>
                {trace.duration_ms !== undefined && (
                  <span>{trace.duration_ms} ms</span>
                )}
              </div>
              <p>{trace.summary}</p>
              {(trace.arguments || trace.result) && (
                <details>
                  <summary>查看调用摘要</summary>
                  {trace.arguments && (
                    <div>
                      <span>输入</span>
                      <code>{JSON.stringify(trace.arguments, null, 2)}</code>
                    </div>
                  )}
                  {trace.result && Object.keys(trace.result).length > 0 && (
                    <div>
                      <span>结果</span>
                      <code>{JSON.stringify(trace.result, null, 2)}</code>
                    </div>
                  )}
                </details>
              )}
            </div>
          </li>
        ))}
      </ol>
    </section>
  );
}
