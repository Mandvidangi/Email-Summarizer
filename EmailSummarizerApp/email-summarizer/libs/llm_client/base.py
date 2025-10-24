from __future__ import annotations
from abc import ABC, abstractmethod
from typing import Dict, Any

class LLMClient(ABC):
    @abstractmethod
    def summarize_thread(self, text: str) -> Dict[str, Any]:
        ...
