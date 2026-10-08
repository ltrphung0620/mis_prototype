import type { ReactElement } from "react";

import {
  artifactTypeLabel,
  artifactValidationLabel,
} from "../../shared/artifactLabels";

import { ArtifactAssessmentView } from "./AssessmentViews";
import type { ArtifactEnvelope } from "./types";

function UpstreamArtifacts({
  artifact,
  runArtifacts,
}: {
  artifact: ArtifactEnvelope;
  runArtifacts: readonly ArtifactEnvelope[];
}): ReactElement | null {
  const upstreamIds = artifact.input_artifact_ids ?? [];
  if (!upstreamIds.length) return null;
  return (
    <section className="artifact-lineage" aria-label="Nguồn đầu vào">
      <h3>Nguồn đầu vào</h3>
      <ul>
        {upstreamIds.map((artifactId) => {
          const upstream = runArtifacts.find((item) => item.artifact_id === artifactId);
          return (
            <li key={artifactId}>
              {upstream ? (
                <>
                  <strong>{artifactTypeLabel(upstream.artifact_type)}</strong> · v{upstream.version}
                </>
              ) : (
                <strong>Không thuộc danh sách của lượt xử lý này</strong>
              )}
              <span className="artifact-id">{artifactId}</span>
            </li>
          );
        })}
      </ul>
    </section>
  );
}

export function ArtifactDetailDialog({
  artifact,
  runArtifacts = [],
  onClose,
}: {
  artifact: ArtifactEnvelope | null;
  runArtifacts?: readonly ArtifactEnvelope[];
  onClose: () => void;
}): ReactElement | null {
  if (!artifact) return null;
  // Merged Finance/Operations views keep the presented type; identity comes from the stored envelope.
  const recordedType =
    runArtifacts.find((item) => item.artifact_id === artifact.artifact_id)?.artifact_type ??
    artifact.artifact_type;
  return (
    <div
      className="assessment-dialog modal-layer"
      role="dialog"
      aria-modal="true"
      aria-labelledby="assessment-dialog-title"
    >
      <article className="modal-card">
        <header className="modal-card__header">
          <div>
            <p>{artifactTypeLabel(recordedType)}</p>
            <h2 id="assessment-dialog-title">Chi tiết đánh giá</h2>
          </div>
          <button
            type="button"
            onClick={onClose}
            aria-label="Đóng chi tiết đánh giá"
          >
            ×
          </button>
        </header>
        <p className="review-artifact-identity">
          {artifact.artifact_id} · v{artifact.version} ·{" "}
          {artifactValidationLabel(artifact.validation_status)}
        </p>
        <div className="modal-card__body">
          <ArtifactAssessmentView
            artifact={artifact}
            runArtifacts={runArtifacts}
          />
          <UpstreamArtifacts artifact={artifact} runArtifacts={runArtifacts} />
        </div>
      </article>
    </div>
  );
}
