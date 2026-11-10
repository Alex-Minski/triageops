"""Data models and the triage taxonomy.

The taxonomy lives here so the classifier's JSON schema, the API validation and
the evaluation scripts all agree on the same labels.
"""

from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator


class Category(str, Enum):
    ACCESS = "access"          # logins, passwords, MFA, permissions
    HARDWARE = "hardware"      # laptops, monitors, peripherals, printers
    SOFTWARE = "software"      # installs, crashes, licences, updates
    NETWORK = "network"        # Wi-Fi, VPN, DNS, connectivity
    EMAIL = "email"            # mailboxes, calendars, distribution lists
    SECURITY = "security"      # phishing, malware, suspicious sign-ins, alerts


class Priority(str, Enum):
    P1 = "P1"  # outage or active security incident, many users or critical system
    P2 = "P2"  # one user fully blocked, or a team degraded
    P3 = "P3"  # degraded but a workaround exists
    P4 = "P4"  # request or question, no impact


class Team(str, Enum):
    SERVICE_DESK = "service_desk"
    DESKTOP_SUPPORT = "desktop_support"
    NETWORK_OPS = "network_ops"
    SECURITY_OPS = "security_ops"
    IDENTITY = "identity"
    APPLICATIONS = "applications"


class TicketIn(BaseModel):
    """A ticket as submitted through the web form or email intake."""

    title: str = Field(min_length=1, max_length=200)
    description: str = Field(min_length=1, max_length=10_000)
    source: Literal["web", "email", "alert"] = "web"
    requester: Optional[str] = Field(default=None, max_length=254)
    external_id: Optional[str] = Field(default=None, max_length=128)

    @field_validator("title", "description")
    @classmethod
    def _strip(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("must not be blank")
        return v


class AlertIn(BaseModel):
    """A Microsoft Defender-style alert as delivered by a webhook (subset of fields)."""

    alertId: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=200)
    severity: str = Field(default="medium", max_length=32)
    category: Optional[str] = Field(default=None, max_length=64)
    description: str = Field(default="", max_length=8_000)
    entities: list[dict] = Field(default_factory=list, max_length=50)

    def to_ticket(self) -> TicketIn:
        lines = [self.description or self.title, "", f"Alert severity: {self.severity}"]
        if self.category:
            lines.append(f"Alert category: {self.category}")
        for ent in self.entities[:20]:
            kind = ent.get("entityType") or ent.get("type") or "entity"
            value = ent.get("name") or ent.get("value") or ent.get("address") or ""
            lines.append(f"Entity ({kind}): {value}")
        return TicketIn(
            title=self.title,
            description="\n".join(lines).strip(),
            source="alert",
            external_id=self.alertId,
        )


class Triage(BaseModel):
    """The structured decision the classifier must return."""

    category: Category
    priority: Priority
    team: Team
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str = Field(min_length=1, max_length=600)


class ReviewIn(BaseModel):
    """A human reviewer's correction (or confirmation) of the model's triage."""

    category: Category
    priority: Priority
    team: Team
    note: Optional[str] = Field(default=None, max_length=1_000)


def triage_json_schema() -> dict:
    """JSON schema handed to the model as the only tool it may call."""
    return {
        "type": "object",
        "properties": {
            "category": {"type": "string", "enum": [c.value for c in Category]},
            "priority": {"type": "string", "enum": [p.value for p in Priority]},
            "team": {"type": "string", "enum": [t.value for t in Team]},
            "confidence": {
                "type": "number",
                "minimum": 0,
                "maximum": 1,
                "description": "Your probability that category AND priority are both correct.",
            },
            "rationale": {
                "type": "string",
                "description": "One or two sentences explaining the decision.",
            },
        },
        "required": ["category", "priority", "team", "confidence", "rationale"],
    }
