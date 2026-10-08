import { useMemo, useState, type FormEvent, type ReactElement } from "react";

import type { NegotiationOutcomePayload } from "../../api/client";
import type { DecisionCondition } from "../decision/types";

interface Props {
  workflowRunId: string;
  decisionCardArtifactId: string;
  conditions: DecisionCondition[];
  submitting?: boolean;
  onClose: () => void;
  onSubmit: (payload: NegotiationOutcomePayload) => void | Promise<void>;
}

function conditionId(condition: DecisionCondition, index: number): string {
  return condition.condition_id?.trim() || `condition-${index + 1}`;
}

export function NegotiationOutcomeForm({
  workflowRunId,
  decisionCardArtifactId,
  conditions,
  submitting = false,
  onClose,
  onSubmit,
}: Props): ReactElement {
  const [responses, setResponses] = useState<Record<string, boolean>>(() =>
    Object.fromEntries(
      conditions.map((condition, index) => [conditionId(condition, index), true]),
    ),
  );
  const [notes, setNotes] = useState<Record<string, string>>({});
  const [summary, setSummary] = useState("");
  const accepted = useMemo(
    () =>
      conditions.filter((_item, index) => responses[conditionId(_item, index)] === true)
        .length,
    [conditions, responses],
  );

  const submit = (event: FormEvent) => {
    event.preventDefault();
    if (!conditions.length) return;
    void onSubmit({
      workflow_run_id: workflowRunId,
      decision_card_artifact_id: decisionCardArtifactId,
      condition_outcomes: conditions.map((condition, index) => {
        const id = conditionId(condition, index);
        return {
          condition_id: id,
          customer_accepted: responses[id] ?? false,
          ...(notes[id]?.trim() ? { founder_note: notes[id].trim() } : {}),
        };
      }),
      ...(summary.trim() ? { founder_summary: summary.trim() } : {}),
    });
  };

  return (
    <div className="approval-dialog" role="dialog" aria-modal="true" aria-labelledby="negotiation-outcome-title">
      <article>
        <header>
          <p>Vòng đàm phán có điều kiện</p>
          <h2 id="negotiation-outcome-title">Ghi nhận phản hồi của khách hàng</h2>
        </header>
        <form onSubmit={submit}>
          {conditions.map((condition, index) => {
            const id = conditionId(condition, index);
            return (
              <fieldset key={id || condition.title} disabled={submitting || !id}>
                <legend>{condition.title}</legend>
                <p>{condition.description}</p>
                <label>
                  <input
                    type="radio"
                    name={`condition-${id}`}
                    checked={responses[id] === true}
                    onChange={() => setResponses((current) => ({ ...current, [id]: true }))}
                  />
                  Khách hàng đồng ý
                </label>
                <label>
                  <input
                    type="radio"
                    name={`condition-${id}`}
                    checked={responses[id] === false}
                    onChange={() => setResponses((current) => ({ ...current, [id]: false }))}
                  />
                  Khách hàng từ chối
                </label>
                <label>
                  Ghi chú (không bắt buộc)
                  <textarea
                    value={notes[id] ?? ""}
                    maxLength={500}
                    onChange={(event) =>
                      setNotes((current) => ({ ...current, [id]: event.target.value }))
                    }
                  />
                </label>
              </fieldset>
            );
          })}
          <p><strong>{accepted}/{conditions.length}</strong> điều kiện được khách hàng chấp thuận.</p>
          <label>
            Tóm tắt của Founder (không bắt buộc)
            <textarea value={summary} maxLength={1000} onChange={(event) => setSummary(event.target.value)} />
          </label>
          <footer>
            <button type="button" onClick={onClose} disabled={submitting}>Đóng</button>
            <button type="submit" disabled={submitting || !conditions.length}>Gửi kết quả để xác nhận</button>
          </footer>
        </form>
      </article>
    </div>
  );
}
