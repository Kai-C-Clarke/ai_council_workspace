#!/usr/bin/env python3
"""
Simple Agent Example for AI Council Workspace

Demonstrates how to create and run a basic agent that can participate
in the collaborative workspace.
"""

import asyncio
import sys
from pathlib import Path

# Add the parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_council.agents.base_agent import SimpleEchoAgent
from ai_council.core.coordination_engine import CoordinationEngine
from ai_council.core.shared_memory import SharedMemory
from ai_council.core.agent_registry import AgentRegistry
from ai_council.core.task_manager import TaskManager
from ai_council.communication.message_broker import MessageBroker

async def main():
    """Run a simple echo agent."""
    
    print("🤖 Starting Simple Agent Example")
    print("=" * 50)
    
    # Initialize core components (in production, these would be shared services)
    shared_memory = SharedMemory("example_shared_memory.db")
    agent_registry = AgentRegistry("example_agent_registry.db")
    task_manager = TaskManager("example_task_manager.db")
    message_broker = MessageBroker("example_message_broker.db")
    
    coordination_engine = CoordinationEngine(
        shared_memory=shared_memory,
        agent_registry=agent_registry,
        task_manager=task_manager
    )
    
    # Start coordination engine
    coordination_engine.start()
    
    # Start message broker
    await message_broker.start_websocket_server()
    
    # Create and start agent
    agent = SimpleEchoAgent(
        agent_id="example_echo_1",
        coordination_engine=coordination_engine,
        message_broker=message_broker
    )
    
    try:
        await agent.start()
        print(f"✓ Agent {agent.agent_id} started successfully")
        
        # Create some example tasks
        print("\n📋 Creating example tasks...")
        
        task1_id = coordination_engine.create_task(
            title="Hello World Task",
            description="A simple greeting task",
            task_type="greeting",
            required_capabilities=["echo"],
            input_data={"message": "Hello from the AI Council!"}
        )
        print(f"✓ Created task: {task1_id}")
        
        task2_id = coordination_engine.create_task(
            title="Data Processing Task", 
            description="Process some sample data",
            task_type="processing",
            required_capabilities=["general"],
            input_data={
                "data": [1, 2, 3, 4, 5],
                "operation": "sum"
            }
        )
        print(f"✓ Created task: {task2_id}")
        
        # Let the agent run for a while to process tasks
        print(f"\n🏃 Agent {agent.agent_id} running... (Press Ctrl+C to stop)")
        print("Monitoring agent activity:")
        
        for i in range(60):  # Run for 60 seconds
            await asyncio.sleep(1)
            
            if i % 10 == 0:  # Print status every 10 seconds
                status = coordination_engine.get_system_health()
                print(f"  Status: {status['health_status']} | "
                      f"Tasks: {status['system_stats']['total_tasks']} | "
                      f"Agents: {status['system_stats']['online_agents']}")
        
    except KeyboardInterrupt:
        print("\n\n🛑 Shutdown requested")
    except Exception as e:
        print(f"\n❌ Error: {e}")
    finally:
        # Clean shutdown
        print("🧹 Cleaning up...")
        await agent.stop()
        coordination_engine.stop()
        print("✅ Shutdown complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nGoodbye! 👋")