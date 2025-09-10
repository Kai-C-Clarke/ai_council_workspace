#!/usr/bin/env python3
"""
Basic functionality test for AI Council Workspace.

Tests core components to ensure they work correctly.
"""

import asyncio
import tempfile
import shutil
from pathlib import Path

def test_shared_memory():
    """Test shared memory functionality."""
    print("🧠 Testing Shared Memory...")
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    try:
        from ai_council.core.shared_memory import SharedMemory
        
        memory = SharedMemory(db_path)
        
        # Test basic set/get
        success = memory.set("test_key", {"message": "Hello World"}, "test_agent")
        assert success, "Failed to set value"
        
        value = memory.get("test_key")
        assert value == {"message": "Hello World"}, f"Expected {{'message': 'Hello World'}}, got {value}"
        
        # Test namespace
        memory.set("ns_key", "namespace_value", "test_agent", namespace="test_ns")
        ns_value = memory.get("ns_key", namespace="test_ns")
        assert ns_value == "namespace_value", f"Namespace value mismatch: {ns_value}"
        
        # Test list keys
        keys = memory.list_keys()
        assert "test_key" in keys, f"test_key not found in keys: {keys}"
        
        print("  ✓ Set/Get operations")
        print("  ✓ Namespace support")
        print("  ✓ Key listing")
        
    finally:
        Path(db_path).unlink(missing_ok=True)

def test_agent_registry():
    """Test agent registry functionality."""
    print("👥 Testing Agent Registry...")
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    try:
        from ai_council.core.agent_registry import AgentRegistry, AgentStatus
        
        registry = AgentRegistry(db_path)
        
        # Test agent registration
        success = registry.register_agent(
            agent_id="test_agent",
            name="Test Agent",
            description="A test agent",
            capabilities=["test", "demo"]
        )
        assert success, "Failed to register agent"
        
        # Test agent retrieval
        agent = registry.get_agent("test_agent")
        assert agent is not None, "Failed to retrieve agent"
        assert agent["name"] == "Test Agent", f"Name mismatch: {agent['name']}"
        assert "test" in agent["capabilities"], f"Capabilities mismatch: {agent['capabilities']}"
        
        # Test heartbeat
        success = registry.heartbeat("test_agent", AgentStatus.ONLINE)
        assert success, "Failed to send heartbeat"
        
        # Test listing agents
        agents = registry.list_agents()
        assert len(agents) == 1, f"Expected 1 agent, got {len(agents)}"
        assert agents[0]["agent_id"] == "test_agent", f"Agent ID mismatch: {agents[0]['agent_id']}"
        
        print("  ✓ Agent registration")
        print("  ✓ Agent retrieval")
        print("  ✓ Heartbeat mechanism")
        print("  ✓ Agent listing")
        
    finally:
        Path(db_path).unlink(missing_ok=True)

def test_task_manager():
    """Test task manager functionality."""
    print("📋 Testing Task Manager...")
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    try:
        from ai_council.core.task_manager import TaskManager, TaskStatus, TaskPriority
        
        manager = TaskManager(db_path)
        
        # Test task creation
        task_id = manager.create_task(
            title="Test Task",
            description="A test task",
            task_type="test",
            required_capabilities=["test"],
            input_data={"message": "Hello"}
        )
        assert task_id is not None, "Failed to create task"
        
        # Test task retrieval
        task = manager.get_task(task_id)
        assert task is not None, "Failed to retrieve task"
        assert task["title"] == "Test Task", f"Title mismatch: {task['title']}"
        assert task["status"] == TaskStatus.PENDING.value, f"Status mismatch: {task['status']}"
        
        # Test task assignment
        success = manager.assign_task(task_id, "test_agent")
        assert success, "Failed to assign task"
        
        # Test task completion
        success = manager.complete_task(task_id, "test_agent", {"result": "completed"})
        assert success, "Failed to complete task"
        
        # Verify completion
        completed_task = manager.get_task(task_id)
        assert completed_task["status"] == TaskStatus.COMPLETED.value, f"Status not completed: {completed_task['status']}"
        
        print("  ✓ Task creation")
        print("  ✓ Task retrieval")
        print("  ✓ Task assignment")
        print("  ✓ Task completion")
        
    finally:
        Path(db_path).unlink(missing_ok=True)

async def test_coordination_engine():
    """Test coordination engine functionality."""
    print("⚙️ Testing Coordination Engine...")
    
    temp_dir = Path(tempfile.mkdtemp())
    
    try:
        from ai_council.core.coordination_engine import CoordinationEngine
        from ai_council.core.shared_memory import SharedMemory
        from ai_council.core.agent_registry import AgentRegistry
        from ai_council.core.task_manager import TaskManager
        
        # Create components with temporary databases
        shared_memory = SharedMemory(str(temp_dir / "shared_memory.db"))
        agent_registry = AgentRegistry(str(temp_dir / "agent_registry.db"))
        task_manager = TaskManager(str(temp_dir / "task_manager.db"))
        
        engine = CoordinationEngine(
            shared_memory=shared_memory,
            agent_registry=agent_registry,
            task_manager=task_manager,
            assignment_interval=1,  # Fast for testing
            cleanup_interval=10
        )
        
        # Test starting the engine
        engine.start()
        
        # Test agent registration
        success = engine.register_agent(
            agent_id="coord_test_agent",
            name="Coordination Test Agent",
            capabilities=["test", "coordination"]
        )
        assert success, "Failed to register agent"
        
        # Test task creation
        task_id = engine.create_task(
            title="Coordination Test Task",
            description="Test task for coordination",
            required_capabilities=["test"],
            input_data={"test": "data"}
        )
        assert task_id is not None, "Failed to create task"
        
        # Give the engine a moment to assign the task
        await asyncio.sleep(2)
        
        # Test system status
        status = engine.get_status()
        assert status["running"] is True, "Engine not reporting as running"
        
        health = engine.get_system_health()
        assert "health_score" in health, "Health score not found"
        assert "health_status" in health, "Health status not found"
        
        print("  ✓ Engine start/stop")
        print("  ✓ Agent registration")
        print("  ✓ Task creation")
        print("  ✓ System status")
        print("  ✓ Health monitoring")
        
        # Stop the engine
        engine.stop()
        
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

async def test_message_broker():
    """Test message broker functionality."""
    print("📨 Testing Message Broker...")
    
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as f:
        db_path = f.name
    
    try:
        from ai_council.communication.message_broker import MessageBroker, MessageType
        
        broker = MessageBroker(db_path, websocket_port=8766)  # Different port to avoid conflicts
        
        # Test message sending
        message_id = broker.send_message(
            sender_id="sender_agent",
            recipient_id="recipient_agent", 
            message_type=MessageType.DIRECT,
            subject="Test Message",
            content={"text": "Hello from sender"}
        )
        assert message_id is not None, "Failed to send message"
        
        # Test message retrieval
        messages = broker.get_messages("recipient_agent")
        assert len(messages) >= 1, f"Expected at least 1 message, got {len(messages)}"
        
        message = messages[0]
        assert message["subject"] == "Test Message", f"Subject mismatch: {message['subject']}"
        assert message["sender_id"] == "sender_agent", f"Sender mismatch: {message['sender_id']}"
        
        # Test message marking as read
        success = broker.mark_as_read(message_id, "recipient_agent")
        assert success, "Failed to mark message as read"
        
        # Test broadcast message
        broadcast_id = broker.send_message(
            sender_id="broadcaster",
            recipient_id=None,  # Broadcast
            message_type=MessageType.BROADCAST,
            subject="Broadcast Test",
            content={"announcement": "System update"}
        )
        assert broadcast_id is not None, "Failed to send broadcast message"
        
        print("  ✓ Direct messaging")
        print("  ✓ Message retrieval")
        print("  ✓ Read status tracking")
        print("  ✓ Broadcast messaging")
        
    finally:
        Path(db_path).unlink(missing_ok=True)

def test_configuration():
    """Test configuration system."""
    print("⚙️ Testing Configuration...")
    
    from ai_council.utils.config import ConfigManager, AICouncilConfig
    
    # Test default configuration
    config = AICouncilConfig()
    assert config.data_dir == "./data", f"Default data_dir mismatch: {config.data_dir}"
    assert config.monitoring.dashboard_port == 8000, f"Default port mismatch: {config.monitoring.dashboard_port}"
    
    # Test configuration manager
    manager = ConfigManager()
    loaded_config = manager.load_config()
    assert loaded_config.environment == "development", f"Environment mismatch: {loaded_config.environment}"
    
    print("  ✓ Default configuration")
    print("  ✓ Configuration loading")

async def main():
    """Run all tests."""
    print("🧪 AI Council Workspace - Basic Functionality Tests")
    print("=" * 60)
    
    try:
        # Test core components
        test_shared_memory()
        test_agent_registry() 
        test_task_manager()
        await test_coordination_engine()
        await test_message_broker()
        test_configuration()
        
        print("\n" + "=" * 60)
        print("🎉 All tests passed! The AI Council Workspace is working correctly.")
        print("✅ Core components are functional and ready for use.")
        
    except Exception as e:
        print(f"\n❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False
        
    return True

if __name__ == "__main__":
    success = asyncio.run(main())
    exit(0 if success else 1)