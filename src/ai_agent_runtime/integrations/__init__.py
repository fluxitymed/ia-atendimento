"""External integration adapters for the agent runtime."""

from .crm_conversations import (
    CrmConversationMonitor,
    CrmConversationRepository,
    CrmOrganizationResolver,
    CrmRestConflictError,
    CrmRestTransport,
    UnknownCrmInstanceError,
    sanitize_crm_error,
)

__all__ = [
    "CrmConversationMonitor",
    "CrmConversationRepository",
    "CrmOrganizationResolver",
    "CrmRestConflictError",
    "CrmRestTransport",
    "UnknownCrmInstanceError",
    "sanitize_crm_error",
]
