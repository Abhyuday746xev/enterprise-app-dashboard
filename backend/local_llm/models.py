# ==========================================
# Local AI Models
# ==========================================

from .config import CHAT_MODEL
from .config import EMBEDDING_MODEL


class EnterpriseModels:
    """
    Central place for all AI models
    used inside the enterprise dashboard.
    """

    CHAT = CHAT_MODEL

    EMBEDDING = EMBEDDING_MODEL


def get_chat_model():
    return EnterpriseModels.CHAT


def get_embedding_model():
    return EnterpriseModels.EMBEDDING