"""Error taxonomy for the core engine.

Per plan section 0 item 3: missing or inconsistent card/rules data must fail
loudly, never be guessed or silently degraded.
"""

from __future__ import annotations


class FabDraftCoreError(Exception):
    """Base class for all errors raised by fabdraft_core."""


class DataIncompleteError(FabDraftCoreError):
    """Raised when source card/set data is missing a required field or is
    otherwise ambiguous. Ingestion and validation code must raise this
    rather than fabricate a value. See plan section 0 item 3 and section 2.5.
    """


class PackGenerationError(FabDraftCoreError):
    """Raised when a pack cannot be generated as configured (e.g. a slot's
    candidate pool is exhausted) rather than silently relaxing constraints.
    See plan section 6.1.
    """
