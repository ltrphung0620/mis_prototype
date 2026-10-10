import { useEffect, useState } from "react";
import type { CompanySection, ContractSection, PreviewRoute } from "./models";

const companySections = [
  "overview",
  "finance",
  "business",
  "invoices",
  "alerts",
];
const contractViews = [
  "overview",
  "assessments",
  "workflow",
  "evidence",
  "history",
];
export function parsePreviewRoute(hash: string): PreviewRoute {
  const [path, query] = (hash.replace(/^#/, "") || "/dashboard").split("?");
  const params = new URLSearchParams(query);
  if (path === "/dashboard")
    return { page: "dashboard", period: params.get("period") ?? "all" };
  if (path === "/company")
    return {
      page: "company",
      section: (companySections.includes(params.get("section") ?? "")
        ? params.get("section")
        : "overview") as CompanySection,
      period: params.get("period") ?? "all",
      status: params.get("status") ?? "all",
    };
  if (path === "/contracts") return { page: "contracts" };
  const match = /^\/contracts\/([A-Za-z0-9-]+)$/.exec(path);
  if (match)
    return {
      page: "contracts",
      contractId: match[1],
      view: (contractViews.includes(params.get("view") ?? "")
        ? params.get("view")
        : "overview") as ContractSection,
      request: params.get("request") ?? undefined,
    };
  return { page: "not-found" };
}
export function navigatePreview(path: string) {
  window.location.hash = path;
}
export function usePreviewRoute(): PreviewRoute {
  const [hash, setHash] = useState(() => window.location.hash);
  useEffect(() => {
    const change = () => {
      setHash(window.location.hash);
      window.scrollTo({ top: 0, behavior: "instant" });
    };
    window.addEventListener("hashchange", change);
    return () => window.removeEventListener("hashchange", change);
  }, []);
  return parsePreviewRoute(hash);
}
