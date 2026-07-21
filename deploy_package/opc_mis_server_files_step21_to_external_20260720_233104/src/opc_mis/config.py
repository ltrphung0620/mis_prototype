"""Environment-backed runtime configuration."""

import base64
import binascii
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from os import getenv
from pathlib import Path

DEFAULT_DATASET_ID = "MISTalent2026_OPC_AgenticAI_TeamPack_v3"
DEFAULT_WORKBOOK_PATH = (
    Path(__file__).resolve().parents[2]
    / "data"
    / "input"
    / "MISTalent2026_OPC_AgenticAI_TeamPack_v3.xlsx"
)
DEFAULT_DATABASE_PATH = Path(__file__).resolve().parents[2] / "data" / "runtime" / "opc_mis.db"
DEFAULT_BANKING_CATALOG_POLICY_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "banking" / "catalog_mappings.json"
)
DEFAULT_BANKING_PRECHECK_SIMULATION_POLICY_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "banking"
    / "precheck_simulation_scenarios.json"
)
DEFAULT_BANKING_PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "prompts"
    / "banking_option_advisor.md"
)
DEFAULT_MASKING_POLICY_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "data_protection"
    / "masking_policy.json"
)
DEFAULT_DECISION_GOVERNANCE_POLICY_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "decision"
    / "decision_governance_policy.json"
)
DEFAULT_DECISION_PROMPT_PATH = (
    Path(__file__).resolve().parents[2]
    / "config"
    / "prompts"
    / "decision_analysis.md"
)


def _masking_hmac_key_from_environment() -> bytes | None:
    """Decode secret key material without retaining or echoing its text form."""
    encoded = getenv("OPC_MIS_MASKING_HMAC_KEY_BASE64")
    if not encoded:
        return None
    try:
        key = base64.b64decode(encoded, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise ValueError(
            "OPC_MIS_MASKING_HMAC_KEY_BASE64 must be valid Base64."
        ) from exc
    if len(key) < 32:
        raise ValueError(
            "OPC_MIS_MASKING_HMAC_KEY_BASE64 must decode to at least 32 bytes."
        )
    return key


@dataclass(frozen=True)
class AppSettings:
    """Configuration resolved by the interface composition root."""

    team_pack_path: Path
    dataset_id: str
    openai_enabled: bool
    openai_api_key: str | None = dataclass_field(repr=False)
    openai_model: str
    openai_timeout_seconds: float
    openai_max_retries: int
    finance_prompt_version: str
    finance_prompt_path: Path
    banking_catalog_policy_path: Path
    banking_precheck_simulation_policy_path: Path
    banking_prompt_version: str
    banking_prompt_path: Path
    masking_policy_path: Path
    decision_governance_policy_path: Path
    decision_prompt_version: str
    decision_prompt_path: Path
    masking_hmac_key: bytes | None = dataclass_field(repr=False)
    database_path: Path

    @classmethod
    def from_environment(cls) -> "AppSettings":
        """Build settings without exposing file paths in the public API."""
        return cls(
            team_pack_path=Path(getenv("OPC_MIS_TEAM_PACK_PATH", str(DEFAULT_WORKBOOK_PATH))),
            dataset_id=getenv("OPC_MIS_DATASET_ID", DEFAULT_DATASET_ID),
            openai_enabled=getenv("OPENAI_ENABLED", "false").strip().casefold()
            in {"1", "true", "yes", "on"},
            openai_api_key=getenv("OPENAI_API_KEY") or None,
            openai_model=getenv("OPENAI_MODEL", "gpt-5.6-terra"),
            openai_timeout_seconds=float(getenv("OPENAI_TIMEOUT_SECONDS", "12")),
            openai_max_retries=int(getenv("OPENAI_MAX_RETRIES", "1")),
            finance_prompt_version=getenv("FINANCE_PROMPT_VERSION", "finance-narrative-v3"),
            finance_prompt_path=Path(
                getenv(
                    "FINANCE_PROMPT_PATH",
                    str(
                        Path(__file__).resolve().parents[2]
                        / "config"
                        / "prompts"
                        / "finance_narrative.md"
                    ),
                )
            ),
            banking_catalog_policy_path=Path(
                getenv(
                    "BANKING_CATALOG_POLICY_PATH",
                    str(DEFAULT_BANKING_CATALOG_POLICY_PATH),
                )
            ),
            banking_precheck_simulation_policy_path=Path(
                getenv(
                    "BANKING_PRECHECK_SIMULATION_POLICY_PATH",
                    str(DEFAULT_BANKING_PRECHECK_SIMULATION_POLICY_PATH),
                )
            ),
            banking_prompt_version=getenv(
                "BANKING_PROMPT_VERSION", "banking-option-advisor-v1"
            ),
            banking_prompt_path=Path(
                getenv("BANKING_PROMPT_PATH", str(DEFAULT_BANKING_PROMPT_PATH))
            ),
            masking_policy_path=Path(
                getenv("MASKING_POLICY_PATH", str(DEFAULT_MASKING_POLICY_PATH))
            ),
            decision_governance_policy_path=Path(
                getenv(
                    "DECISION_GOVERNANCE_POLICY_PATH",
                    str(DEFAULT_DECISION_GOVERNANCE_POLICY_PATH),
                )
            ),
            decision_prompt_version=getenv(
                "DECISION_PROMPT_VERSION", "decision-analysis-v7"
            ),
            decision_prompt_path=Path(
                getenv("DECISION_PROMPT_PATH", str(DEFAULT_DECISION_PROMPT_PATH))
            ),
            masking_hmac_key=_masking_hmac_key_from_environment(),
            database_path=Path(
                getenv("OPC_MIS_DATABASE_PATH", str(DEFAULT_DATABASE_PATH))
            ),
        )
