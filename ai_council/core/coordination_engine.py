"""
Coordination Engine for AI Council Workspace

Orchestrates collaboration between agents, manages task assignment,
and ensures continuous operation even when agents are offline.
"""

import asyncio
import threading
import time
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta

from .shared_memory import SharedMemory
from .agent_registry import AgentRegistry, AgentStatus
from .task_manager import TaskManager, TaskStatus, TaskPriority

logger = logging.getLogger(__name__)

class CoordinationEngine:
    """
    Central coordination engine for the AI Council Workspace.
    
    Features:
    - Automatic task assignment based on agent capabilities
    - Agent health monitoring and offline detection
    - Task redistribution on agent failure
    - Continuous operation coordination
    - Progress tracking and reporting
    """
    
    def __init__(self, 
                 shared_memory: Optional[SharedMemory] = None,
                 agent_registry: Optional[AgentRegistry] = None,
                 task_manager: Optional[TaskManager] = None,
                 assignment_interval: int = 30,
                 cleanup_interval: int = 3600):
        """
        Initialize coordination engine.
        
        Args:
            shared_memory: Shared memory instance (creates new if None)
            agent_registry: Agent registry instance (creates new if None)  
            task_manager: Task manager instance (creates new if None)
            assignment_interval: Task assignment check interval (seconds)
            cleanup_interval: Cleanup operations interval (seconds)
        """
        self.shared_memory = shared_memory or SharedMemory()
        self.agent_registry = agent_registry or AgentRegistry()
        self.task_manager = task_manager or TaskManager()
        
        self.assignment_interval = assignment_interval
        self.cleanup_interval = cleanup_interval
        
        self._running = False
        self._assignment_thread = None
        self._cleanup_thread = None
        self._lock = threading.RLock()
        
        # Coordination state
        self._last_assignment = datetime.now()
        self._last_cleanup = datetime.now()
        self._assignment_stats = {
            "total_assignments": 0,
            "successful_assignments": 0,
            "failed_assignments": 0
        }
        
    def start(self):
        """Start the coordination engine."""
        with self._lock:
            if self._running:
                logger.warning("Coordination engine already running")
                return
                
            self._running = True
            logger.info("Starting coordination engine")
            
            # Start background threads
            self._assignment_thread = threading.Thread(
                target=self._assignment_loop, daemon=True
            )
            self._cleanup_thread = threading.Thread(
                target=self._cleanup_loop, daemon=True
            )
            
            self._assignment_thread.start()
            self._cleanup_thread.start()
            
            # Record start in shared memory
            self.shared_memory.set(
                "coordination_engine_status", 
                {"status": "running", "started_at": datetime.now().isoformat()},
                "coordination_engine"
            )
            
    def stop(self):
        """Stop the coordination engine."""
        with self._lock:
            if not self._running:
                return
                
            logger.info("Stopping coordination engine")
            self._running = False
            
            # Wait for threads to finish
            if self._assignment_thread:
                self._assignment_thread.join(timeout=5)
            if self._cleanup_thread:
                self._cleanup_thread.join(timeout=5)
                
            # Record stop in shared memory
            self.shared_memory.set(
                "coordination_engine_status",
                {"status": "stopped", "stopped_at": datetime.now().isoformat()},
                "coordination_engine"
            )
            
    def create_task(self, title: str, description: str = "", task_type: str = "general",
                   required_capabilities: List[str] = None, input_data: Dict = None,
                   priority: TaskPriority = TaskPriority.NORMAL, 
                   deadline: Optional[datetime] = None,
                   dependencies: List[str] = None, metadata: Dict = None,
                   auto_assign: bool = True) -> Optional[str]:
        """
        Create a new task and optionally auto-assign it.
        
        Args:
            title: Task title
            description: Task description  
            task_type: Task type/category
            required_capabilities: Required agent capabilities
            input_data: Task input data
            priority: Task priority
            deadline: Optional deadline
            dependencies: Task dependencies
            metadata: Additional metadata
            auto_assign: Whether to automatically try to assign the task
            
        Returns:
            Task ID if created successfully
        """
        task_id = self.task_manager.create_task(
            title=title,
            description=description,
            task_type=task_type,
            required_capabilities=required_capabilities,
            input_data=input_data,
            priority=priority,
            created_by="coordination_engine",
            deadline=deadline,
            dependencies=dependencies,
            metadata=metadata
        )
        
        if task_id and auto_assign:
            # Try immediate assignment
            self._try_assign_task(task_id)
            
        return task_id
        
    def register_agent(self, agent_id: str, name: str, description: str = "",
                      capabilities: List[str] = None, metadata: Dict = None) -> bool:
        """
        Register an agent with the coordination engine.
        
        Args:
            agent_id: Unique agent identifier
            name: Agent name
            description: Agent description
            capabilities: Agent capabilities
            metadata: Additional metadata
            
        Returns:
            True if successful
        """
        success = self.agent_registry.register_agent(
            agent_id, name, description, capabilities, metadata
        )
        
        if success:
            logger.info(f"Agent registered: {agent_id} ({name})")
            
            # Record in shared memory
            self.shared_memory.set(
                f"agent_{agent_id}_registration",
                {
                    "name": name,
                    "capabilities": capabilities or [],
                    "registered_at": datetime.now().isoformat()
                },
                "coordination_engine",
                namespace="agents"
            )
            
            # Try to assign tasks to the new agent
            self._assign_tasks_to_agent(agent_id)
            
        return success
        
    def agent_heartbeat(self, agent_id: str, status: AgentStatus = AgentStatus.ONLINE,
                       metadata: Dict = None) -> bool:
        """
        Process agent heartbeat.
        
        Args:
            agent_id: Agent ID
            status: Agent status
            metadata: Optional status metadata
            
        Returns:
            True if successful
        """
        return self.agent_registry.heartbeat(agent_id, status, metadata)
        
    def get_agent_tasks(self, agent_id: str) -> List[Dict]:
        """
        Get tasks assigned to a specific agent.
        
        Args:
            agent_id: Agent ID
            
        Returns:
            List of assigned tasks
        """
        return self.task_manager.list_tasks(assigned_agent=agent_id)
        
    def complete_task(self, task_id: str, agent_id: str, output_data: Dict = None) -> bool:
        """
        Mark a task as completed by an agent.
        
        Args:
            task_id: Task ID
            agent_id: Agent ID
            output_data: Task results
            
        Returns:
            True if successful
        """
        success = self.task_manager.complete_task(task_id, agent_id, output_data)
        
        if success:
            # Update assignment stats
            self._assignment_stats["successful_assignments"] += 1
            
            # Store results in shared memory
            self.shared_memory.set(
                f"task_{task_id}_result",
                {
                    "completed_by": agent_id,
                    "completed_at": datetime.now().isoformat(),
                    "output_data": output_data or {}
                },
                agent_id,
                namespace="task_results"
            )
            
        return success
        
    def fail_task(self, task_id: str, agent_id: str, error_info: Dict = None) -> bool:
        """
        Mark a task as failed and handle retry logic.
        
        Args:
            task_id: Task ID
            agent_id: Agent ID  
            error_info: Error information
            
        Returns:
            True if successful
        """
        success = self.task_manager.fail_task(task_id, agent_id, error_info)
        
        if success:
            self._assignment_stats["failed_assignments"] += 1
            
            # Store failure info in shared memory
            self.shared_memory.set(
                f"task_{task_id}_failure",
                {
                    "failed_by": agent_id,
                    "failed_at": datetime.now().isoformat(),
                    "error_info": error_info or {}
                },
                agent_id,
                namespace="task_failures"
            )
            
        return success
        
    def _assignment_loop(self):
        """Main task assignment loop."""
        logger.info("Task assignment loop started")
        
        while self._running:
            try:
                self._assign_pending_tasks()
                self._check_stalled_tasks()
                self._update_assignment_stats()
                
                time.sleep(self.assignment_interval)
                
            except Exception as e:
                logger.error(f"Error in assignment loop: {e}")
                time.sleep(min(self.assignment_interval, 60))
                
        logger.info("Task assignment loop stopped")
        
    def _cleanup_loop(self):
        """Main cleanup loop."""
        logger.info("Cleanup loop started")
        
        while self._running:
            try:
                self._cleanup_operations()
                time.sleep(self.cleanup_interval)
                
            except Exception as e:
                logger.error(f"Error in cleanup loop: {e}")
                time.sleep(min(self.cleanup_interval, 300))
                
        logger.info("Cleanup loop stopped")
        
    def _assign_pending_tasks(self):
        """Assign pending tasks to available agents."""
        # Get online agents
        online_agents = self.agent_registry.list_agents(status=AgentStatus.ONLINE)
        if not online_agents:
            return
            
        # Get pending tasks
        pending_tasks = self.task_manager.list_tasks(status=TaskStatus.PENDING)
        if not pending_tasks:
            return
            
        logger.debug(f"Attempting to assign {len(pending_tasks)} tasks to {len(online_agents)} agents")
        
        for task in pending_tasks:
            assigned = self._try_assign_task(task["task_id"])
            if assigned:
                logger.info(f"Assigned task {task['task_id']} ({task['title']})")
                
    def _try_assign_task(self, task_id: str) -> bool:
        """
        Try to assign a specific task to an available agent.
        
        Args:
            task_id: Task to assign
            
        Returns:
            True if assignment was successful
        """
        task = self.task_manager.get_task(task_id)
        if not task or task["status"] != TaskStatus.PENDING.value:
            return False
            
        # Find capable agents
        required_caps = task["required_capabilities"]
        capable_agents = self.agent_registry.find_capable_agents(
            required_caps, AgentStatus.ONLINE
        )
        
        if not capable_agents:
            logger.debug(f"No capable agents for task {task_id} (requires: {required_caps})")
            return False
            
        # Select best agent (for now, just pick the first available)
        # TODO: Implement more sophisticated assignment algorithm
        selected_agent = capable_agents[0]
        
        # Assign task
        success = self.task_manager.assign_task(task_id, selected_agent["agent_id"])
        if success:
            # Also record in agent registry
            self.agent_registry.assign_task(selected_agent["agent_id"], task_id)
            
        return success
        
    def _assign_tasks_to_agent(self, agent_id: str):
        """Try to assign available tasks to a specific agent."""
        agent = self.agent_registry.get_agent(agent_id)
        if not agent or agent["status"] != AgentStatus.ONLINE.value:
            return
            
        available_tasks = self.task_manager.get_available_tasks(agent["capabilities"])
        
        for task in available_tasks[:5]:  # Limit to 5 tasks at once
            success = self.task_manager.assign_task(task["task_id"], agent_id)
            if success:
                self.agent_registry.assign_task(agent_id, task["task_id"])
                logger.info(f"Assigned task {task['task_id']} to new agent {agent_id}")
                
    def _check_stalled_tasks(self):
        """Check for tasks that may be stalled and need reassignment."""
        # Get tasks assigned but not started for more than 10 minutes
        assigned_tasks = self.task_manager.list_tasks(status=TaskStatus.ASSIGNED)
        stalled_threshold = datetime.now() - timedelta(minutes=10)
        
        for task in assigned_tasks:
            assigned_at = task["assigned_at"]
            if assigned_at:
                # Parse datetime string if needed
                if isinstance(assigned_at, str):
                    try:
                        assigned_at = datetime.fromisoformat(assigned_at.replace('Z', '+00:00'))
                    except (ValueError, AttributeError):
                        continue
                        
                if assigned_at < stalled_threshold:
                    agent_id = task["assigned_agent"]
                
                # Check if agent is still online
                agent = self.agent_registry.get_agent(agent_id)
                if not agent or agent["status"] != AgentStatus.ONLINE.value:
                    logger.warning(f"Reassigning stalled task {task['task_id']} from offline agent {agent_id}")
                    
                    # Reset task to pending
                    self.task_manager.fail_task(
                        task["task_id"], 
                        agent_id, 
                        {"reason": "agent_offline", "auto_reassign": True}
                    )
                    
    def _update_assignment_stats(self):
        """Update assignment statistics in shared memory."""
        self._last_assignment = datetime.now()
        
        stats = {
            "last_assignment_check": self._last_assignment.isoformat(),
            "assignment_stats": self._assignment_stats.copy(),
            "pending_tasks": len(self.task_manager.list_tasks(status=TaskStatus.PENDING)),
            "online_agents": len(self.agent_registry.list_agents(status=AgentStatus.ONLINE))
        }
        
        self.shared_memory.set(
            "coordination_stats",
            stats,
            "coordination_engine"
        )
        
    def _cleanup_operations(self):
        """Perform periodic cleanup operations."""
        logger.debug("Running cleanup operations")
        
        # Update offline agents
        offline_count = self.agent_registry.update_offline_agents()
        
        # Cleanup expired shared memory entries
        expired_count = self.shared_memory.cleanup_expired()
        
        # Cleanup old task versions in shared memory
        old_versions_count = self.shared_memory.cleanup_old_versions()
        
        # Cleanup old completed tasks (older than 30 days)
        old_tasks_count = self.task_manager.cleanup_old_tasks(30)
        
        self._last_cleanup = datetime.now()
        
        cleanup_stats = {
            "last_cleanup": self._last_cleanup.isoformat(),
            "offline_agents": offline_count,
            "expired_entries": expired_count,
            "old_versions": old_versions_count,
            "old_tasks": old_tasks_count
        }
        
        self.shared_memory.set(
            "cleanup_stats",
            cleanup_stats,
            "coordination_engine"
        )
        
        if any(cleanup_stats.values()):
            logger.info(f"Cleanup completed: {cleanup_stats}")
            
    def get_status(self) -> Dict[str, Any]:
        """Get current coordination engine status."""
        return {
            "running": self._running,
            "last_assignment": self._last_assignment.isoformat() if self._last_assignment else None,
            "last_cleanup": self._last_cleanup.isoformat() if self._last_cleanup else None,
            "assignment_stats": self._assignment_stats.copy(),
            "agent_stats": self.agent_registry.get_stats(),
            "task_stats": self.task_manager.get_stats(),
            "memory_stats": self.shared_memory.get_stats()
        }
        
    def get_system_health(self) -> Dict[str, Any]:
        """Get overall system health status."""
        agent_stats = self.agent_registry.get_stats()
        task_stats = self.task_manager.get_stats()
        
        total_agents = agent_stats.get("total_agents", 0)
        online_agents = agent_stats.get("recently_active", 0)
        
        pending_tasks = task_stats.get("by_status", {}).get("pending", 0)
        failed_tasks = task_stats.get("by_status", {}).get("failed", 0)
        
        health_score = 100
        issues = []
        
        # Check agent availability
        if total_agents == 0:
            health_score -= 50
            issues.append("No agents registered")
        elif online_agents == 0:
            health_score -= 40
            issues.append("No agents online")
        elif online_agents / total_agents < 0.5:
            health_score -= 20
            issues.append("Less than 50% of agents online")
            
        # Check task backlog
        if pending_tasks > 100:
            health_score -= 20
            issues.append("Large task backlog")
        elif pending_tasks > 50:
            health_score -= 10
            issues.append("Moderate task backlog")
            
        # Check failure rate
        total_completed = task_stats.get("by_status", {}).get("completed", 0)
        if total_completed > 0:
            failure_rate = failed_tasks / (total_completed + failed_tasks)
            if failure_rate > 0.2:
                health_score -= 15
                issues.append("High task failure rate")
            elif failure_rate > 0.1:
                health_score -= 5
                issues.append("Moderate task failure rate")
                
        health_status = "healthy"
        if health_score < 50:
            health_status = "critical"
        elif health_score < 70:
            health_status = "warning"
        elif health_score < 90:
            health_status = "degraded"
            
        return {
            "health_score": max(0, health_score),
            "health_status": health_status,
            "issues": issues,
            "system_stats": {
                "total_agents": total_agents,
                "online_agents": online_agents,
                "pending_tasks": pending_tasks,
                "total_tasks": task_stats.get("total_tasks", 0)
            },
            "last_updated": datetime.now().isoformat()
        }