import React from "react";
import { createRoot } from "react-dom/client";
import { LiveWorkbench } from "./LiveWorkbench";
import { App } from "./App.tsx";
import "./styles.css";
import "./neo.css";
createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    {new URLSearchParams(window.location.search).get("preview") === "1" ? (
      <App />
    ) : (
      <LiveWorkbench />
    )}
  </React.StrictMode>,
);
