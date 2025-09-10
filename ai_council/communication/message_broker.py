"""
Message Broker for AI Council Workspace

Enables real-time communication between agents with message queuing,
routing, and persistence to support continuous collaboration.
"""

import sqlite3
import json
import threading
import time
import uuid
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Callable
from pathlib import Path
from enum import Enum
import logging
import asyncio
import websockets
from collections import defaultdict

logger = logging.getLogger(__name__)

class MessageType(Enum):
    """Message type enumeration."""
    DIRECT = "direct"           # Direct agent-to-agent message
    BROADCAST = "broadcast"     # Message to all agents
    TASK_UPDATE = "task_update" # Task-related update
    STATUS = "status"          # Status update
    REQUEST = "request"        # Request for information/action
    RESPONSE = "response"      # Response to a request
    NOTIFICATION = "notification" # General notification

class MessageBroker:
    """
    Message broker for inter-agent communication.
    
    Features:
    - Message queuing and routing
    - Persistent message storage
    - WebSocket support for real-time messaging
    - Message filtering and subscription
    - Delivery confirmation and retry
    - Message history and search
    """
    
    def __init__(self, db_path: str = "message_broker.db", 
                 retention_days: int = 7, websocket_port: int = 8765):
        """
        Initialize message broker.
        
        Args:
            db_path: Path to SQLite database
            retention_days: Days to retain messages
            websocket_port: Port for WebSocket server
        """
        self.db_path = Path(db_path)
        self.retention_days = retention_days
        self.websocket_port = websocket_port
        
        self._lock = threading.RLock()
        self._subscribers = defaultdict(list)  # agent_id -> list of callback functions
        self._websocket_clients = {}  # agent_id -> websocket connection
        self._message_handlers = {}  # message_type -> handler function
        
        self._running = False
        self._websocket_server = None
        self._cleanup_thread = None
        
        self._init_database()
        
    def _init_database(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS messages (
                    message_id TEXT PRIMARY KEY,
                    sender_id TEXT NOT NULL,
                    recipient_id TEXT,  -- NULL for broadcast
                    message_type TEXT NOT NULL,
                    subject TEXT,
                    content TEXT NOT NULL,  -- JSON content
                    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME,
                    delivered BOOLEAN DEFAULT FALSE,
                    delivered_at DATETIME,
                    metadata TEXT  -- JSON metadata
                )
            """)
            
            conn.execute("""
                CREATE TABLE IF NOT EXISTS message_delivery (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    message_id TEXT NOT NULL,
                    recipient_id TEXT NOT NULL,
                    delivered_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                    delivery_method TEXT,
                    FOREIGN KEY (message_id) REFERENCES messages (message_id)
                )
            """)
            
            # Indexes
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_recipient ON messages(recipient_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_sender ON messages(sender_id)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_type ON messages(message_type)
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_messages_created ON messages(created_at)
            """)
            
    async def start_websocket_server(self):
        """Start WebSocket server for real-time messaging."""
        try:
            logger.info(f"Starting WebSocket server on port {self.websocket_port}")
            
            async def handle_client(websocket, path):
                try:
                    # Extract agent ID from path or initial message
                    agent_id = await self._authenticate_websocket_client(websocket)
                    if agent_id:
                        self._websocket_clients[agent_id] = websocket
                        logger.info(f"WebSocket client connected: {agent_id}")
                        
                        try:
                            async for message in websocket:
                                await self._handle_websocket_message(agent_id, message)
                        except websockets.exceptions.ConnectionClosed:
                            pass
                        finally:
                            if agent_id in self._websocket_clients:
                                del self._websocket_clients[agent_id]
                            logger.info(f"WebSocket client disconnected: {agent_id}")
                            
                except Exception as e:
                    logger.error(f"WebSocket client error: {e}")
                    
            self._websocket_server = await websockets.serve(
                handle_client, "localhost", self.websocket_port
            )
            
        except Exception as e:
            logger.error(f"Failed to start WebSocket server: {e}")
            
    async def _authenticate_websocket_client(self, websocket) -> Optional[str]:
        """Authenticate WebSocket client and return agent ID."""
        try:
            # Wait for authentication message
            auth_message = await asyncio.wait_for(websocket.recv(), timeout=10.0)
            auth_data = json.loads(auth_message)
            
            if auth_data.get("type") == "auth":
                agent_id = auth_data.get("agent_id")
                # TODO: Add proper authentication here
                await websocket.send(json.dumps({
                    "type": "auth_response",
                    "success": True,
                    "agent_id": agent_id
                }))
                return agent_id
                
        except Exception as e:
            logger.error(f"WebSocket authentication failed: {e}")
            await websocket.send(json.dumps({
                "type": "auth_response", 
                "success": False,
                "error": str(e)
            }))
            
        return None
        
    async def _handle_websocket_message(self, sender_id: str, message: str):
        """Handle incoming WebSocket message."""
        try:
            data = json.loads(message)
            
            if data.get("type") == "send_message":
                # Send message through broker
                await asyncio.to_thread(
                    self.send_message,
                    sender_id=sender_id,
                    recipient_id=data.get("recipient_id"),
                    message_type=MessageType(data.get("message_type", "direct")),
                    subject=data.get("subject"),
                    content=data.get("content"),
                    metadata=data.get("metadata")
                )
                
        except Exception as e:
            logger.error(f"Error handling WebSocket message from {sender_id}: {e}")
            
    def send_message(self, sender_id: str, recipient_id: Optional[str],
                    message_type: MessageType, subject: str = "", 
                    content: Any = None, expires_in: Optional[int] = None,
                    metadata: Dict = None) -> Optional[str]:
        """
        Send a message through the broker.
        
        Args:
            sender_id: ID of sender agent
            recipient_id: ID of recipient agent (None for broadcast)
            message_type: Type of message
            subject: Message subject/title
            content: Message content (will be JSON serialized)
            expires_in: Optional expiration time in seconds
            metadata: Additional metadata
            
        Returns:
            Message ID if successful
        """
        try:
            message_id = str(uuid.uuid4())
            content = content or {}
            metadata = metadata or {}
            
            expires_at = None
            if expires_in:
                expires_at = datetime.now() + timedelta(seconds=expires_in)
                
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT INTO messages (
                            message_id, sender_id, recipient_id, message_type,
                            subject, content, expires_at, metadata
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        message_id, sender_id, recipient_id, message_type.value,
                        subject, json.dumps(content), expires_at, json.dumps(metadata)
                    ))
                    
            # Deliver message immediately
            asyncio.create_task(self._deliver_message(message_id))
            
            logger.debug(f"Message sent: {message_id} from {sender_id} to {recipient_id}")
            return message_id
            
        except Exception as e:
            logger.error(f"Failed to send message: {e}")
            return None
            
    async def _deliver_message(self, message_id: str):
        """Deliver a message to recipient(s)."""
        try:
            message = self.get_message(message_id)
            if not message:
                return
                
            if message["recipient_id"]:
                # Direct message
                await self._deliver_to_agent(message, message["recipient_id"])
            else:
                # Broadcast message
                for agent_id in self._websocket_clients.keys():
                    if agent_id != message["sender_id"]:  # Don't send to sender
                        await self._deliver_to_agent(message, agent_id)
                        
        except Exception as e:
            logger.error(f"Failed to deliver message {message_id}: {e}")
            
    async def _deliver_to_agent(self, message: Dict, recipient_id: str):
        """Deliver message to a specific agent."""
        try:
            # Try WebSocket delivery first
            if recipient_id in self._websocket_clients:
                websocket = self._websocket_clients[recipient_id]
                delivery_data = {
                    "type": "new_message",
                    "message": message
                }
                
                try:
                    await websocket.send(json.dumps(delivery_data))
                    self._record_delivery(message["message_id"], recipient_id, "websocket")
                    logger.debug(f"Delivered message {message['message_id']} to {recipient_id} via WebSocket")
                    return
                except websockets.exceptions.ConnectionClosed:
                    # Remove closed connection
                    del self._websocket_clients[recipient_id]
                    
            # Try callback delivery
            if recipient_id in self._subscribers:
                for callback in self._subscribers[recipient_id]:
                    try:
                        callback(message)
                        self._record_delivery(message["message_id"], recipient_id, "callback")
                        logger.debug(f"Delivered message {message['message_id']} to {recipient_id} via callback")
                        return
                    except Exception as e:
                        logger.error(f"Callback delivery failed for {recipient_id}: {e}")
                        
            # If no real-time delivery, message stays in queue for polling
            logger.debug(f"Message {message['message_id']} queued for {recipient_id}")
            
        except Exception as e:
            logger.error(f"Failed to deliver message to {recipient_id}: {e}")
            
    def _record_delivery(self, message_id: str, recipient_id: str, method: str):
        """Record successful message delivery."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT INTO message_delivery (message_id, recipient_id, delivery_method)
                        VALUES (?, ?, ?)
                    """, (message_id, recipient_id, method))
                    
                    # Mark message as delivered if this is the primary recipient
                    conn.execute("""
                        UPDATE messages SET delivered = TRUE, delivered_at = CURRENT_TIMESTAMP
                        WHERE message_id = ? AND (recipient_id = ? OR recipient_id IS NULL)
                    """, (message_id, recipient_id))
                    
        except Exception as e:
            logger.error(f"Failed to record delivery: {e}")
            
    def subscribe(self, agent_id: str, callback: Callable[[Dict], None]):
        """
        Subscribe an agent to receive messages via callback.
        
        Args:
            agent_id: Agent ID
            callback: Function to call when message is received
        """
        with self._lock:
            self._subscribers[agent_id].append(callback)
            logger.debug(f"Agent {agent_id} subscribed to messages")
            
    def unsubscribe(self, agent_id: str, callback: Optional[Callable] = None):
        """
        Unsubscribe an agent from messages.
        
        Args:
            agent_id: Agent ID
            callback: Specific callback to remove (None to remove all)
        """
        with self._lock:
            if agent_id in self._subscribers:
                if callback:
                    try:
                        self._subscribers[agent_id].remove(callback)
                    except ValueError:
                        pass
                else:
                    self._subscribers[agent_id].clear()
                    
    def get_messages(self, agent_id: str, message_type: Optional[MessageType] = None,
                    unread_only: bool = True, limit: int = 50) -> List[Dict]:
        """
        Get messages for an agent.
        
        Args:
            agent_id: Agent ID
            message_type: Optional message type filter
            unread_only: Whether to only return unread messages
            limit: Maximum number of messages
            
        Returns:
            List of messages
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    query = """
                        SELECT message_id, sender_id, recipient_id, message_type,
                               subject, content, created_at, metadata
                        FROM messages
                        WHERE (recipient_id = ? OR recipient_id IS NULL)
                        AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                    """
                    params = [agent_id]
                    
                    if message_type:
                        query += " AND message_type = ?"
                        params.append(message_type.value)
                        
                    if unread_only:
                        query += """ AND message_id NOT IN (
                            SELECT message_id FROM message_delivery 
                            WHERE recipient_id = ?
                        )"""
                        params.append(agent_id)
                        
                    query += " ORDER BY created_at DESC LIMIT ?"
                    params.append(limit)
                    
                    cursor = conn.execute(query, params)
                    messages = []
                    
                    for row in cursor.fetchall():
                        message = {
                            "message_id": row[0],
                            "sender_id": row[1],
                            "recipient_id": row[2],
                            "message_type": row[3],
                            "subject": row[4],
                            "content": json.loads(row[5]) if row[5] else {},
                            "created_at": row[6],
                            "metadata": json.loads(row[7]) if row[7] else {}
                        }
                        messages.append(message)
                        
                    return messages
                    
        except Exception as e:
            logger.error(f"Failed to get messages for {agent_id}: {e}")
            return []
            
    def get_message(self, message_id: str) -> Optional[Dict]:
        """Get a specific message by ID."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT message_id, sender_id, recipient_id, message_type,
                               subject, content, created_at, delivered, delivered_at, metadata
                        FROM messages WHERE message_id = ?
                    """, (message_id,))
                    
                    row = cursor.fetchone()
                    if row:
                        return {
                            "message_id": row[0],
                            "sender_id": row[1],
                            "recipient_id": row[2],
                            "message_type": row[3],
                            "subject": row[4],
                            "content": json.loads(row[5]) if row[5] else {},
                            "created_at": row[6],
                            "delivered": bool(row[7]),
                            "delivered_at": row[8],
                            "metadata": json.loads(row[9]) if row[9] else {}
                        }
                    return None
                    
        except Exception as e:
            logger.error(f"Failed to get message {message_id}: {e}")
            return None
            
    def mark_as_read(self, message_id: str, agent_id: str) -> bool:
        """
        Mark a message as read by an agent.
        
        Args:
            message_id: Message ID
            agent_id: Agent ID
            
        Returns:
            True if successful
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute("""
                        INSERT OR IGNORE INTO message_delivery 
                        (message_id, recipient_id, delivery_method)
                        VALUES (?, ?, 'manual')
                    """, (message_id, agent_id))
                    
            return True
            
        except Exception as e:
            logger.error(f"Failed to mark message {message_id} as read: {e}")
            return False
            
    def cleanup_old_messages(self) -> int:
        """
        Clean up old messages based on retention policy.
        
        Returns:
            Number of messages deleted
        """
        try:
            cutoff_date = datetime.now() - timedelta(days=self.retention_days)
            
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Delete old message deliveries first
                    conn.execute("""
                        DELETE FROM message_delivery 
                        WHERE message_id IN (
                            SELECT message_id FROM messages 
                            WHERE created_at < ?
                        )
                    """, (cutoff_date,))
                    
                    # Delete old messages
                    cursor = conn.execute("""
                        DELETE FROM messages WHERE created_at < ?
                    """, (cutoff_date,))
                    
                    count = cursor.rowcount
                    logger.info(f"Cleaned up {count} old messages")
                    return count
                    
        except Exception as e:
            logger.error(f"Failed to cleanup old messages: {e}")
            return 0
            
    def get_stats(self) -> Dict[str, Any]:
        """Get message broker statistics."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    stats = {}
                    
                    # Total messages
                    cursor = conn.execute("SELECT COUNT(*) FROM messages")
                    stats["total_messages"] = cursor.fetchone()[0]
                    
                    # Messages by type
                    cursor = conn.execute("""
                        SELECT message_type, COUNT(*) FROM messages GROUP BY message_type
                    """)
                    stats["by_type"] = dict(cursor.fetchall())
                    
                    # Recent activity (last 24 hours)
                    cursor = conn.execute("""
                        SELECT COUNT(*) FROM messages 
                        WHERE created_at > datetime('now', '-1 day')
                    """)
                    stats["messages_24h"] = cursor.fetchone()[0]
                    
                    # Connected WebSocket clients
                    stats["websocket_clients"] = len(self._websocket_clients)
                    
                    # Subscribed agents
                    stats["subscribed_agents"] = len([
                        agent_id for agent_id, callbacks in self._subscribers.items()
                        if callbacks
                    ])
                    
                    return stats
                    
        except Exception as e:
            logger.error(f"Failed to get message broker stats: {e}")
            return {}