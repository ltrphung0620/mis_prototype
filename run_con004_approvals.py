"""Execution script to run CON-004, auto-approve all human approvals, handle all input stages, and log to Downloads/runtime_log.txt in real-time."""

import datetime
import json
import os
from pathlib import Path
import time
from fastapi.testclient import TestClient

# Load environment variables from .env file
env_path = Path(".env")
if env_path.exists():
    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ[k.strip()] = v.strip()

# Explicitly ensure HMAC key is set to a valid 32-byte Base64 key
os.environ["OPC_MIS_MASKING_HMAC_KEY_BASE64"] = "MDEyMzQ1Njc4OWFiY2RlZjAxMjM0NTY3ODlhYmNkZWY="

from opc_mis.api.application import create_app

TEAM_PACK = Path("data/input/MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx").resolve()
LOG_PATH = Path(r"C:\Users\LENOVO\Downloads\runtime_log.txt")

# Initialize and truncate log file
LOG_PATH.parent.mkdir(parents=True, exist_ok=True)
with open(LOG_PATH, "w", encoding="utf-8") as f:
    f.write("")

def log(msg: str):
    timestamp = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
    entry = f"[{timestamp}] {msg}"
    print(entry)
    with open(LOG_PATH, "a", encoding="utf-8") as f:
        f.write(entry + "\n")
        f.flush()

def main():
    log("==========================================================")
    log("OPC MIS Agentic AI - Workflow Execution CON-004")
    log("==========================================================")
    log(f"TeamPack Location: {TEAM_PACK}")
    log("Target Case: CON-004")
    log("Auto-approval Mode: ENABLED (All human approval gates auto-approved by FOUNDER)")

    app = create_app(
        workbook_path=TEAM_PACK,
        dataset_id="MISTalent2026_OPC_AgenticAI_TeamPack_v3",
        database_path=":memory:",
    )

    with TestClient(app) as client:
        log("FastAPI Runtime Application Initialized Successfully")

        # Start Case Workflow
        start_res = client.post(
            "/api/cases/run",
            json={
                "contract_id": "CON-004",
                "evaluation_scope": ["FINANCE", "OPERATIONS", "RISK"],
                "as_of_date": "2026-07-16",
            },
        )
        assert start_res.status_code == 202, f"Failed to start case: {start_res.text}"
        start_data = start_res.json()

        workflow_run_id = start_data["workflow_run_id"]
        evaluation_case_id = start_data["evaluation_case_id"]

        log("Workflow Initiated:")
        log(f"  - Workflow Run ID: {workflow_run_id}")
        log(f"  - Evaluation Case ID: {evaluation_case_id}")
        log(f"  - Initial Status: {start_data['status']}")

        step = 0
        while True:
            step += 1
            summary_res = client.get(f"/api/workflows/{workflow_run_id}")
            assert summary_res.status_code == 200
            curr = summary_res.json()

            status = curr["status"]
            current_stage = curr.get("current_stage")
            blocked_action = curr.get("blocked_action")
            pending_approval_ids = curr.get("pending_approval_ids", [])
            pending_missing_ids = curr.get("pending_missing_data_ids", [])
            
            if curr.get("evaluation_case_id"):
                evaluation_case_id = curr["evaluation_case_id"]

            log(f"Step {step} -> Status: {status} | Stage: {current_stage} | Blocked Action: {blocked_action}")

            # Check terminal status
            if status in ("COMPLETED", "FAILED_SAFE"):
                log("----------------------------------------------------------")
                log(f"Workflow reached terminal status: {status}")
                log(f"Final Stage: {current_stage}")
                log("Node Progress Summary:")
                for n in curr.get("nodes", []):
                    log(f"  - Node [{n['node']}]: {n['status']}")
                break

            # Handle WAITING_FOR_APPROVAL dynamically
            if status == "WAITING_FOR_APPROVAL":
                log(f"  [PAUSE REASON] Waiting for Human Approval on pending requests: {pending_approval_ids}")
                
                # Fetch approval request details
                reqs_res = client.get(f"/api/cases/{evaluation_case_id}/approval-requests")
                if reqs_res.status_code == 200:
                    for req in reqs_res.json():
                        if req.get("request_id") in pending_approval_ids:
                            cmd = req.get("command", {})
                            log(f"  [APPROVAL DETAILS] Request ID: {req['request_id']}")
                            log(f"    - Action Type: {cmd.get('action_type')}")
                            log(f"    - Payload: {cmd.get('payload')}")

                for app_id in pending_approval_ids:
                    log(f"  [ACTION] Approving request_id={app_id} (Role: FOUNDER, Reason: HUMAN_REVIEW_COMPLETED)")
                    dec_res = client.post(
                        f"/api/approval-requests/{app_id}/decision",
                        json={
                            "decision": "APPROVE",
                            "decided_by": "FOUNDER",
                            "reason": "HUMAN_REVIEW_COMPLETED",
                        },
                    )
                    assert dec_res.status_code == 200, f"Approval failed: {dec_res.text}"
                    log(f"  [RESULT] Approval Authorized: {dec_res.json().get('action_authorized')}")

                time.sleep(0.1)
                continue

            # Handle WAITING_FOR_INPUT
            if status == "WAITING_FOR_INPUT":
                if current_stage == "DOCUMENT_PREPARATION":
                    log(f"  [PAUSE REASON] Missing document evidence required: {pending_missing_ids}")
                    artifacts = client.get(f"/api/cases/{evaluation_case_id}/artifacts").json()
                    checklist = next(
                        (item for item in reversed(artifacts) if item.get("artifact_type") == "DOCUMENT_CHECKLIST"),
                        None
                    )

                    for missing_id in pending_missing_ids:
                        doc_type = "PERFORMANCE_BOND_REQUEST_FORM"
                        if checklist and "items" in checklist.get("payload", {}):
                            for item in checklist["payload"]["items"]:
                                if item.get("missing_request_id") == missing_id:
                                    doc_type = item.get("document_code", doc_type)
                                    break

                        doc_ref = (
                            "DOCREF-00000000-0000-4000-8000-000000000002"
                            if doc_type == "PERFORMANCE_BOND_REQUEST_FORM"
                            else "DOCREF-00000000-0000-4000-8000-000000000005"
                        )

                        log(f"  [ACTION] Supplying evidence supplement for missing_id={missing_id} ({doc_type}) with ref={doc_ref}")
                        supp_res = client.post(
                            f"/api/cases/{evaluation_case_id}/documents/evidence-supplements",
                            json={
                                "workflow_run_id": workflow_run_id,
                                "missing_request_id": missing_id,
                                "document_reference_id": doc_ref,
                                "content_sha256": "b" * 64,
                                "document_type": doc_type,
                                "evidence_note": "REQUESTED_DOCUMENT_REFERENCE_SUPPLIED",
                            },
                        )
                        assert supp_res.status_code == 202, f"Evidence submission failed: {supp_res.text}"
                        log(f"  [RESULT] Evidence supplement accepted (status: 202)")

                    time.sleep(0.1)
                    continue

                elif current_stage == "NEGOTIATION_TERMS_SENT":
                    log("  [PAUSE REASON] Waiting for confirmation that negotiation terms were sent")
                    
                    artifacts = client.get(f"/api/cases/{evaluation_case_id}/artifacts").json()
                    decision_card = next(
                        (a for a in artifacts if a.get("artifact_type") == "DECISION_CARD"), None
                    )
                    assert decision_card is not None, "Decision Card not found during terms sent confirmation"
                    card_art_id = decision_card["artifact_id"]
                    
                    log(f"  [ACTION] Confirming negotiation terms sent for Decision Card Artifact ID: {card_art_id}")
                    confirm_res = client.post(
                        f"/api/cases/{evaluation_case_id}/negotiation/terms-sent",
                        json={
                            "workflow_run_id": workflow_run_id,
                            "decision_card_artifact_id": card_art_id,
                        },
                    )
                    assert confirm_res.status_code == 202, f"Negotiation terms confirmation failed: {confirm_res.text}"
                    log("  [RESULT] Negotiation terms confirmation accepted")
                    
                    time.sleep(0.1)
                    continue

                elif current_stage == "NEGOTIATION_OUTCOME_RECEIVED":
                    log("  [PAUSE REASON] Waiting for negotiation outcome submission")
                    
                    artifacts = client.get(f"/api/cases/{evaluation_case_id}/artifacts").json()
                    decision_card = next(
                        (a for a in artifacts if a.get("artifact_type") == "DECISION_CARD"), None
                    )
                    assert decision_card is not None, "Decision Card not found during negotiation outcome submission"
                    card_art_id = decision_card["artifact_id"]
                    card_payload = decision_card.get("payload", {})
                    
                    # Accept all conditions
                    condition_outcomes = []
                    for cond in card_payload.get("conditions", []):
                        log(f"    - Preparing outcome for Condition ID: {cond.get('condition_id')}")
                        condition_outcomes.append({
                            "condition_id": cond["condition_id"],
                            "customer_accepted": True,
                            "founder_note": "Negotiation accepted by customer"
                        })
                    
                    log(f"  [ACTION] Submitting customer negotiation outcomes (Accepting all conditions)")
                    outcome_res = client.post(
                        f"/api/cases/{evaluation_case_id}/negotiation/outcome",
                        json={
                            "workflow_run_id": workflow_run_id,
                            "decision_card_artifact_id": card_art_id,
                            "condition_outcomes": condition_outcomes,
                            "founder_summary": "Customer accepted all conditions during manual review"
                        },
                    )
                    assert outcome_res.status_code == 202, f"Negotiation outcome submission failed: {outcome_res.text}"
                    log("  [RESULT] Negotiation outcome successfully submitted")
                    
                    time.sleep(0.1)
                    continue

            time.sleep(0.1)

        # Retrieve all events for this workflow run to show process linkage and API history
        log("----------------------------------------------------------")
        log("Retrieving Workflow Events (API/Tool History & Trace IDs)...")
        events_res = client.get(f"/api/workflows/{workflow_run_id}/events")
        if events_res.status_code == 200:
            events = events_res.json()
            log(f"Total events found: {len(events)}")
            for idx, event in enumerate(events):
                log(f"  Event #{idx+1} | ID: {event.get('event_id')} | Trace/Workflow Run ID: {event.get('workflow_run_id')} | Type: {event.get('event_type')} | Node: {event.get('node')}")
        else:
            log(f"Failed to retrieve workflow events: {events_res.status_code}")

        # Retrieve Document Release Package to extract Masking Manifest details
        if evaluation_case_id:
            log("----------------------------------------------------------")
            log("Retrieving Masking Manifest details for outbound sensitive data...")
            artifacts_res = client.get(f"/api/cases/{evaluation_case_id}/artifacts")
            if artifacts_res.status_code == 200:
                artifacts = artifacts_res.json()
                release_pkg = next(
                    (a for a in artifacts if a.get("artifact_type") == "DOCUMENT_RELEASE_PACKAGE"), 
                    None
                )
                if release_pkg:
                    manifest = release_pkg.get("payload", {}).get("masking_manifest", {})
                    log(f"Masking Manifest ID: {manifest.get('manifest_id')}")
                    log(f"Policy Reference ID: {manifest.get('policy_id')} (v{manifest.get('policy_version')})")
                    log(f"Recipient: {manifest.get('recipient')} | Purpose: {manifest.get('purpose')}")
                    log("Masked Fields:")
                    for item in manifest.get("items", []):
                        log(f"  - Field: {item.get('field_name')}")
                        log(f"    * Action: {item.get('action')}")
                        log(f"    * Algorithm: {item.get('algorithm_id')} ({item.get('algorithm_version')})")
                        log(f"    * Output Digest (Redacted SHA256): {item.get('output_digest')}")
                        log(f"    * Source Evidence IDs: {item.get('source_evidence_ids')}")
                else:
                    log("DOCUMENT_RELEASE_PACKAGE artifact not found.")
            else:
                log(f"Failed to retrieve case artifacts: {artifacts_res.status_code}")

    log("==========================================================")
    log("CON-004 Execution and Approval Log Finished Successfully")
    log("==========================================================")

if __name__ == "__main__":
    main()
