import React from "react";
import { createRoot } from "react-dom/client";
import { LiveWorkbench } from "./LiveWorkbench";
import "./styles.css";
import "./neo.css";

// Historical demo state is only downloaded when the preview is requested.
const DemoApp = React.lazy(() =>
  import("./App").then(({ App }) => ({ default: App })),
);

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {new URLSearchParams(window.location.search).get("preview") === "1" ? (
      <React.Suspense fallback={<p role="status">正在加载演示…</p>}>
        <DemoApp />
      </React.Suspense>
    ) : (
      <LiveWorkbench />
    )}
  </React.StrictMode>,
);
