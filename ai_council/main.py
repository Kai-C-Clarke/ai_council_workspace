"""
Main Application Entry Point for AI Council Workspace

Provides command-line interface and main application startup.
"""

import asyncio
import argparse
import sys
import signal
import logging
from pathlib import Path
from typing import Optional

from .core.shared_memory import SharedMemory
from .core.agent_registry import AgentRegistry
from .core.task_manager import TaskManager
from .core.coordination_engine import CoordinationEngine
from .communication.message_broker import MessageBroker
from .monitoring.dashboard import MonitoringDashboard
from .utils.config import load_config, setup_logging, AICouncilConfig

logger = logging.getLogger(__name__)

class AICouncilWorkspace:
    """
    Main application class for AI Council Workspace.
    
    Manages the lifecycle of all components and provides a unified interface
    for starting and stopping the collaborative AI system.
    """
    
    def __init__(self, config: AICouncilConfig):
        """Initialize the workspace with configuration."""
        self.config = config
        
        # Initialize core components
        self.shared_memory = SharedMemory(
            db_path=config.get_db_path(config.database.shared_memory_db)
        )
        
        self.agent_registry = AgentRegistry(
            db_path=config.get_db_path(config.database.agent_registry_db),
            heartbeat_timeout=config.coordination.heartbeat_timeout
        )
        
        self.task_manager = TaskManager(
            db_path=config.get_db_path(config.database.task_manager_db),
            max_retries=config.coordination.max_task_retries
        )
        
        self.coordination_engine = CoordinationEngine(
            shared_memory=self.shared_memory,
            agent_registry=self.agent_registry,
            task_manager=self.task_manager,
            assignment_interval=config.coordination.assignment_interval,
            cleanup_interval=config.coordination.cleanup_interval
        )
        
        self.message_broker = MessageBroker(
            db_path=config.get_db_path(config.database.message_broker_db),
            retention_days=config.message_broker.retention_days,
            websocket_port=config.message_broker.websocket_port
        )
        
        self.monitoring_dashboard = None
        if config.monitoring.enable_monitoring:
            self.monitoring_dashboard = MonitoringDashboard(
                coordination_engine=self.coordination_engine,
                message_broker=self.message_broker,
                port=config.monitoring.dashboard_port
            )
        
        self._running = False
        self._tasks = []
        
    async def start(self):
        """Start all components of the AI Council Workspace."""
        logger.info("Starting AI Council Workspace")
        
        try:
            # Start coordination engine
            self.coordination_engine.start()
            
            # Start message broker WebSocket server
            await self.message_broker.start_websocket_server()
            
            # Start monitoring if enabled
            if self.monitoring_dashboard:
                monitoring_task = asyncio.create_task(
                    self.monitoring_dashboard.start_monitoring()
                )
                self._tasks.append(monitoring_task)
                
                # Start dashboard web server in background
                dashboard_task = asyncio.create_task(
                    self._run_dashboard()
                )
                self._tasks.append(dashboard_task)
            
            # Record startup in shared memory
            self.shared_memory.set(
                "workspace_status",
                {
                    "status": "running",
                    "started_at": str(asyncio.get_event_loop().time()),
                    "config": self.config.dict()
                },
                "system"
            )
            
            self._running = True
            logger.info("AI Council Workspace started successfully")
            
            # Display startup information
            self._display_startup_info()
            
        except Exception as e:
            logger.error(f"Failed to start AI Council Workspace: {e}")
            await self.stop()
            raise
            
    async def stop(self):
        """Stop all components gracefully."""
        logger.info("Stopping AI Council Workspace")
        
        self._running = False
        
        # Cancel background tasks
        for task in self._tasks:
            task.cancel()
            
        # Wait for tasks to complete
        if self._tasks:
            await asyncio.gather(*self._tasks, return_exceptions=True)
            
        # Stop coordination engine
        self.coordination_engine.stop()
        
        # Record shutdown in shared memory
        try:
            self.shared_memory.set(
                "workspace_status",
                {
                    "status": "stopped",
                    "stopped_at": str(asyncio.get_event_loop().time())
                },
                "system"
            )
        except Exception as e:
            logger.error(f"Failed to record shutdown: {e}")
            
        logger.info("AI Council Workspace stopped")
        
    async def _run_dashboard(self):
        """Run the monitoring dashboard web server."""
        if not self.monitoring_dashboard:
            return
            
        import uvicorn
        config = uvicorn.Config(
            self.monitoring_dashboard.app,
            host="0.0.0.0",
            port=self.config.monitoring.dashboard_port,
            log_level=self.config.monitoring.log_level.lower()
        )
        server = uvicorn.Server(config)
        await server.serve()
        
    def _display_startup_info(self):
        """Display startup information to console."""
        print("\n" + "="*60)
        print("🤖 AI COUNCIL WORKSPACE STARTED")
        print("="*60)
        print(f"Environment: {self.config.environment}")
        print(f"Data Directory: {self.config.data_dir}")
        
        if self.monitoring_dashboard:
            print(f"Dashboard: http://localhost:{self.config.monitoring.dashboard_port}")
            
        print(f"WebSocket: ws://localhost:{self.config.message_broker.websocket_port}")
        print(f"Log Level: {self.config.monitoring.log_level}")
        print("\nComponents:")
        print("  ✓ Shared Memory System")
        print("  ✓ Agent Registry") 
        print("  ✓ Task Manager")
        print("  ✓ Coordination Engine")
        print("  ✓ Message Broker")
        
        if self.monitoring_dashboard:
            print("  ✓ Monitoring Dashboard")
            
        print("\n📊 System Status:")
        status = self.coordination_engine.get_system_health()
        print(f"  Health: {status['health_status'].upper()} ({status['health_score']}/100)")
        print(f"  Agents: {status['system_stats']['total_agents']}")
        print(f"  Tasks: {status['system_stats']['total_tasks']}")
        
        if status['issues']:
            print("  ⚠️  Issues:", ", ".join(status['issues']))
            
        print("\n🚀 Ready for agent connections!")
        print("="*60 + "\n")
        
    def get_status(self):
        """Get current workspace status."""
        return {
            "running": self._running,
            "config": self.config.dict(),
            "coordination_status": self.coordination_engine.get_status(),
            "system_health": self.coordination_engine.get_system_health()
        }

def create_sample_config():
    """Create a sample configuration file."""
    config = AICouncilConfig()
    
    # Save to current directory
    config_path = Path("ai_council_config.yaml")
    
    import yaml
    with open(config_path, 'w') as f:
        yaml.dump(config.dict(), f, default_flow_style=False, indent=2)
        
    print(f"Sample configuration created: {config_path}")
    return config_path

async def run_workspace(config_path: Optional[str] = None, 
                       env_file: Optional[str] = None):
    """Run the AI Council Workspace."""
    
    # Load configuration
    config = load_config(config_path, env_file)
    setup_logging(config)
    
    # Create workspace
    workspace = AICouncilWorkspace(config)
    
    # Setup signal handlers for graceful shutdown
    def signal_handler():
        logger.info("Received shutdown signal")
        asyncio.create_task(workspace.stop())
        
    # Register signal handlers
    for sig in [signal.SIGINT, signal.SIGTERM]:
        try:
            asyncio.get_event_loop().add_signal_handler(sig, signal_handler)
        except NotImplementedError:
            # Signal handlers not supported on Windows
            pass
    
    try:
        # Start workspace
        await workspace.start()
        
        # Keep running until stopped
        while workspace._running:
            await asyncio.sleep(1)
            
    except KeyboardInterrupt:
        logger.info("Keyboard interrupt received")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
    finally:
        await workspace.stop()

def main():
    """Main entry point with command-line interface."""
    parser = argparse.ArgumentParser(
        description="AI Council Workspace - Collaborative AI Infrastructure"
    )
    
    subparsers = parser.add_subparsers(dest='command', help='Available commands')
    
    # Start command
    start_parser = subparsers.add_parser('start', help='Start the AI Council Workspace')
    start_parser.add_argument('--config', '-c', help='Configuration file path')
    start_parser.add_argument('--env', '-e', help='Environment file path')
    
    # Config command
    config_parser = subparsers.add_parser('config', help='Configuration management')
    config_parser.add_argument('--create-sample', action='store_true', 
                              help='Create sample configuration file')
    
    # Status command (for checking running instance)
    status_parser = subparsers.add_parser('status', help='Check workspace status')
    
    args = parser.parse_args()
    
    if args.command == 'start':
        try:
            asyncio.run(run_workspace(args.config, args.env))
        except KeyboardInterrupt:
            print("\nShutdown complete.")
        except Exception as e:
            print(f"Failed to start workspace: {e}")
            sys.exit(1)
            
    elif args.command == 'config':
        if args.create_sample:
            create_sample_config()
        else:
            config_parser.print_help()
            
    elif args.command == 'status':
        # This would need to connect to a running instance
        print("Status checking not yet implemented")
        
    else:
        parser.print_help()

if __name__ == "__main__":
    main()