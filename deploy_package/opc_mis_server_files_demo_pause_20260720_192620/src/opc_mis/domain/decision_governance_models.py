"""Server-owned Governance policy for final Decision confirmation."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, StrictBool, StrictStr


class DecisionGovernancePolicyDocument(BaseModel):
    """Validated policy semantics before the canonical configuration hash is added."""

    model_config = ConfigDict(frozen=True, extra="forbid")

    policy_id: StrictStr = Field(min_length=1)
    policy_version: StrictStr = Field(min_length=1)
    final_decision_requires_founder: StrictBool
    approver_role: Literal["FOUNDER"] = "FOUNDER"


class DecisionGovernancePolicy(DecisionGovernancePolicyDocument):
    """Versioned policy with a formatting-independent configuration identity."""

    policy_hash: StrictStr = Field(min_length=64, max_length=64)
