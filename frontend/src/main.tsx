import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { App } from "./app/App";
import { PreviewEntry } from "./preview/PreviewEntry";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/dashboard.css";

const isPreview =
  new URLSearchParams(window.location.search).get("preview") === "1";

createRoot(document.getElementById("root")!).render(
  <StrictMode>{isPreview ? <PreviewEntry /> : <App />}</StrictMode>,
);
