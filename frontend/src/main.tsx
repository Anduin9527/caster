import React from "react";
import { createRoot } from "react-dom/client";
import { LiveWorkbench } from "./LiveWorkbench";
import { QueryClientProvider } from "@tanstack/react-query";
import { createQueryClient } from "./workbench/queries";
import "./styles.css";
import "./neo.css";

// Historical demo state is only downloaded when the preview is requested.
const DemoApp = React.lazy(() =>
  import("./App").then(({ App }) => ({ default: App })),
);

const queryClient = createQueryClient();

createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      {new URLSearchParams(window.location.search).get("preview") === "1" ? (
        <React.Suspense fallback={<p role="status">正在加载演示…</p>}>
          <DemoApp />
        </React.Suspense>
      ) : (
        <LiveWorkbench />
      )}
    </QueryClientProvider>
  </React.StrictMode>,
);
