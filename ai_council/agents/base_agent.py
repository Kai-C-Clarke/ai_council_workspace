"""
Base Agent Implementation for AI Council Workspace

Provides a foundation for building AI agents that can participate
in the collaborative workspace ecosystem.
"""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Any, Callable
from datetime import datetime, timedelta

from ..core.coordination_engine import CoordinationEngine
from ..core.agent_registry import AgentStatus
from ..communication.message_broker import MessageBroker, MessageType

logger = logging.getLogger(__name__)

class BaseAgent(ABC):
    """
    Base class for AI Council agents.
    
    Provides common functionality for:
    - Agent registration and lifecycle
    - Task execution framework
    - Message handling
    - Heartbeat and status management
    - Error handling and recovery
    """
    
    def __init__(self, agent_id: str, name: str, description: str = "",
                 capabilities: List[str] = None, 
                 coordination_engine: Optional[CoordinationEngine] = None,
                 message_broker: Optional[MessageBroker] = None,
                 heartbeat_interval: int = 60):
        """
        Initialize base agent.
        
        Args:
            agent_id: Unique identifier for the agent
            name: Human-readable name
            description: Agent description
            capabilities: List of agent capabilities/skills
            coordination_engine: Coordination engine instance
            message_broker: Message broker instance
            heartbeat_interval: Heartbeat interval in seconds
        """
        self.agent_id = agent_id
        self.name = name
        self.description = description
        self.capabilities = capabilities or []
        self.coordination_engine = coordination_engine
        self.message_broker = message_broker
        self.heartbeat_interval = heartbeat_interval
        
        # Agent state
        self._status = AgentStatus.OFFLINE
        self._running = False
        self._current_task = None
        self._metadata = {}
        
        # Background tasks
        self._heartbeat_task = None
        self._task_polling_task = None
        self._message_handling_task = None
        
        # Message handlers
        self._message_handlers = {}
        
    async def start(self):
        """Start the agent and register with the workspace."""
        logger.info(f"Starting agent {self.agent_id} ({self.name})")
        
        if not self.coordination_engine:
            raise RuntimeError("Coordination engine not provided")
            
        try:
            # Register with coordination engine
            success = self.coordination_engine.register_agent(
                agent_id=self.agent_id,
                name=self.name,
                description=self.description,
                capabilities=self.capabilities,
                metadata=self._metadata
            )
            
            if not success:
                raise RuntimeError("Failed to register agent")
                
            # Subscribe to messages if message broker available
            if self.message_broker:
                self.message_broker.subscribe(self.agent_id, self._handle_message)
                
            # Start background tasks
            self._running = True
            self._status = AgentStatus.ONLINE
            
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            self._task_polling_task = asyncio.create_task(self._task_polling_loop())
            
            if self.message_broker:
                self._message_handling_task = asyncio.create_task(self._message_loop())
                
            # Send initial heartbeat
            await self._send_heartbeat()
            
            # Call agent-specific initialization
            await self.on_start()
            
            logger.info(f"Agent {self.agent_id} started successfully")
            
        except Exception as e:
            logger.error(f"Failed to start agent {self.agent_id}: {e}")
            await self.stop()
            raise
            
    async def stop(self):
        """Stop the agent gracefully."""
        logger.info(f"Stopping agent {self.agent_id}")
        
        self._running = False
        self._status = AgentStatus.OFFLINE
        
        # Cancel current task if any
        if self._current_task:
            await self._cancel_current_task()
            
        # Cancel background tasks
        for task in [self._heartbeat_task, self._task_polling_task, self._message_handling_task]:
            if task:
                task.cancel()
                
        # Send final heartbeat
        try:
            await self._send_heartbeat()
        except Exception as e:
            logger.error(f"Failed to send final heartbeat: {e}")
            
        # Unsubscribe from messages
        if self.message_broker:
            self.message_broker.unsubscribe(self.agent_id)
            
        # Call agent-specific cleanup
        await self.on_stop()
        
        logger.info(f"Agent {self.agent_id} stopped")
        
    async def _heartbeat_loop(self):
        """Background heartbeat loop."""
        while self._running:
            try:
                await self._send_heartbeat()
                await asyncio.sleep(self.heartbeat_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Heartbeat error: {e}")
                await asyncio.sleep(min(self.heartbeat_interval, 30))
                
    async def _send_heartbeat(self):
        """Send heartbeat to coordination engine."""
        if self.coordination_engine:
            self.coordination_engine.agent_heartbeat(
                self.agent_id, 
                self._status, 
                self._get_status_metadata()
            )
            
    def _get_status_metadata(self) -> Dict[str, Any]:
        """Get current status metadata."""
        metadata = self._metadata.copy()
        metadata.update({
            "current_task": self._current_task["task_id"] if self._current_task else None,
            "last_activity": datetime.now().isoformat(),
            "uptime": time.time() - (getattr(self, '_start_time', time.time()))
        })
        return metadata
        
    async def _task_polling_loop(self):
        """Background task polling loop."""
        while self._running:
            try:
                if self._status == AgentStatus.IDLE and not self._current_task:
                    await self._check_for_tasks()
                await asyncio.sleep(10)  # Check every 10 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Task polling error: {e}")
                await asyncio.sleep(30)
                
    async def _check_for_tasks(self):
        """Check for available tasks and claim one if possible."""
        if not self.coordination_engine:
            return
            
        # Get assigned tasks
        assigned_tasks = self.coordination_engine.get_agent_tasks(self.agent_id)
        
        # Find an assigned task that's not started
        for task in assigned_tasks:
            if task.get("status") == "assigned":
                await self._start_task(task["task_id"])
                break
                
    async def _start_task(self, task_id: str):
        """Start executing a task."""
        if self._current_task:
            logger.warning(f"Agent {self.agent_id} already has a current task")
            return
            
        task = self.coordination_engine.task_manager.get_task(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return
            
        logger.info(f"Agent {self.agent_id} starting task {task_id}")
        
        self._current_task = task
        self._status = AgentStatus.BUSY
        
        # Mark task as started in coordination engine
        self.coordination_engine.task_manager.start_task(task_id, self.agent_id)
        
        try:
            # Execute the task
            result = await self.execute_task(task)
            
            # Mark task as completed
            await self._complete_task(task_id, result)
            
        except Exception as e:
            logger.error(f"Task {task_id} failed: {e}")
            await self._fail_task(task_id, {"error": str(e), "type": type(e).__name__})
            
    async def _complete_task(self, task_id: str, result: Dict[str, Any]):
        """Complete a task successfully."""
        if self.coordination_engine:
            self.coordination_engine.complete_task(task_id, self.agent_id, result)
            
        logger.info(f"Agent {self.agent_id} completed task {task_id}")
        self._current_task = None
        self._status = AgentStatus.IDLE
        
    async def _fail_task(self, task_id: str, error_info: Dict[str, Any]):
        """Fail a task with error information."""
        if self.coordination_engine:
            self.coordination_engine.fail_task(task_id, self.agent_id, error_info)
            
        logger.error(f"Agent {self.agent_id} failed task {task_id}: {error_info}")
        self._current_task = None
        self._status = AgentStatus.IDLE
        
    async def _cancel_current_task(self):
        """Cancel the currently executing task."""
        if self._current_task:
            task_id = self._current_task["task_id"]
            logger.info(f"Cancelling current task {task_id}")
            
            await self.on_task_cancelled(self._current_task)
            await self._fail_task(task_id, {"error": "Task cancelled", "reason": "agent_shutdown"})
            
    async def _message_loop(self):
        """Background message processing loop."""
        while self._running:
            try:
                if self.message_broker:
                    messages = self.message_broker.get_messages(self.agent_id, unread_only=True, limit=10)
                    for message in messages:
                        await self._handle_message(message)
                        self.message_broker.mark_as_read(message["message_id"], self.agent_id)
                        
                await asyncio.sleep(5)  # Check every 5 seconds
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Message processing error: {e}")
                await asyncio.sleep(30)
                
    async def _handle_message(self, message: Dict[str, Any]):
        """Handle incoming message."""
        message_type = message.get("message_type")
        
        # Check for registered handlers
        if message_type in self._message_handlers:
            try:
                await self._message_handlers[message_type](message)
            except Exception as e:
                logger.error(f"Message handler error for {message_type}: {e}")
        else:
            # Default message handling
            await self.on_message_received(message)
            
    def register_message_handler(self, message_type: str, handler: Callable):
        """Register a handler for a specific message type."""
        self._message_handlers[message_type] = handler
        
    async def send_message(self, recipient_id: Optional[str], message_type: MessageType,
                          subject: str = "", content: Any = None, 
                          expires_in: Optional[int] = None) -> Optional[str]:
        """Send a message through the message broker."""
        if not self.message_broker:
            logger.warning("No message broker available for sending messages")
            return None
            
        return self.message_broker.send_message(
            sender_id=self.agent_id,
            recipient_id=recipient_id,
            message_type=message_type,
            subject=subject,
            content=content,
            expires_in=expires_in
        )
        
    # Abstract methods that subclasses must implement
    
    @abstractmethod
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """
        Execute a task and return results.
        
        Args:
            task: Task dictionary with details and input data
            
        Returns:
            Dictionary containing task results
        """
        pass
        
    # Optional override methods
    
    async def on_start(self):
        """Called when agent starts (after registration)."""
        pass
        
    async def on_stop(self):
        """Called when agent stops (before deregistration)."""
        pass
        
    async def on_message_received(self, message: Dict[str, Any]):
        """Called when a message is received (if no specific handler)."""
        logger.debug(f"Agent {self.agent_id} received message: {message['subject']}")
        
    async def on_task_cancelled(self, task: Dict[str, Any]):
        """Called when current task is cancelled."""
        logger.info(f"Task {task['task_id']} was cancelled")

class SimpleEchoAgent(BaseAgent):
    """
    Simple example agent that echoes task input as output.
    Useful for testing and demonstration purposes.
    """
    
    def __init__(self, agent_id: str = "echo_agent", **kwargs):
        super().__init__(
            agent_id=agent_id,
            name="Echo Agent",
            description="Simple agent that echoes task input",
            capabilities=["echo", "test", "general"],
            **kwargs
        )
        
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Echo the task input with some processing delay."""
        
        # Simulate some work
        await asyncio.sleep(1)
        
        input_data = task.get("input_data", {})
        
        return {
            "echoed_input": input_data,
            "task_id": task["task_id"],
            "processed_by": self.agent_id,
            "processed_at": datetime.now().isoformat(),
            "message": f"Task '{task.get('title', 'Untitled')}' processed successfully"
        }
        
    async def on_start(self):
        """Send startup message."""
        if self.message_broker:
            await self.send_message(
                recipient_id=None,  # Broadcast
                message_type=MessageType.NOTIFICATION,
                subject="Agent Started",
                content={
                    "message": f"Echo Agent {self.agent_id} is now online and ready for tasks"
                }
            )