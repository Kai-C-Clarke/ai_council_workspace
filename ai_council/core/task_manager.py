"""
Task Manager for AI Council Workspace

Manages task queuing, assignment, and execution tracking across agents
to enable continuous collaborative work even when agents are offline.
"""

import sqlite3
import json
import threading
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Set
from pathlib import Path
from enum import Enum
import logging

logger = logging.getLogger(__name__)

class TaskStatus(Enum):
    """Task status enumeration."""
    PENDING = "pending"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class TaskPriority(Enum):
    """Task priority levels."""
    LOW = 1
    NORMAL = 2
    HIGH = 3
    URGENT = 4

class TaskManager:
    """
    Task management system for coordinating work across AI agents.
    
    Features:
    - Task creation and queuing
    - Priority-based assignment
    - Dependency tracking
    - Progress monitoring
    - Automatic reassignment on failure
    - Result storage
    """
    
    def __init__(self, db_path: str = "task_manager.db", max_retries: int = 3):
        """
        Initialize task manager.
        
        Args:
            db_path: Path to SQLite database
            max_retries: Maximum retry attempts for failed tasks
        """
        self.db_path = Path(db_path)
        self.max_retries = max_retries
        self._lock = threading.RLock()
        self._init_database()
        
    def _init_database(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            # Tasks table
            conn.execute("""
                CREATE TABLE IF NOT EXISTS tasks (
                    task_id TEXT PRIMARY KEY,
                    title TEXT NOT NULL,
                    description TEXT,
                    task_type TEXT,
                    required_capabilities TEXT,  -- JSON list
                    input_data TEXT,  -- JSON object
                    output_data TEXT,  -- JSON object
                    priority INTEGER DEFAULT 2,
                    status TEXT DEFAULT 'pending',
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    assigned_at DATETIME,
                    started_at DATETIME,
                    completed_at DATETIME,
                    assigned_agent TEXT,
                    created_by TEXT,
                    retry_count INTEGER DEFAULT 0,
                    max_retries INTEGER DEFAULT 3,
                    deadline DATETIME,
                    metadata TEXT  -- JSON object
                )
            """)
            
            # Task dependencies
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_dependencies (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    depends_on_task_id TEXT NOT NULL,
                    FOREIGN KEY (task_id) REFERENCES tasks (task_id),
                    FOREIGN KEY (depends_on_task_id) REFERENCES tasks (task_id),
                    UNIQUE(task_id, depends_on_task_id)
                )
            """)
            
            # Task execution log
            conn.execute("""
                CREATE TABLE IF NOT EXISTS task_execution_log (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT NOT NULL,
                    agent_id TEXT,
                    event_type TEXT NOT NULL,
                    event_data TEXT,
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    FOREIGN KEY (task_id) REFERENCES tasks (task_id)
                )
            """)
            
            # Indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_status ON tasks(status)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_priority ON tasks(priority)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_assigned_agent ON tasks(assigned_agent)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_task_created_at ON tasks(created_at)
            """)
            
    def create_task(self, title: str, description: str = "", task_type: str = "general",
                   required_capabilities: List[str] = None, input_data: Dict = None,
                   priority: TaskPriority = TaskPriority.NORMAL, created_by: str = "system",
                   deadline: Optional[datetime] = None, dependencies: List[str] = None,
                   metadata: Dict = None) -> Optional[str]:
        """
        Create a new task.
        
        Args:
            title: Task title
            description: Task description
            task_type: Type/category of task
            required_capabilities: List of required agent capabilities
            input_data: Input data for the task
            priority: Task priority level
            created_by: Who created the task
            deadline: Optional deadline
            dependencies: List of task IDs this task depends on
            metadata: Additional metadata
            
        Returns:
            Task ID if successful, None otherwise
        """
        try:
            task_id = str(uuid.uuid4())
            required_capabilities = required_capabilities or []
            input_data = input_data or {}
            dependencies = dependencies or []
            metadata = metadata or {}
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Create task
                    conn.execute("""
                        INSERT INTO tasks (
                            task_id, title, description, task_type, required_capabilities,
                            input_data, priority, created_by, deadline, max_retries, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        task_id, title, description, task_type,
                        json.dumps(required_capabilities), json.dumps(input_data),
                        priority.value, created_by, deadline, self.max_retries,
                        json.dumps(metadata)
                    ))
                    
                    # Add dependencies
                    for dep_task_id in dependencies:
                        conn.execute("""
                            INSERT INTO task_dependencies (task_id, depends_on_task_id)
                            VALUES (?, ?)
                        """, (task_id, dep_task_id))
                    
                    # Log creation
                    self._log_event(conn, task_id, None, "created", {
                        "created_by": created_by,
                        "priority": priority.name
                    })
                    
            logger.info(f"Created task: {task_id} ({title})")
            return task_id
            
        except Exception as e:
            logger.error(f"Failed to create task: {e}")
            return None
            
    def get_task(self, task_id: str) -> Optional[Dict]:
        """
        Get task details.
        
        Args:
            task_id: Task identifier
            
        Returns:
            Task dictionary or None if not found
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT task_id, title, description, task_type, required_capabilities,
                               input_data, output_data, priority, status, created_at,
                               assigned_at, started_at, completed_at, assigned_agent,
                               created_by, retry_count, max_retries, deadline, metadata
                        FROM tasks WHERE task_id = ?
                    """, (task_id,))
                    
                    row = cursor.fetchone()
                    if row:
                        task = {
                            "task_id": row[0],
                            "title": row[1],
                            "description": row[2],
                            "task_type": row[3],
                            "required_capabilities": json.loads(row[4]) if row[4] else [],
                            "input_data": json.loads(row[5]) if row[5] else {},
                            "output_data": json.loads(row[6]) if row[6] else {},
                            "priority": row[7],
                            "status": row[8],
                            "created_at": row[9],
                            "assigned_at": row[10],
                            "started_at": row[11],
                            "completed_at": row[12],
                            "assigned_agent": row[13],
                            "created_by": row[14],
                            "retry_count": row[15],
                            "max_retries": row[16],
                            "deadline": row[17],
                            "metadata": json.loads(row[18]) if row[18] else {}
                        }
                        
                        # Get dependencies
                        dep_cursor = conn.execute("""
                            SELECT depends_on_task_id FROM task_dependencies
                            WHERE task_id = ?
                        """, (task_id,))
                        task["dependencies"] = [row[0] for row in dep_cursor.fetchall()]
                        
                        return task
                    
                    return None
                    
        except Exception as e:
            logger.error(f"Failed to get task {task_id}: {e}")
            return None
            
    def list_tasks(self, status: Optional[TaskStatus] = None,
                  assigned_agent: Optional[str] = None,
                  created_by: Optional[str] = None,
                  limit: int = 100) -> List[Dict]:
        """
        List tasks with optional filtering.
        
        Args:
            status: Filter by task status
            assigned_agent: Filter by assigned agent
            created_by: Filter by creator
            limit: Maximum number of tasks to return
            
        Returns:
            List of task dictionaries
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    query = """
                        SELECT task_id, title, description, task_type, required_capabilities,
                               input_data, output_data, priority, status, created_at,
                               assigned_at, started_at, completed_at, assigned_agent,
                               created_by, retry_count, max_retries, deadline, metadata
                        FROM tasks
                    """
                    
                    conditions = []
                    params = []
                    
                    if status:
                        conditions.append("status = ?")
                        params.append(status.value)
                        
                    if assigned_agent:
                        conditions.append("assigned_agent = ?")
                        params.append(assigned_agent)
                        
                    if created_by:
                        conditions.append("created_by = ?")
                        params.append(created_by)
                        
                    if conditions:
                        query += " WHERE " + " AND ".join(conditions)
                        
                    query += " ORDER BY priority DESC, created_at ASC LIMIT ?"
                    params.append(limit)
                    
                    cursor = conn.execute(query, params)
                    tasks = []
                    
                    for row in cursor.fetchall():
                        task = {
                            "task_id": row[0],
                            "title": row[1],
                            "description": row[2],
                            "task_type": row[3],
                            "required_capabilities": json.loads(row[4]) if row[4] else [],
                            "input_data": json.loads(row[5]) if row[5] else {},
                            "output_data": json.loads(row[6]) if row[6] else {},
                            "priority": row[7],
                            "status": row[8],
                            "created_at": row[9],
                            "assigned_at": row[10],
                            "started_at": row[11],
                            "completed_at": row[12],
                            "assigned_agent": row[13],
                            "created_by": row[14],
                            "retry_count": row[15],
                            "max_retries": row[16],
                            "deadline": row[17],
                            "metadata": json.loads(row[18]) if row[18] else {}
                        }
                        tasks.append(task)
                        
                    return tasks
                    
        except Exception as e:
            logger.error(f"Failed to list tasks: {e}")
            return []
            
    def get_available_tasks(self, agent_capabilities: List[str]) -> List[Dict]:
        """
        Get tasks that can be assigned to an agent with given capabilities.
        
        Args:
            agent_capabilities: List of agent capabilities
            
        Returns:
            List of available tasks sorted by priority
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Get pending tasks without unmet dependencies
                    cursor = conn.execute("""
                        SELECT t.task_id, t.title, t.description, t.task_type, 
                               t.required_capabilities, t.input_data, t.priority,
                               t.created_at, t.deadline, t.metadata
                        FROM tasks t
                        WHERE t.status = 'pending'
                        AND NOT EXISTS (
                            SELECT 1 FROM task_dependencies td
                            JOIN tasks dt ON td.depends_on_task_id = dt.task_id
                            WHERE td.task_id = t.task_id 
                            AND dt.status NOT IN ('completed', 'cancelled')
                        )
                        ORDER BY t.priority DESC, t.created_at ASC
                    """)
                    
                    available_tasks = []
                    agent_caps_set = set(agent_capabilities)
                    
                    for row in cursor.fetchall():
                        required_caps = json.loads(row[4]) if row[4] else []
                        required_caps_set = set(required_caps)
                        
                        # Check if agent has all required capabilities
                        if required_caps_set.issubset(agent_caps_set):
                            task = {
                                "task_id": row[0],
                                "title": row[1],
                                "description": row[2],
                                "task_type": row[3],
                                "required_capabilities": required_caps,
                                "input_data": json.loads(row[5]) if row[5] else {},
                                "priority": row[6],
                                "created_at": row[7],
                                "deadline": row[8],
                                "metadata": json.loads(row[9]) if row[9] else {}
                            }
                            available_tasks.append(task)
                            
                    return available_tasks
                    
        except Exception as e:
            logger.error(f"Failed to get available tasks: {e}")
            return []
            
    def assign_task(self, task_id: str, agent_id: str) -> bool:
        """
        Assign a task to an agent.
        
        Args:
            task_id: Task to assign
            agent_id: Agent to assign to
            
        Returns:
            True if successful
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Check if task is available for assignment
                    cursor = conn.execute("""
                        SELECT status FROM tasks WHERE task_id = ?
                    """, (task_id,))
                    
                    result = cursor.fetchone()
                    if not result or result[0] != TaskStatus.PENDING.value:
                        logger.warning(f"Task {task_id} not available for assignment")
                        return False
                        
                    # Assign task
                    conn.execute("""
                        UPDATE tasks 
                        SET status = ?, assigned_agent = ?, assigned_at = CURRENT_TIMESTAMP
                        WHERE task_id = ?
                    """, (TaskStatus.ASSIGNED.value, agent_id, task_id))
                    
                    # Log assignment
                    self._log_event(conn, task_id, agent_id, "assigned", {})
                    
            logger.info(f"Assigned task {task_id} to agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to assign task {task_id}: {e}")
            return False
            
    def start_task(self, task_id: str, agent_id: str) -> bool:
        """
        Mark a task as started by an agent.
        
        Args:
            task_id: Task ID
            agent_id: Agent ID
            
        Returns:
            True if successful
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        UPDATE tasks 
                        SET status = ?, started_at = CURRENT_TIMESTAMP
                        WHERE task_id = ? AND assigned_agent = ?
                    """, (TaskStatus.IN_PROGRESS.value, task_id, agent_id))
                    
                    # Log start
                    self._log_event(conn, task_id, agent_id, "started", {})
                    
            logger.info(f"Task {task_id} started by agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to start task {task_id}: {e}")
            return False
            
    def complete_task(self, task_id: str, agent_id: str, output_data: Dict = None) -> bool:
        """
        Mark a task as completed.
        
        Args:
            task_id: Task ID
            agent_id: Agent ID
            output_data: Task output/results
            
        Returns:
            True if successful
        """
        try:
            output_data = output_data or {}
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        UPDATE tasks 
                        SET status = ?, output_data = ?, completed_at = CURRENT_TIMESTAMP
                        WHERE task_id = ? AND assigned_agent = ?
                    """, (TaskStatus.COMPLETED.value, json.dumps(output_data), task_id, agent_id))
                    
                    # Log completion
                    self._log_event(conn, task_id, agent_id, "completed", output_data)
                    
            logger.info(f"Task {task_id} completed by agent {agent_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to complete task {task_id}: {e}")
            return False
            
    def fail_task(self, task_id: str, agent_id: str, error_info: Dict = None) -> bool:
        """
        Mark a task as failed and potentially retry.
        
        Args:
            task_id: Task ID
            agent_id: Agent ID
            error_info: Error information
            
        Returns:
            True if successful
        """
        try:
            error_info = error_info or {}
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Get current retry count
                    cursor = conn.execute("""
                        SELECT retry_count, max_retries FROM tasks WHERE task_id = ?
                    """, (task_id,))
                    
                    result = cursor.fetchone()
                    if not result:
                        return False
                        
                    retry_count, max_retries = result
                    new_retry_count = retry_count + 1
                    
                    if new_retry_count <= max_retries:
                        # Reset for retry
                        conn.execute("""
                            UPDATE tasks 
                            SET status = ?, assigned_agent = NULL, assigned_at = NULL,
                                started_at = NULL, retry_count = ?
                            WHERE task_id = ?
                        """, (TaskStatus.PENDING.value, new_retry_count, task_id))
                        
                        logger.info(f"Task {task_id} failed, retrying ({new_retry_count}/{max_retries})")
                    else:
                        # Max retries reached, mark as failed
                        conn.execute("""
                            UPDATE tasks 
                            SET status = ?, completed_at = CURRENT_TIMESTAMP
                            WHERE task_id = ?
                        """, (TaskStatus.FAILED.value, task_id))
                        
                        logger.warning(f"Task {task_id} failed permanently after {max_retries} retries")
                    
                    # Log failure
                    self._log_event(conn, task_id, agent_id, "failed", error_info)
                    
            return True
            
        except Exception as e:
            logger.error(f"Failed to fail task {task_id}: {e}")
            return False
            
    def cancel_task(self, task_id: str, reason: str = "") -> bool:
        """
        Cancel a task.
        
        Args:
            task_id: Task ID
            reason: Cancellation reason
            
        Returns:
            True if successful
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        UPDATE tasks 
                        SET status = ?, completed_at = CURRENT_TIMESTAMP
                        WHERE task_id = ?
                    """, (TaskStatus.CANCELLED.value, task_id))
                    
                    # Log cancellation
                    self._log_event(conn, task_id, None, "cancelled", {"reason": reason})
                    
            logger.info(f"Task {task_id} cancelled: {reason}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to cancel task {task_id}: {e}")
            return False
            
    def _log_event(self, conn, task_id: str, agent_id: Optional[str], 
                  event_type: str, event_data: Dict):
        """Log a task event."""
        conn.execute("""
            INSERT INTO task_execution_log (task_id, agent_id, event_type, event_data)
            VALUES (?, ?, ?, ?)
        """, (task_id, agent_id, event_type, json.dumps(event_data)))
        
    def get_task_log(self, task_id: str) -> List[Dict]:
        """
        Get execution log for a task.
        
        Args:
            task_id: Task ID
            
        Returns:
            List of log entries
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT agent_id, event_type, event_data, timestamp
                        FROM task_execution_log 
                        WHERE task_id = ?
                        ORDER BY timestamp
                    """, (task_id,))
                    
                    return [
                        {
                            "agent_id": row[0],
                            "event_type": row[1],
                            "event_data": json.loads(row[2]) if row[2] else {},
                            "timestamp": row[3]
                        }
                        for row in cursor.fetchall()
                    ]
                    
        except Exception as e:
            logger.error(f"Failed to get task log for {task_id}: {e}")
            return []
            
    def cleanup_old_tasks(self, days: int = 30) -> int:
        """
        Clean up old completed/failed/cancelled tasks.
        
        Args:
            days: Number of days to keep tasks
            
        Returns:
            Number of tasks removed
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=days)
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Get task IDs to delete
                    cursor = conn.execute("""
                        SELECT task_id FROM tasks 
                        WHERE status IN ('completed', 'failed', 'cancelled')
                        AND completed_at < ?
                    """, (cutoff_date,))
                    
                    task_ids = [row[0] for row in cursor.fetchall()]
                    
                    if task_ids:
                        # Delete logs first
                        conn.execute("""
                            DELETE FROM task_execution_log 
                            WHERE task_id IN ({})
                        """.format(",".join("?" * len(task_ids))), task_ids)
                        
                        # Delete dependencies
                        conn.execute("""
                            DELETE FROM task_dependencies 
                            WHERE task_id IN ({}) OR depends_on_task_id IN ({})
                        """.format(",".join("?" * len(task_ids)), ",".join("?" * len(task_ids))), 
                        task_ids + task_ids)
                        
                        # Delete tasks
                        cursor = conn.execute("""
                            DELETE FROM tasks 
                            WHERE task_id IN ({})
                        """.format(",".join("?" * len(task_ids))), task_ids)
                        
                        count = cursor.rowcount
                        logger.info(f"Cleaned up {count} old tasks")
                        return count
                        
            return 0
            
        except Exception as e:
            logger.error(f"Failed to cleanup old tasks: {e}")
            return 0
            
    def get_stats(self) -> Dict[str, Any]:
        """Get task manager statistics."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    stats = {}
                    
                    # Total tasks
                    cursor = conn.execute("SELECT COUNT(*) FROM tasks")
                    stats["total_tasks"] = cursor.fetchone()[0]
                    
                    # Tasks by status
                    cursor = conn.execute("""
                        SELECT status, COUNT(*) FROM tasks GROUP BY status
                    """)
                    stats["by_status"] = dict(cursor.fetchall())
                    
                    # Tasks by priority
                    cursor = conn.execute("""
                        SELECT priority, COUNT(*) FROM tasks GROUP BY priority
                    """)
                    priority_map = {1: "low", 2: "normal", 3: "high", 4: "urgent"}
                    stats["by_priority"] = {
                        priority_map.get(k, k): v for k, v in cursor.fetchall()
                    }
                    
                    # Active assignments
                    cursor = conn.execute("""
                        SELECT assigned_agent, COUNT(*) FROM tasks 
                        WHERE status IN ('assigned', 'in_progress')
                        GROUP BY assigned_agent
                    """)
                    stats["active_assignments"] = dict(cursor.fetchall())
                    
                    return stats
                    
        except Exception as e:
            logger.error(f"Failed to get task stats: {e}")
            return {}