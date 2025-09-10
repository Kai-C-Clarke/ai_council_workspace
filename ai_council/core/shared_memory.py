"""
Shared Memory System for AI Council Workspace

Provides persistent shared memory that agents can read/write to maintain
state and collaborate even when individual agents are offline or reset.
"""

import sqlite3
import json
import threading
import time
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, Union
from pathlib import Path
import logging

logger = logging.getLogger(__name__)

class SharedMemory:
    """
    Thread-safe shared memory system with SQLite persistence.
    
    Supports:
    - Key-value storage with versioning
    - Agent-specific memory spaces
    - Automatic cleanup of old data
    - Transaction support for atomic operations
    """
    
    def __init__(self, db_path: str = "shared_memory.db", cleanup_days: int = 30):
        """Initialize shared memory with database path."""
        self.db_path = Path(db_path)
        self.cleanup_days = cleanup_days
        self._lock = threading.RLock()
        self._init_database()
        
    def _init_database(self):
        """Initialize database schema."""
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS shared_memory (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    key TEXT NOT NULL,
                    value TEXT NOT NULL,
                    agent_id TEXT,
                    namespace TEXT DEFAULT 'global',
                    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
                    expires_at DATETIME,
                    version INTEGER DEFAULT 1
                )
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_key_namespace ON shared_memory(key, namespace)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_agent_id ON shared_memory(agent_id)
            """)
            
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_expires_at ON shared_memory(expires_at)
            """)
            
    def set(self, key: str, value: Any, agent_id: str, namespace: str = "global", 
            expires_in: Optional[int] = None) -> bool:
        """
        Store a value in shared memory.
        
        Args:
            key: The key to store the value under
            value: The value to store (will be JSON serialized)
            agent_id: ID of the agent storing the value
            namespace: Namespace for the key (default: 'global')
            expires_in: Optional expiration time in seconds
            
        Returns:
            True if successful, False otherwise
        """
        try:
            with self._lock:
                serialized_value = json.dumps(value)
                expires_at = None
                
                if expires_in:
                    expires_at = datetime.now() + timedelta(seconds=expires_in)
                
                with sqlite3.connect(self.db_path) as conn:
                    # Check if key exists to determine version
                    cursor = conn.execute(
                        "SELECT MAX(version) FROM shared_memory WHERE key = ? AND namespace = ?",
                        (key, namespace)
                    )
                    result = cursor.fetchone()
                    version = (result[0] or 0) + 1
                    
                    conn.execute("""
                        INSERT INTO shared_memory (key, value, agent_id, namespace, expires_at, version)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (key, serialized_value, agent_id, namespace, expires_at, version))
                    
                logger.debug(f"Set {namespace}:{key} by agent {agent_id} (v{version})")
                return True
                
        except Exception as e:
            logger.error(f"Failed to set {namespace}:{key}: {e}")
            return False
            
    def get(self, key: str, namespace: str = "global", default: Any = None) -> Any:
        """
        Retrieve the latest value for a key.
        
        Args:
            key: The key to retrieve
            namespace: Namespace for the key (default: 'global')
            default: Default value if key not found
            
        Returns:
            The stored value or default
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT value FROM shared_memory 
                        WHERE key = ? AND namespace = ? 
                        AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                        ORDER BY version DESC LIMIT 1
                    """, (key, namespace))
                    
                    result = cursor.fetchone()
                    if result:
                        return json.loads(result[0])
                    return default
                    
        except Exception as e:
            logger.error(f"Failed to get {namespace}:{key}: {e}")
            return default
            
    def get_history(self, key: str, namespace: str = "global", limit: int = 10) -> List[Dict]:
        """
        Get version history for a key.
        
        Args:
            key: The key to get history for
            namespace: Namespace for the key
            limit: Maximum number of versions to return
            
        Returns:
            List of version records with metadata
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute("""
                        SELECT value, agent_id, timestamp, version 
                        FROM shared_memory 
                        WHERE key = ? AND namespace = ?
                        ORDER BY version DESC LIMIT ?
                    """, (key, namespace, limit))
                    
                    return [
                        {
                            "value": json.loads(row[0]),
                            "agent_id": row[1],
                            "timestamp": row[2],
                            "version": row[3]
                        }
                        for row in cursor.fetchall()
                    ]
                    
        except Exception as e:
            logger.error(f"Failed to get history for {namespace}:{key}: {e}")
            return []
            
    def delete(self, key: str, namespace: str = "global") -> bool:
        """
        Delete all versions of a key.
        
        Args:
            key: The key to delete
            namespace: Namespace for the key
            
        Returns:
            True if successful
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    conn.execute(
                        "DELETE FROM shared_memory WHERE key = ? AND namespace = ?",
                        (key, namespace)
                    )
                logger.debug(f"Deleted {namespace}:{key}")
                return True
                
        except Exception as e:
            logger.error(f"Failed to delete {namespace}:{key}: {e}")
            return False
            
    def list_keys(self, namespace: str = "global", agent_id: Optional[str] = None) -> List[str]:
        """
        List all keys in a namespace.
        
        Args:
            namespace: Namespace to list keys from
            agent_id: Optional filter by agent ID
            
        Returns:
            List of keys
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    query = """
                        SELECT DISTINCT key FROM shared_memory 
                        WHERE namespace = ?
                        AND (expires_at IS NULL OR expires_at > CURRENT_TIMESTAMP)
                    """
                    params = [namespace]
                    
                    if agent_id:
                        query += " AND agent_id = ?"
                        params.append(agent_id)
                        
                    cursor = conn.execute(query, params)
                    return [row[0] for row in cursor.fetchall()]
                    
        except Exception as e:
            logger.error(f"Failed to list keys in {namespace}: {e}")
            return []
            
    def cleanup_expired(self) -> int:
        """
        Remove expired entries from shared memory.
        
        Returns:
            Number of entries removed
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    cursor = conn.execute(
                        "DELETE FROM shared_memory WHERE expires_at < CURRENT_TIMESTAMP"
                    )
                    count = cursor.rowcount
                    
                logger.debug(f"Cleaned up {count} expired entries")
                return count
                
        except Exception as e:
            logger.error(f"Failed to cleanup expired entries: {e}")
            return 0
            
    def cleanup_old_versions(self, keep_versions: int = 5) -> int:
        """
        Remove old versions, keeping only the most recent N versions per key.
        
        Args:
            keep_versions: Number of versions to keep per key
            
        Returns:
            Number of entries removed
        """
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    # Get keys with more than keep_versions versions
                    cursor = conn.execute("""
                        SELECT key, namespace, COUNT(*) as count
                        FROM shared_memory
                        GROUP BY key, namespace
                        HAVING count > ?
                    """, (keep_versions,))
                    
                    total_deleted = 0
                    for key, namespace, count in cursor.fetchall():
                        # Delete older versions
                        delete_cursor = conn.execute("""
                            DELETE FROM shared_memory 
                            WHERE id IN (
                                SELECT id FROM shared_memory 
                                WHERE key = ? AND namespace = ?
                                ORDER BY version DESC 
                                LIMIT -1 OFFSET ?
                            )
                        """, (key, namespace, keep_versions))
                        total_deleted += delete_cursor.rowcount
                        
                logger.debug(f"Cleaned up {total_deleted} old versions")
                return total_deleted
                
        except Exception as e:
            logger.error(f"Failed to cleanup old versions: {e}")
            return 0
            
    def get_stats(self) -> Dict[str, Any]:
        """Get statistics about shared memory usage."""
        try:
            with self._lock:
                with sqlite3.connect(self.db_path) as conn:
                    stats = {}
                    
                    # Total entries
                    cursor = conn.execute("SELECT COUNT(*) FROM shared_memory")
                    stats["total_entries"] = cursor.fetchone()[0]
                    
                    # Entries by namespace
                    cursor = conn.execute("""
                        SELECT namespace, COUNT(*) FROM shared_memory GROUP BY namespace
                    """)
                    stats["by_namespace"] = dict(cursor.fetchall())
                    
                    # Entries by agent
                    cursor = conn.execute("""
                        SELECT agent_id, COUNT(*) FROM shared_memory GROUP BY agent_id
                    """)
                    stats["by_agent"] = dict(cursor.fetchall())
                    
                    # Expired entries
                    cursor = conn.execute("""
                        SELECT COUNT(*) FROM shared_memory 
                        WHERE expires_at < CURRENT_TIMESTAMP
                    """)
                    stats["expired_entries"] = cursor.fetchone()[0]
                    
                    return stats
                    
        except Exception as e:
            logger.error(f"Failed to get stats: {e}")
            return {}