"""
AI Council Workspace

A collaborative framework enabling persistent AI-to-AI communication 
and task management across session boundaries.
"""

__version__ = "0.1.0"
__author__ = "Kai-C-Clarke"

from .core.shared_memory import SharedMemory
from .core.agent_registry import AgentRegistry
from .core.task_manager import TaskManager
from .core.coordination_engine import CoordinationEngine

__all__ = [
    "SharedMemory",
    "AgentRegistry", 
    "TaskManager",
    "CoordinationEngine"
]