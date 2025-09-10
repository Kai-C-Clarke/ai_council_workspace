"""
Agent Registry for AI Council Workspace

Manages agent lifecycle, capabilities, and status tracking to support
continuous collaboration even when agents go offline or reset.
"""

import sqlite3
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from pathlib import Path
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class AgentStatus(Enum):
    """Agent status enumeration."""
    ONLINE = "online"
    OFFLINE = "offline"
    BUSY = "busy"
    IDLE = "idle"
    ERROR = "error"

class AgentRegistry:
    """
    Registry for managing AI agents and their capabilities.
    
    Features:
    - Agent registration and deregistration
    - Status tracking and heartbeat monitoring
    - Capability management
    - Task assignment tracking
    - Automatic offline detection
    """
    
    def __init__(self, db_path: str = "agent_registry.db", heartbeat_timeout: int = 300):
        """
        Initialize agent registry.
        
        Args:
            db_path: Path to SQLite database
            heartbeat_timeout: Seconds before marking agent as offline
        """
        self.db_path = Path(db_path)
        self.heartbeat_timeout = heartbeat_timeout
        self._lock = threading.RLock()
        self._init_database()
        
    def _init_database(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            # Agents table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agents (
                    agent_id TEXT PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    capabilities TEXT,  -- JSON list
                    status TEXT DEFAULT 'offline',
                    last_heartbeat DATETIME,
                    registered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    metadata TEXT  -- JSON object
                )
            """)
            
            # Agent tasks table for tracking assignments
            conn.execute("""
                CREATE TABLE IF NOT EXISTS agent_tasks (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    agent_id TEXT NOT NULL,
                    task_id TEXT NOT NULL,
                    assigned_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    status TEXT DEFAULT 'assigned',
                    FOREIGN KEY (agent_id) REFERENCES agents (agent_id)
                )
            """)
            
            # Indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_status ON agents(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_last_heartbeat ON agents(last_heartbeat)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_tasks_agent ON agent_tasks(agent_id)
            """)
            
    def register_agent(self, agent_id: str, name: str, description: str = "",
                      capabilities: List[str] = None, metadata: Dict = None) -> bool:
        """
        Register a new agent or update existing agent info.
        
        Args:
            agent_id: Unique identifier for the agent
            name: Human-readable name
            description: Description of the agent
            capabilities: List of capabilities/skills
            metadata: Additional metadata
            
        Returns:
            True if successful
        """
        try:
            capabilities = capabilities or []
            metadata = metadata or {}
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT OR REPLACE INTO agents 
                        (agent_id, name, description, capabilities, status, 
                         last_heartbeat, registered_at, metadata)
                        VALUES (?, ?, ?, ?, ?, CURRENT_TIMESTAMP, 
                               COALESCE((SELECT registered_at FROM agents WHERE agent_id = ?), 
                                       CURRENT_TIMESTAMP), ?)
                    """, (agent_id, name, description, json.dumps(capabilities), 
                          AgentStatus.ONLINE.value, agent_id, json.dumps(metadata)))
                    
            logger.info(f"Registered agent: {agent_id} ({name})")
            return True
            
        except Exception as e:
            logger.error(f"Failed to register agent {agent_id}: {e}")
            return False
            
    def deregister_agent(self, agent_id: str) -> bool:
        """
        Deregister an agent.
        
        Args:
            agent_id: Agent to deregister
            
        Returns:
            True if successful
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("DELETE FROM agents WHERE agent_id = ?", (agent_id,))
                    conn.execute("DELETE FROM agent_tasks WHERE agent_id = ?", (agent_id,))
                    
            logger.info(f"Deregistered agent: {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to deregister agent {agent_id}: {e}")
            return False
            
    def heartbeat(self, agent_id: str, status: AgentStatus = AgentStatus.ONLINE, 
                  metadata: Dict = None) -> bool:
        """
        Record agent heartbeat to indicate it's still alive.
        
        Args:
            agent_id: Agent sending heartbeat
            status: Current agent status
            metadata: Optional status metadata
            
        Returns:
            True if successful
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Check if agent exists
                    cursor = conn.execute(
                        "SELECT 1 FROM agents WHERE agent_id = ?", (agent_id,)
                    )
                    if not cursor.fetchone():
                        logger.warning(f"Heartbeat from unregistered agent: {agent_id}")
                        return False
                        
                    # Update heartbeat and status
                    update_data = [status.value, agent_id]
                    query = """
                        UPDATE agents 
                        SET status = ?, last_heartbeat = CURRENT_TIMESTAMP
                    """
                    
                    if metadata:
                        query += ", metadata = ?"
                        update_data.insert(-1, json.dumps(metadata))
                        
                    query += " WHERE agent_id = ?"
                    conn.execute(query, update_data)
                    
            logger.debug(f"Heartbeat from {agent_id}: {status.value}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to process heartbeat from {agent_id}: {e}")
            return False
            
    def get_agent(self, agent_id: str) -> Optional[Dict]:
        """
        Get agent information.
        
        Args:
            agent_id: Agent to retrieve
            
        Returns:
            Agent dictionary or None if not found
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT agent_id, name, description, capabilities, status,
                               last_heartbeat, registered_at, metadata
                        FROM agents WHERE agent_id = ?
                    """, (agent_id,))
                    
                    row = cursor.fetchone()
                    if row:
                        return {
                            "agent_id": row[0],
                            "name": row[1],
                            "description": row[2],
                            "capabilities": json.loads(row[3]) if row[3] else [],
                            "status": row[4],
                            "last_heartbeat": row[5],
                            "registered_at": row[6],
                            "metadata": json.loads(row[7]) if row[7] else {}
                        }
                    return None
                    
        except Exception as e:
            logger.error(f"Failed to get agent {agent_id}: {e}")
            return None
            
    def list_agents(self, status: Optional[AgentStatus] = None, 
                   capability: Optional[str] = None) -> List[Dict]:
        """
        List agents with optional filtering.
        
        Args:
            status: Optional status filter
            capability: Optional capability filter
            
        Returns:
            List of agent dictionaries
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    query = """
                        SELECT agent_id, name, description, capabilities, status,
                               last_heartbeat, registered_at, metadata
                        FROM agents
                    """
                    params = []
                    
                    conditions = []
                    if status:
                        conditions.append("status = ?")
                        params.append(status.value)
                        
                    if conditions:
                        query += " WHERE " + " AND ".join(conditions)
                        
                    query += " ORDER BY registered_at"
                    
                    cursor = conn.execute(query, params)
                    agents = []
                    
                    for row in cursor.fetchall():
                        agent = {
                            "agent_id": row[0],
                            "name": row[1], 
                            "description": row[2],
                            "capabilities": json.loads(row[3]) if row[3] else [],
                            "status": row[4],
                            "last_heartbeat": row[5],
                            "registered_at": row[6],
                            "metadata": json.loads(row[7]) if row[7] else {}
                        }
                        
                        # Filter by capability if specified
                        if capability and capability not in agent["capabilities"]:
                            continue
                            
                        agents.append(agent)
                        
                    return agents
                    
        except Exception as e:
            logger.error(f"Failed to list agents: {e}")
            return []
            
    def find_capable_agents(self, required_capabilities: List[str], 
                           status: AgentStatus = AgentStatus.ONLINE) -> List[Dict]:
        """
        Find agents with specific capabilities.
        
        Args:
            required_capabilities: List of required capabilities
            status: Required agent status
            
        Returns:
            List of matching agents
        """
        agents = self.list_agents(status=status)
        capable_agents = []
        
        for agent in agents:
            agent_capabilities = set(agent["capabilities"])
            required_set = set(required_capabilities)
            
            if required_set.issubset(agent_capabilities):
                capable_agents.append(agent)
                
        return capable_agents
        
    def update_offline_agents(self) -> int:
        """
        Mark agents as offline if they haven't sent heartbeat recently.
        
        Returns:
            Number of agents marked as offline
        """
        try:
            cutoff_time = datetime.now() - timedelta(seconds=self.heartbeat_timeout)
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        UPDATE agents 
                        SET status = ?
                        WHERE last_heartbeat < ? AND status != ?
                    """, (AgentStatus.OFFLINE.value, cutoff_time, AgentStatus.OFFLINE.value))
                    
                    count = cursor.rowcount
                    
            if count > 0:
                logger.info(f"Marked {count} agents as offline")
                
            return count
            
        except Exception as e:
            logger.error(f"Failed to update offline agents: {e}")
            return 0
            
    def assign_task(self, agent_id: str, task_id: str) -> bool:
        """
        Assign a task to an agent.
        
        Args:
            agent_id: Agent to assign task to
            task_id: Task identifier
            
        Returns:
            True if successful
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT INTO agent_tasks (agent_id, task_id, status)
                        VALUES (?, ?, 'assigned')
                    """, (agent_id, task_id))
                    
            logger.debug(f"Assigned task {task_id} to agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to assign task {task_id} to {agent_id}: {e}")
            return False
            
    def update_task_status(self, agent_id: str, task_id: str, status: str) -> bool:
        """
        Update the status of an agent's task.
        
        Args:
            agent_id: Agent ID
            task_id: Task ID
            status: New status
            
        Returns:
            True if successful
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        UPDATE agent_tasks 
                        SET status = ?
                        WHERE agent_id = ? AND task_id = ?
                    """, (status, agent_id, task_id))
                    
            logger.debug(f"Updated task {task_id} status to {status} for agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to update task status: {e}")
            return False
            
    def get_agent_tasks(self, agent_id: str, status: Optional[str] = None) -> List[Dict]:
        """
        Get tasks assigned to an agent.
        
        Args:
            agent_id: Agent ID
            status: Optional status filter
            
        Returns:
            List of task assignments
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    query = """
                        SELECT task_id, assigned_at, status
                        FROM agent_tasks WHERE agent_id = ?
                    """
                    params = [agent_id]
                    
                    if status:
                        query += " AND status = ?"
                        params.append(status)
                        
                    query += " ORDER BY assigned_at DESC"
                    
                    cursor = conn.execute(query, params)
                    return [
                        {
                            "task_id": row[0],
                            "assigned_at": row[1],
                            "status": row[2]
                        }
                        for row in cursor.fetchall()
                    ]
                    
        except Exception as e:
            logger.error(f"Failed to get tasks for agent {agent_id}: {e}")
            return []
            
    def get_stats(self) -> Dict[str, Any]:
        """Get registry statistics."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    stats = {}
                    
                    # Total agents
                    cursor = conn.execute("SELECT COUNT(*) FROM agents")
                    stats["total_agents"] = cursor.fetchone()[0]
                    
                    # Agents by status
                    cursor = conn.execute("""
                        SELECT status, COUNT(*) FROM agents GROUP BY status
                    """)
                    stats["by_status"] = dict(cursor.fetchall())
                    
                    # Online agents
                    cutoff = datetime.now() - timedelta(seconds=self.heartbeat_timeout)
                    cursor = conn.execute("""
                        SELECT COUNT(*) FROM agents 
                        WHERE last_heartbeat > ? AND status != 'offline'
                    """, (cutoff,))
                    stats["recently_active"] = cursor.fetchone()[0]
                    
                    return stats
                    
        except Exception as e:
            logger.error(f"Failed to get registry stats: {e}")
            return {}