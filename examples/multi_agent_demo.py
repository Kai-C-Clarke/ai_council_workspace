#!/usr/bin/env python3
"""
Multi-Agent Demo for AI Council Workspace

Demonstrates multiple agents collaborating on tasks with different capabilities.
"""

import asyncio
import sys
from pathlib import Path

# Add the parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from ai_council.agents.base_agent import BaseAgent
from ai_council.core.coordination_engine import CoordinationEngine
from ai_council.core.shared_memory import SharedMemory
from ai_council.core.agent_registry import AgentRegistry
from ai_council.core.task_manager import TaskManager, TaskPriority
from ai_council.communication.message_broker import MessageBroker, MessageType

class MathAgent(BaseAgent):
    """Agent specialized in mathematical operations."""
    
    def __init__(self, agent_id: str = "math_agent", **kwargs):
        super().__init__(
            agent_id=agent_id,
            name="Math Agent",
            description="Specialized in mathematical calculations",
            capabilities=["math", "calculation", "statistics"],
            **kwargs
        )
        
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute mathematical tasks."""
        input_data = task.get("input_data", {})
        operation = input_data.get("operation", "unknown")
        numbers = input_data.get("numbers", [])
        
        await asyncio.sleep(2)  # Simulate processing time
        
        result = None
        if operation == "sum":
            result = sum(numbers)
        elif operation == "multiply":
            result = 1
            for num in numbers:
                result *= num
        elif operation == "average":
            result = sum(numbers) / len(numbers) if numbers else 0
        elif operation == "max":
            result = max(numbers) if numbers else None
        elif operation == "min":
            result = min(numbers) if numbers else None
        
        return {
            "operation": operation,
            "input_numbers": numbers,
            "result": result,
            "processed_by": self.agent_id,
            "calculation_time": 2.0
        }

class TextAgent(BaseAgent):
    """Agent specialized in text processing."""
    
    def __init__(self, agent_id: str = "text_agent", **kwargs):
        super().__init__(
            agent_id=agent_id,
            name="Text Processing Agent",
            description="Specialized in text analysis and processing",
            capabilities=["text", "analysis", "nlp"],
            **kwargs
        )
        
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute text processing tasks."""
        input_data = task.get("input_data", {})
        text = input_data.get("text", "")
        operation = input_data.get("operation", "analyze")
        
        await asyncio.sleep(1.5)  # Simulate processing time
        
        result = {}
        if operation == "analyze":
            words = text.split()
            result = {
                "word_count": len(words),
                "character_count": len(text),
                "sentence_count": text.count('.') + text.count('!') + text.count('?'),
                "unique_words": len(set(word.lower().strip('.,!?') for word in words))
            }
        elif operation == "uppercase":
            result = {"processed_text": text.upper()}
        elif operation == "lowercase":
            result = {"processed_text": text.lower()}
        elif operation == "reverse":
            result = {"processed_text": text[::-1]}
        
        return {
            "operation": operation,
            "input_text": text[:100] + "..." if len(text) > 100 else text,
            "result": result,
            "processed_by": self.agent_id
        }

class CoordinatorAgent(BaseAgent):
    """Agent that coordinates work between other agents."""
    
    def __init__(self, agent_id: str = "coordinator_agent", **kwargs):
        super().__init__(
            agent_id=agent_id,
            name="Coordinator Agent",
            description="Coordinates complex multi-step tasks",
            capabilities=["coordination", "workflow", "management"],
            **kwargs
        )
        
    async def execute_task(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """Execute coordination tasks by delegating to other agents."""
        input_data = task.get("input_data", {})
        workflow = input_data.get("workflow", [])
        
        results = []
        
        for step in workflow:
            step_type = step.get("type")
            step_data = step.get("data", {})
            
            if step_type == "math":
                # Create a math task
                task_id = self.coordination_engine.create_task(
                    title=f"Math Step: {step.get('description', 'Calculation')}",
                    description="Math operation delegated by coordinator",
                    required_capabilities=["math"],
                    input_data=step_data,
                    priority=TaskPriority.HIGH
                )
            elif step_type == "text":
                # Create a text task
                task_id = self.coordination_engine.create_task(
                    title=f"Text Step: {step.get('description', 'Text processing')}",
                    description="Text operation delegated by coordinator",
                    required_capabilities=["text"],
                    input_data=step_data,
                    priority=TaskPriority.HIGH
                )
            
            # Wait a bit for the task to be processed
            await asyncio.sleep(5)
            
            # Check if task completed (simplified - in real implementation would poll properly)
            delegated_task = self.coordination_engine.task_manager.get_task(task_id)
            if delegated_task and delegated_task.get("status") == "completed":
                results.append({
                    "step": step,
                    "result": delegated_task.get("output_data", {})
                })
            else:
                results.append({
                    "step": step,
                    "result": {"error": "Task not completed in time"}
                })
        
        return {
            "workflow_results": results,
            "coordinated_by": self.agent_id,
            "total_steps": len(workflow)
        }

async def main():
    """Run multi-agent demonstration."""
    
    print("🤖 Starting Multi-Agent Demo")
    print("=" * 50)
    
    # Initialize core components
    shared_memory = SharedMemory("demo_shared_memory.db")
    agent_registry = AgentRegistry("demo_agent_registry.db")
    task_manager = TaskManager("demo_task_manager.db")
    message_broker = MessageBroker("demo_message_broker.db")
    
    coordination_engine = CoordinationEngine(
        shared_memory=shared_memory,
        agent_registry=agent_registry,
        task_manager=task_manager
    )
    
    # Start services
    coordination_engine.start()
    await message_broker.start_websocket_server()
    
    # Create agents
    math_agent = MathAgent(
        coordination_engine=coordination_engine,
        message_broker=message_broker
    )
    
    text_agent = TextAgent(
        coordination_engine=coordination_engine,
        message_broker=message_broker
    )
    
    coordinator_agent = CoordinatorAgent(
        coordination_engine=coordination_engine,
        message_broker=message_broker
    )
    
    try:
        # Start all agents
        print("🚀 Starting agents...")
        await math_agent.start()
        print(f"✓ {math_agent.name} started")
        
        await text_agent.start()
        print(f"✓ {text_agent.name} started")
        
        await coordinator_agent.start()
        print(f"✓ {coordinator_agent.name} started")
        
        # Wait a moment for agents to settle
        await asyncio.sleep(2)
        
        print(f"\n📊 System Status:")
        health = coordination_engine.get_system_health()
        print(f"  Health: {health['health_status']} ({health['health_score']}/100)")
        print(f"  Agents Online: {health['system_stats']['online_agents']}")
        
        # Create various tasks
        print(f"\n📋 Creating demonstration tasks...")
        
        # Math tasks
        math_task1 = coordination_engine.create_task(
            title="Calculate Sum",
            description="Calculate sum of numbers",
            required_capabilities=["math"],
            input_data={
                "operation": "sum",
                "numbers": [10, 20, 30, 40, 50]
            }
        )
        
        math_task2 = coordination_engine.create_task(
            title="Find Average",
            description="Calculate average of test scores",
            required_capabilities=["math"],
            input_data={
                "operation": "average", 
                "numbers": [85, 92, 78, 88, 95, 82]
            }
        )
        
        # Text tasks
        text_task1 = coordination_engine.create_task(
            title="Analyze Text",
            description="Analyze sample text",
            required_capabilities=["text"],
            input_data={
                "operation": "analyze",
                "text": "The quick brown fox jumps over the lazy dog. This sentence contains every letter of the alphabet!"
            }
        )
        
        text_task2 = coordination_engine.create_task(
            title="Convert to Uppercase",
            description="Convert text to uppercase",
            required_capabilities=["text"],
            input_data={
                "operation": "uppercase",
                "text": "hello world from the ai council!"
            }
        )
        
        # Coordination task
        coordination_task = coordination_engine.create_task(
            title="Complex Workflow",
            description="Multi-step workflow coordination",
            required_capabilities=["coordination"],
            input_data={
                "workflow": [
                    {
                        "type": "math",
                        "description": "Calculate statistics",
                        "data": {
                            "operation": "sum",
                            "numbers": [1, 2, 3, 4, 5]
                        }
                    },
                    {
                        "type": "text", 
                        "description": "Process description",
                        "data": {
                            "operation": "analyze",
                            "text": "This is a coordinated workflow task."
                        }
                    }
                ]
            },
            priority=TaskPriority.HIGH
        )
        
        print(f"✓ Created {5} demonstration tasks")
        
        # Monitor progress
        print(f"\n🏃 Agents working... (monitoring for 30 seconds)")
        
        for i in range(30):
            await asyncio.sleep(1)
            
            if i % 5 == 0:  # Update every 5 seconds
                health = coordination_engine.get_system_health()
                pending = health['system_stats']['pending_tasks']
                total = health['system_stats']['total_tasks']
                completed = total - pending
                
                print(f"  Progress: {completed}/{total} tasks completed, {pending} pending")
                
                # Show recent messages
                if i % 10 == 0 and message_broker:
                    recent_messages = message_broker.get_messages("coordinator_agent", limit=3)
                    if recent_messages:
                        print(f"  Recent messages: {len(recent_messages)}")
        
        print(f"\n📈 Final Results:")
        final_health = coordination_engine.get_system_health()
        print(f"  System Health: {final_health['health_status']}")
        print(f"  Total Tasks: {final_health['system_stats']['total_tasks']}")
        print(f"  Pending Tasks: {final_health['system_stats']['pending_tasks']}")
        
        # Show some completed tasks
        completed_tasks = task_manager.list_tasks(limit=10)
        completed_count = sum(1 for task in completed_tasks if task.get('status') == 'completed')
        print(f"  Completed Tasks: {completed_count}")
        
    except KeyboardInterrupt:
        print("\n\n🛑 Demo interrupted")
    except Exception as e:
        print(f"\n❌ Demo error: {e}")
        import traceback
        traceback.print_exc()
    finally:
        # Clean shutdown
        print("🧹 Shutting down agents...")
        await math_agent.stop()
        await text_agent.stop()
        await coordinator_agent.stop()
        coordination_engine.stop()
        print("✅ Demo complete")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nDemo terminated. Goodbye! 👋")