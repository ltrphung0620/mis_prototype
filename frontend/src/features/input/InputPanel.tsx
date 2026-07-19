import type {
  ContractCatalog,
  NormalizedWorkflowDashboard,
} from "../../api/types";
import { formatVndCompact, pluralizeCount } from "../../shared/formatters";
import { LoadingBlock } from "../../shared/components/LoadingBlock";
import { Notice } from "../../shared/components/Notice";
import { Panel } from "../../shared/components/Panel";
import { StatusBadge } from "../../shared/components/StatusBadge";
import {
  isTerminalExecutionStatus,
  statusLabel,
} from "../../shared/workflowLabels";

interface InputPanelProps {
  catalog: ContractCatalog | null;
  selectedContractId: string;
  dashboard: NormalizedWorkflowDashboard | null;
  bootstrapping: boolean;
  starting: boolean;
  onSelectContract: (contractId: string) => void;
  onStart: () => void;
}

export function InputPanel({
  catalog,
  selectedContractId,
  dashboard,
  bootstrapping,
  starting,
  onSelectContract,
  onStart,
}: InputPanelProps) {
  const input = dashboard?.input;
  const canStart = Boolean(
    catalog &&
      selectedContractId &&
      !starting &&
      (!dashboard || isTerminalExecutionStatus(dashboard.status)),
  );
  const selectedContract = catalog?.contracts.find(
    (item) => item.contractId === selectedContractId,
  );

  return (
    <Panel
      eyebrow="01 · ĐẦU VÀO"
      title="Chọn hợp đồng"
      className="input-panel"
      aside={
        dashboard ? (
          <StatusBadge
            status={input?.readinessStatus ?? dashboard.status}
            label={input?.readinessLabel}
          />
        ) : null
      }
    >
      {bootstrapping ? (
        <LoadingBlock label="Đang tải danh mục hợp đồng" rows={5} />
      ) : (
        <>
          <p className="panel-intro">
            TeamPack được máy chủ quản lý. Bạn chỉ cần chọn đúng hợp đồng; hệ thống sẽ
            tự liên kết các bản ghi có quan hệ rõ ràng.
          </p>

          <label className="field" htmlFor="contract-select">
            <span>Hợp đồng cần đánh giá</span>
            <select
              id="contract-select"
              value={selectedContractId}
              onChange={(event) => onSelectContract(event.target.value)}
              disabled={!catalog?.contracts.length || starting}
            >
              {!catalog?.contracts.length ? (
                <option value="">Không có hợp đồng khả dụng</option>
              ) : null}
              {catalog?.contracts.map((contract) => (
                <option value={contract.contractId} key={contract.contractId}>
                  {contract.label}
                </option>
              ))}
            </select>
          </label>

          {selectedContract?.customerName ? (
            <p className="selected-customer">
              Khách hàng: <strong>{selectedContract.customerName}</strong>
            </p>
          ) : null}

          <button
            className="primary-action"
            type="button"
            disabled={!canStart}
            onClick={onStart}
          >
            <span aria-hidden="true">{starting ? "…" : "→"}</span>
            {starting
              ? "Đang khởi tạo lượt đánh giá"
              : dashboard
                ? "Bắt đầu lượt đánh giá mới"
                : "Bắt đầu đánh giá"}
          </button>

          <dl className="dataset-facts">
            <div>
              <dt>Bộ dữ liệu</dt>
              <dd title={catalog?.datasetId}>{catalog?.datasetId || "Chưa tải"}</dd>
            </div>
          </dl>

          {dashboard ? (
            <section className="input-readiness" aria-labelledby="input-readiness-title">
              <div className="section-heading">
                <div>
                  <span>HỒ SƠ ĐÃ TIẾP NHẬN</span>
                  <h3 id="input-readiness-title">Tình trạng dữ liệu đầu vào</h3>
                </div>
                <StatusBadge
                  compact
                  status={input?.readinessStatus ?? dashboard.status}
                  label={input?.readinessLabel}
                />
              </div>

              {input?.linkedRecords.length ? (
                <ul className="linked-counts" aria-label="Các bản ghi được liên kết rõ ràng">
                  {input.linkedRecords.map((record) => (
                    <li key={record.key}>
                      <strong>{record.count}</strong>
                      <span>{record.label}</span>
                    </li>
                  ))}
                </ul>
              ) : (
                <p className="empty-copy">
                  Thống kê liên kết sẽ xuất hiện khi phần tổng hợp đầu vào được hoàn tất.
                </p>
              )}

              {input?.contractRequirements.length ? (
                <section className="contract-requirements" aria-labelledby="contract-requirements-title">
                  <div className="subsection-heading">
                    <span>YÊU CẦU TỪ HỢP ĐỒNG</span>
                    <h4 id="contract-requirements-title">Nhu cầu cần xử lý</h4>
                  </div>
                  <div className="requirement-list">
                    {input.contractRequirements.map((requirement) => (
                      <article className="requirement-card" key={requirement.id}>
                        <header>
                          <div>
                            <strong>{requirement.requirementLabel}</strong>
                          </div>
                          <span>{statusLabel(requirement.certainty)}</span>
                        </header>
                        <dl>
                          <div>
                            <dt>Giá trị yêu cầu</dt>
                            <dd>
                              {requirement.amount === undefined
                                ? "Chưa xác định"
                                : formatVndCompact(
                                    requirement.amount,
                                    requirement.currency ?? "VND",
                                  )}
                            </dd>
                          </div>
                          <div>
                            <dt>Hồ sơ tín dụng</dt>
                            <dd>{requirement.creditCaseId ?? "Chưa liên kết"}</dd>
                          </div>
                        </dl>
                      </article>
                    ))}
                  </div>
                </section>
              ) : null}

              <div className="input-counters">
                <span className={dashboard.pendingMissingDataCount ? "counter counter--warning" : "counter"}>
                  {pluralizeCount(dashboard.pendingMissingDataCount, "yêu cầu bổ sung")}
                </span>
                <span className={dashboard.pendingApprovalCount ? "counter counter--active" : "counter"}>
                  {pluralizeCount(dashboard.pendingApprovalCount, "yêu cầu phê duyệt")}
                </span>
              </div>

              {input?.blockingItems.length ? (
                <Notice tone="warning" title="Cần bổ sung dữ liệu trước khi tiếp tục">
                  {input.blockingItems.join(" · ")}
                </Notice>
              ) : null}

              {input?.warnings.length ? (
                <div className="input-warnings">
                  <strong>Lưu ý không gây dừng</strong>
                  <ul>
                    {input.warnings.map((warning, index) => (
                      <li key={`${warning}-${index}`}>{warning}</li>
                    ))}
                  </ul>
                </div>
              ) : null}
            </section>
          ) : (
            <div className="input-empty">
              <span aria-hidden="true">◇</span>
              <p>Chưa có hồ sơ đánh giá cho lựa chọn hiện tại.</p>
            </div>
          )}
        </>
      )}
    </Panel>
  );
}
