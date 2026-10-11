import { createContext, useContext } from "react";
import * as fixtures from "./fixtures";

/** Replace this read model provider only after the corresponding API scope is approved.
 * No write methods, production API clients or orchestration are imported by the preview. */
export type PreviewDataset = typeof fixtures;
export const PreviewDataContext = createContext<PreviewDataset>(fixtures);
export const usePreviewData = () => useContext(PreviewDataContext);
