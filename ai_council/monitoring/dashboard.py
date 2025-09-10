"""
Monitoring Dashboard for AI Council Workspace

Provides human oversight interface with real-time monitoring,
system health tracking, and intervention capabilities.
"""

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse
import json
import asyncio
import logging
from typing import Dict, List, Optional, Any
from datetime import datetime, timedelta
from pathlib import Path

from ..core.coordination_engine import CoordinationEngine
from ..core.shared_memory import SharedMemory
from ..core.agent_registry import AgentRegistry, AgentStatus
from ..core.task_manager import TaskManager, TaskStatus, TaskPriority
from ..communication.message_broker import MessageBroker, MessageType

logger = logging.getLogger(__name__)

class MonitoringDashboard:
    """
    Web-based monitoring dashboard for human oversight.
    
    Features:
    - Real-time system status monitoring
    - Agent health and activity tracking
    - Task progress visualization
    - Manual intervention capabilities
    - System alerts and notifications
    - Historical data and analytics
    """
    
    def __init__(self, coordination_engine: CoordinationEngine,
                 message_broker: MessageBroker, port: int = 8000):
        """
        Initialize monitoring dashboard.
        
        Args:
            coordination_engine: Coordination engine instance
            message_broker: Message broker instance
            port: Port to run dashboard on
        """
        self.coordination_engine = coordination_engine
        self.message_broker = message_broker
        self.port = port
        
        self.app = FastAPI(title="AI Council Monitoring Dashboard")
        self._setup_routes()
        
        # WebSocket connections for real-time updates
        self._websocket_connections = set()
        
        # Monitoring state
        self._alerts = []
        self._system_events = []
        
    def _setup_routes(self):
        """Setup FastAPI routes."""
        
        @self.app.get("/", response_class=HTMLResponse)
        async def dashboard():
            """Main dashboard page."""
            return self._get_dashboard_html()
            
        @self.app.get("/api/status")
        async def get_status():
            """Get overall system status."""
            return {
                "timestamp": datetime.now().isoformat(),
                "status": self.coordination_engine.get_status(),
                "health": self.coordination_engine.get_system_health()
            }
            
        @self.app.get("/api/agents")
        async def get_agents():
            """Get all agents."""
            return self.coordination_engine.agent_registry.list_agents()
            
        @self.app.get("/api/agents/{agent_id}")
        async def get_agent(agent_id: str):
            """Get specific agent details."""
            agent = self.coordination_engine.agent_registry.get_agent(agent_id)
            if not agent:
                raise HTTPException(status_code=404, detail="Agent not found")
            return agent
            
        @self.app.get("/api/tasks")
        async def get_tasks(status: Optional[str] = None, limit: int = 100):
            """Get tasks with optional filtering."""
            status_enum = None
            if status:
                try:
                    status_enum = TaskStatus(status)
                except ValueError:
                    raise HTTPException(status_code=400, detail="Invalid status")
                    
            return self.coordination_engine.task_manager.list_tasks(
                status=status_enum, limit=limit
            )
            
        @self.app.get("/api/tasks/{task_id}")
        async def get_task(task_id: str):
            """Get specific task details."""
            task = self.coordination_engine.task_manager.get_task(task_id)
            if not task:
                raise HTTPException(status_code=404, detail="Task not found")
                
            # Add execution log
            task["execution_log"] = self.coordination_engine.task_manager.get_task_log(task_id)
            return task
            
        @self.app.post("/api/tasks")
        async def create_task(task_data: Dict):
            """Create a new task."""
            try:
                priority = TaskPriority(task_data.get("priority", 2))
                
                task_id = self.coordination_engine.create_task(
                    title=task_data["title"],
                    description=task_data.get("description", ""),
                    task_type=task_data.get("task_type", "general"),
                    required_capabilities=task_data.get("required_capabilities", []),
                    input_data=task_data.get("input_data", {}),
                    priority=priority,
                    deadline=task_data.get("deadline"),
                    dependencies=task_data.get("dependencies", []),
                    metadata=task_data.get("metadata", {})
                )
                
                if task_id:
                    return {"task_id": task_id, "status": "created"}
                else:
                    raise HTTPException(status_code=500, detail="Failed to create task")
                    
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
                
        @self.app.post("/api/tasks/{task_id}/cancel")
        async def cancel_task(task_id: str, reason: str = ""):
            """Cancel a task."""
            success = self.coordination_engine.task_manager.cancel_task(task_id, reason)
            if success:
                return {"status": "cancelled"}
            else:
                raise HTTPException(status_code=500, detail="Failed to cancel task")
                
        @self.app.get("/api/messages")
        async def get_messages(agent_id: Optional[str] = None, limit: int = 50):
            """Get recent messages."""
            if agent_id:
                return self.message_broker.get_messages(agent_id, limit=limit)
            else:
                # Get all recent messages (admin view)
                return self._get_all_recent_messages(limit)
                
        @self.app.post("/api/messages")
        async def send_message(message_data: Dict):
            """Send a message."""
            try:
                message_type = MessageType(message_data.get("message_type", "direct"))
                
                message_id = self.message_broker.send_message(
                    sender_id=message_data.get("sender_id", "dashboard"),
                    recipient_id=message_data.get("recipient_id"),
                    message_type=message_type,
                    subject=message_data.get("subject", ""),
                    content=message_data.get("content", {}),
                    metadata=message_data.get("metadata", {})
                )
                
                if message_id:
                    return {"message_id": message_id, "status": "sent"}
                else:
                    raise HTTPException(status_code=500, detail="Failed to send message")
                    
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
                
        @self.app.get("/api/shared-memory")
        async def get_shared_memory(namespace: str = "global"):
            """Get shared memory contents."""
            keys = self.coordination_engine.shared_memory.list_keys(namespace)
            data = {}
            
            for key in keys:
                data[key] = self.coordination_engine.shared_memory.get(key, namespace)
                
            return {
                "namespace": namespace,
                "data": data,
                "stats": self.coordination_engine.shared_memory.get_stats()
            }
            
        @self.app.post("/api/shared-memory")
        async def set_shared_memory(memory_data: Dict):
            """Set shared memory value."""
            try:
                success = self.coordination_engine.shared_memory.set(
                    key=memory_data["key"],
                    value=memory_data["value"],
                    agent_id=memory_data.get("agent_id", "dashboard"),
                    namespace=memory_data.get("namespace", "global"),
                    expires_in=memory_data.get("expires_in")
                )
                
                if success:
                    return {"status": "set"}
                else:
                    raise HTTPException(status_code=500, detail="Failed to set value")
                    
            except Exception as e:
                raise HTTPException(status_code=400, detail=str(e))
                
        @self.app.get("/api/alerts")
        async def get_alerts():
            """Get system alerts."""
            return {
                "alerts": self._alerts,
                "system_events": self._system_events[-50:]  # Last 50 events
            }
            
        @self.app.post("/api/alerts/{alert_id}/dismiss")
        async def dismiss_alert(alert_id: str):
            """Dismiss an alert."""
            for alert in self._alerts:
                if alert.get("id") == alert_id:
                    alert["dismissed"] = True
                    alert["dismissed_at"] = datetime.now().isoformat()
                    break
                    
            return {"status": "dismissed"}
            
        @self.app.websocket("/ws")
        async def websocket_endpoint(websocket: WebSocket):
            """WebSocket endpoint for real-time updates."""
            await websocket.accept()
            self._websocket_connections.add(websocket)
            
            try:
                while True:
                    # Keep connection alive and handle client messages
                    message = await websocket.receive_text()
                    # Echo back for now (could handle commands)
                    await websocket.send_text(f"Echo: {message}")
                    
            except WebSocketDisconnect:
                self._websocket_connections.discard(websocket)
                
    def _get_dashboard_html(self) -> str:
        """Generate dashboard HTML."""
        return """
<!DOCTYPE html>
<html>
<head>
    <title>AI Council Monitoring Dashboard</title>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1">
    <style>
        body { font-family: Arial, sans-serif; margin: 20px; background-color: #f5f5f5; }
        .container { max-width: 1200px; margin: 0 auto; }
        .header { background: #2c3e50; color: white; padding: 20px; border-radius: 5px; margin-bottom: 20px; }
        .grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(300px, 1fr)); gap: 20px; }
        .card { background: white; padding: 20px; border-radius: 5px; box-shadow: 0 2px 5px rgba(0,0,0,0.1); }
        .status-healthy { color: #27ae60; }
        .status-warning { color: #f39c12; }
        .status-critical { color: #e74c3c; }
        .metric { font-size: 24px; font-weight: bold; }
        .metric-label { font-size: 14px; color: #666; }
        button { background: #3498db; color: white; border: none; padding: 10px 20px; border-radius: 3px; cursor: pointer; }
        button:hover { background: #2980b9; }
        .alert { background: #f8d7da; color: #721c24; padding: 10px; border-radius: 3px; margin: 5px 0; }
        .log { background: #f8f9fa; padding: 10px; border-radius: 3px; font-family: monospace; font-size: 12px; max-height: 200px; overflow-y: auto; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>AI Council Monitoring Dashboard</h1>
            <div id="connection-status">Connected</div>
        </div>
        
        <div class="grid">
            <div class="card">
                <h3>System Health</h3>
                <div id="health-status" class="status-healthy">
                    <div class="metric" id="health-score">--</div>
                    <div class="metric-label">Health Score</div>
                </div>
                <div id="health-issues"></div>
            </div>
            
            <div class="card">
                <h3>Agents</h3>
                <div class="metric" id="agent-count">--</div>
                <div class="metric-label">Total Agents</div>
                <div id="agent-details"></div>
            </div>
            
            <div class="card">
                <h3>Tasks</h3>
                <div class="metric" id="task-count">--</div>
                <div class="metric-label">Total Tasks</div>
                <div id="task-details"></div>
            </div>
            
            <div class="card">
                <h3>Messages</h3>
                <div class="metric" id="message-count">--</div>
                <div class="metric-label">Messages (24h)</div>
                <div id="message-details"></div>
            </div>
        </div>
        
        <div class="grid">
            <div class="card">
                <h3>Recent Activities</h3>
                <div id="activity-log" class="log"></div>
            </div>
            
            <div class="card">
                <h3>System Alerts</h3>
                <div id="alerts"></div>
                <button onclick="clearAlerts()">Clear All</button>
            </div>
        </div>
        
        <div class="card">
            <h3>Quick Actions</h3>
            <button onclick="refreshData()">Refresh Data</button>
            <button onclick="createSampleTask()">Create Sample Task</button>
            <button onclick="broadcastMessage()">Broadcast Message</button>
        </div>
    </div>

    <script>
        let ws;
        
        function connectWebSocket() {
            ws = new WebSocket(`ws://${window.location.host}/ws`);
            
            ws.onopen = function() {
                document.getElementById('connection-status').textContent = 'Connected';
            };
            
            ws.onclose = function() {
                document.getElementById('connection-status').textContent = 'Disconnected';
                // Reconnect after 3 seconds
                setTimeout(connectWebSocket, 3000);
            };
            
            ws.onmessage = function(event) {
                console.log('WebSocket message:', event.data);
            };
        }
        
        async function fetchData(endpoint) {
            try {
                const response = await fetch(`/api${endpoint}`);
                return await response.json();
            } catch (error) {
                console.error('Fetch error:', error);
                return null;
            }
        }
        
        async function updateDashboard() {
            // Update system status
            const status = await fetchData('/status');
            if (status) {
                const health = status.health;
                const healthEl = document.getElementById('health-score');
                const statusEl = document.getElementById('health-status');
                
                healthEl.textContent = health.health_score;
                statusEl.className = `status-${health.health_status}`;
                
                document.getElementById('health-issues').innerHTML = 
                    health.issues.map(issue => `<div class="alert">${issue}</div>`).join('');
                    
                // Update metrics
                document.getElementById('agent-count').textContent = health.system_stats.total_agents;
                document.getElementById('task-count').textContent = health.system_stats.total_tasks;
                
                // Update agent details
                const agentDetails = `
                    Online: ${health.system_stats.online_agents}<br>
                    Offline: ${health.system_stats.total_agents - health.system_stats.online_agents}
                `;
                document.getElementById('agent-details').innerHTML = agentDetails;
                
                // Update task details
                const taskDetails = `
                    Pending: ${health.system_stats.pending_tasks}<br>
                    Completed: ${health.system_stats.total_tasks - health.system_stats.pending_tasks}
                `;
                document.getElementById('task-details').innerHTML = taskDetails;
            }
            
            // Update message stats
            const messages = await fetchData('/messages?limit=10');
            if (messages) {
                document.getElementById('message-count').textContent = messages.length;
                
                const recent = messages.slice(0, 5).map(msg => 
                    `${msg.created_at}: ${msg.sender_id} → ${msg.recipient_id || 'ALL'}: ${msg.subject}`
                ).join('<br>');
                document.getElementById('message-details').innerHTML = recent;
            }
            
            // Update alerts
            const alerts = await fetchData('/alerts');
            if (alerts) {
                const alertsHtml = alerts.alerts
                    .filter(alert => !alert.dismissed)
                    .map(alert => `<div class="alert">${alert.message}</div>`)
                    .join('');
                document.getElementById('alerts').innerHTML = alertsHtml || 'No alerts';
                
                // Update activity log
                const activities = alerts.system_events.slice(-10).reverse()
                    .map(event => `${event.timestamp}: ${event.message}`)
                    .join('<br>');
                document.getElementById('activity-log').innerHTML = activities;
            }
        }
        
        function refreshData() {
            updateDashboard();
        }
        
        async function createSampleTask() {
            const task = {
                title: "Sample Task",
                description: "A sample task created from the dashboard",
                task_type: "sample",
                required_capabilities: ["general"],
                priority: 2
            };
            
            const response = await fetch('/api/tasks', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(task)
            });
            
            if (response.ok) {
                alert('Sample task created successfully');
                refreshData();
            } else {
                alert('Failed to create task');
            }
        }
        
        async function broadcastMessage() {
            const message = {
                message_type: "broadcast",
                subject: "Dashboard Message",
                content: {
                    text: "Hello from the monitoring dashboard!",
                    timestamp: new Date().toISOString()
                }
            };
            
            const response = await fetch('/api/messages', {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify(message)
            });
            
            if (response.ok) {
                alert('Broadcast message sent');
            } else {
                alert('Failed to send message');
            }
        }
        
        function clearAlerts() {
            // This would need to call the dismiss endpoints for each alert
            alert('Clear alerts functionality would be implemented here');
        }
        
        // Initialize
        connectWebSocket();
        updateDashboard();
        
        // Auto-refresh every 30 seconds
        setInterval(updateDashboard, 30000);
    </script>
</body>
</html>
        """
        
    def _get_all_recent_messages(self, limit: int) -> List[Dict]:
        """Get all recent messages for admin view."""
        # This would query the message broker's database directly
        # For now, return empty list
        return []
        
    async def broadcast_update(self, update_type: str, data: Any):
        """Broadcast update to all connected WebSocket clients."""
        if not self._websocket_connections:
            return
            
        message = json.dumps({
            "type": update_type,
            "data": data,
            "timestamp": datetime.now().isoformat()
        })
        
        # Send to all connections
        disconnected = set()
        for websocket in self._websocket_connections:
            try:
                await websocket.send_text(message)
            except Exception:
                disconnected.add(websocket)
                
        # Remove disconnected clients
        self._websocket_connections -= disconnected
        
    def add_alert(self, severity: str, message: str, source: str = "system"):
        """Add a system alert."""
        alert = {
            "id": f"alert_{int(datetime.now().timestamp())}",
            "severity": severity,
            "message": message,
            "source": source,
            "timestamp": datetime.now().isoformat(),
            "dismissed": False
        }
        
        self._alerts.append(alert)
        logger.warning(f"System alert: {message}")
        
        # Broadcast to connected clients
        asyncio.create_task(self.broadcast_update("alert", alert))
        
    def add_system_event(self, message: str, event_type: str = "info"):
        """Add a system event to the log."""
        event = {
            "timestamp": datetime.now().isoformat(),
            "message": message,
            "type": event_type
        }
        
        self._system_events.append(event)
        
        # Keep only last 1000 events
        if len(self._system_events) > 1000:
            self._system_events = self._system_events[-1000:]
            
        # Broadcast to connected clients
        asyncio.create_task(self.broadcast_update("system_event", event))
        
    async def start_monitoring(self):
        """Start automated monitoring and alerting."""
        logger.info("Starting automated monitoring")
        
        while True:
            try:
                # Check system health
                health = self.coordination_engine.get_system_health()
                
                # Generate alerts based on health
                if health["health_status"] == "critical":
                    self.add_alert("critical", f"System health critical: {', '.join(health['issues'])}")
                elif health["health_status"] == "warning":
                    self.add_alert("warning", f"System health degraded: {', '.join(health['issues'])}")
                    
                # Check for stuck tasks
                # TODO: Implement stuck task detection
                
                # Check agent activity
                # TODO: Implement agent activity monitoring
                
                await asyncio.sleep(60)  # Check every minute
                
            except Exception as e:
                logger.error(f"Monitoring error: {e}")
                await asyncio.sleep(60)
                
    def run(self):
        """Run the monitoring dashboard."""
        import uvicorn
        logger.info(f"Starting monitoring dashboard on port {self.port}")
        uvicorn.run(self.app, host="0.0.0.0", port=self.port)