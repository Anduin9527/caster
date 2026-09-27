import { ActionLink } from "./components/ActionLink";
import { expressionLabel, jobErrorLabel } from "./presentation";
import { useEffect, useState } from "react";
import {
  productionAPI,
  productionAssetURL,
  productionProgress,
  productionStateNames,
  type ProductionSnapshot,
} from "./production";

export function ProductionRecords({ characterId }: { characterId: string }) {
  const [data, setData] = useState<ProductionSnapshot | null>(null);
  const [error, setError] = useState("");
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout>;
    setData(null);
    setError("");
    async function load() {
      try {
        const snapshot = await productionAPI.snapshot(
          characterId,
          controller.signal,
        );
        if (!controller.signal.aborted) {
          setData(snapshot);
          setError("");
        }
      } catch (e) {
        if (!controller.signal.aborted)
          setError(e instanceof Error ? e.message : "制作记录连接失败。");
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(load, 5000);
      }
    }
    void load();
    return () => {
      controller.abort();
      clearTimeout(timer);
    };
  }, [characterId, revision]);
  return (
    <section className="production-records" aria-label="服务器制作记录">
      <h3>已保存的制作记录</h3>
      {error && (
        <p role="status">
          {error} {data && "当前显示上次读取的记录。"}{" "}
          <button
            className="text-button"
            onClick={() => setRevision((v) => v + 1)}
          >
            重新连接
          </button>
        </p>
      )}
      {!data && !error && <p role="status">正在读取制作记录…</p>}
      {data && (
        <>
          <p className="muted small">{data.jobs.length} 项任务</p>
          {!data.jobs.length && <p>还没有制作任务。</p>}
          {data.jobs.map((job) => {
            const progress = productionProgress(job);
            const results = data.assets.filter(
              (a) =>
                job.outputs.includes(a.id) &&
                ["original", "transparent"].includes(a.role),
            );
            const names: Record<string, string> = {
              sprite: "角色图片",
              pose: "姿态图片",
              expression: "表情图片",
              matte: "透明图片",
              outfit: "换装图片",
            };
            return (
              <details className="batch" key={job.id}>
                <summary>
                  <span>{names[job.spec.asset_type || ""] || "图片"}</span>
                  <small>{productionStateNames[job.state]}</small>
                </summary>
                <div className="disclosure-content">
                  <article className="task">
                    {job.spec.expression && (
                      <p>{expressionLabel(job.spec.expression)}</p>
                    )}
                    <p className="muted small">
                      {new Date(job.created * 1000).toLocaleString("zh-CN")}
                    </p>
                    {["running", "submitting", "recovering"].includes(
                      job.state,
                    ) &&
                      (progress === undefined ? (
                        <p>等待进度更新</p>
                      ) : (
                        <progress
                          max="100"
                          value={progress}
                          aria-label="实际制作进度"
                        />
                      ))}
                    {job.state === "submission_uncertain" && (
                      <p>提交结果需要核对，暂不重复提交。</p>
                    )}
                    {job.error && (
                      <details>
                        <summary>查看任务详情</summary>
                        <div className="disclosure-content">
                          <p className="task-error">
                            {jobErrorLabel(job.error)}
                          </p>
                        </div>
                      </details>
                    )}
                    {results.map((asset) => {
                      return (
                        <div className="production-result" key={asset.id}>
                          <a
                            href={productionAssetURL(asset.id)}
                            target="_blank"
                            rel="noreferrer"
                            aria-label="查看服务器原图"
                          >
                            <img
                              loading="lazy"
                              src={productionAssetURL(asset.id)}
                              alt={
                                asset.role === "transparent"
                                  ? "透明图片"
                                  : "制作结果"
                              }
                            />
                          </a>
                          <ActionLink
                            href={productionAssetURL(asset.id)}
                            download={`${asset.id}.png`}
                          >
                            下载原图
                          </ActionLink>
                        </div>
                      );
                    })}
                  </article>
                </div>
              </details>
            );
          })}
        </>
      )}
    </section>
  );
}
