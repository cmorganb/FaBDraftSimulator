"""Generated pydantic models for contracts/*.schema.json.

Do not hand-edit this file's imports - regenerate with
scripts/generate_contract_models.py. Re-exports a stable name per
contract so callers write `from fabdraft_core.contracts import Card`
instead of reaching into `.generated.card_schema`.
"""

from __future__ import annotations

from .generated.agent_view_schema import AgentView as AgentView
from .generated.card_schema import Card as Card
from .generated.decklist_schema import Decklist as Decklist
from .generated.draft_event_schema import DraftEvent as DraftEvent
from .generated.pack_config_schema import PackConfig as PackConfig
from .generated.pick_decision_schema import PickDecision as PickDecision
from .generated.session_config_schema import SessionConfig as SessionConfig
from .generated.set_schema import SetSnapshot as SetSnapshot

__all__ = [
    "AgentView",
    "Card",
    "Decklist",
    "DraftEvent",
    "PackConfig",
    "PickDecision",
    "SessionConfig",
    "SetSnapshot",
]
