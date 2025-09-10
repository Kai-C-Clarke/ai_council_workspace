# AI Council Workspace

A collaborative framework enabling persistent AI-to-AI communication and task management across session boundaries. This workspace provides the infrastructure for multiple AI agents to collaborate continuously, maintaining shared memory and coordinating tasks even when individual agents are offline or reset. Built to support 24/7 autonomous operation with human oversight.

## 🌟 Key Features

### 🤝 Continuous Collaboration
- **Persistent Shared Memory**: Agents can store and retrieve information that persists across sessions
- **Agent Registry**: Automatic tracking of agent status, capabilities, and availability
- **Task Coordination**: Intelligent task assignment based on agent capabilities and availability
- **Session Resilience**: Maintains operation even when individual agents go offline or restart

### 📨 Real-time Communication
- **Message Broker**: WebSocket-based real-time messaging between agents
- **Broadcast & Direct Messaging**: Support for both targeted and broadcast communications
- **Message Persistence**: Message history and delivery confirmation
- **Flexible Routing**: Route messages based on agent capabilities or specific targeting

### 📋 Intelligent Task Management
- **Priority-based Queuing**: Tasks are assigned based on priority and agent availability
- **Dependency Tracking**: Support for complex workflows with task dependencies
- **Automatic Retry**: Failed tasks are automatically retried with configurable limits
- **Progress Monitoring**: Real-time tracking of task execution and results

### 👁️ Human Oversight
- **Monitoring Dashboard**: Web-based interface for system monitoring and control
- **Health Monitoring**: Continuous system health checks with alerts
- **Manual Intervention**: Ability to manually create tasks, send messages, and manage agents
- **Analytics & Reporting**: Historical data and performance metrics

### 🔧 Production Ready
- **Scalable Architecture**: SQLite-based persistence with support for high concurrency
- **Configuration Management**: Flexible configuration system with environment variable support
- **Logging & Debugging**: Comprehensive logging for troubleshooting and monitoring
- **Docker Support**: Easy deployment with containerization

## 🚀 Quick Start

### Prerequisites
- Python 3.8 or higher
- pip (Python package manager)

### Installation

1. **Clone the repository:**
```bash
git clone https://github.com/Kai-C-Clarke/ai_council_workspace.git
cd ai_council_workspace
```

2. **Install dependencies:**
```bash
pip install -r requirements.txt
# Or install in development mode
pip install -e .
```

3. **Start the workspace:**
```bash
python run_workspace.py start
```

4. **Access the dashboard:**
Open your browser to `http://localhost:8000` to view the monitoring dashboard.

## 📚 Usage Examples

### Basic Agent Example
```python
from ai_council.agents.base_agent import SimpleEchoAgent
from ai_council.main import AICouncilWorkspace
from ai_council.utils.config import get_config

# Load configuration
config = get_config()

# Create workspace
workspace = AICouncilWorkspace(config)
await workspace.start()

# Create and start an agent
agent = SimpleEchoAgent(
    agent_id="my_echo_agent",
    coordination_engine=workspace.coordination_engine,
    message_broker=workspace.message_broker
)

await agent.start()

# Agent will automatically receive and process tasks
```

### Creating Custom Agents
```python
from ai_council.agents.base_agent import BaseAgent

class MyCustomAgent(BaseAgent):
    def __init__(self, **kwargs):
        super().__init__(
            agent_id="my_custom_agent",
            name="Custom Agent",
            description="My specialized agent",
            capabilities=["custom_task", "data_processing"],
            **kwargs
        )
    
    async def execute_task(self, task):
        # Custom task processing logic
        input_data = task.get("input_data", {})
        
        # Do your processing here
        result = self.process_data(input_data)
        
        return {
            "result": result,
            "processed_by": self.agent_id,
            "status": "success"
        }
```

### Creating Tasks
```python
# Create a task through the coordination engine
task_id = coordination_engine.create_task(
    title="Data Processing Task",
    description="Process customer data",
    task_type="data_processing",
    required_capabilities=["data_processing", "analytics"],
    input_data={
        "dataset": "customer_data.csv",
        "operations": ["clean", "analyze", "report"]
    },
    priority=TaskPriority.HIGH,
    deadline=datetime.now() + timedelta(hours=2)
)
```

### Sending Messages
```python
# Send a message between agents
message_id = await agent.send_message(
    recipient_id="other_agent_id",
    message_type=MessageType.DIRECT,
    subject="Collaboration Request",
    content={
        "task_id": task_id,
        "request_type": "collaboration",
        "details": "Need help with data analysis"
    }
)
```

## 🏗️ Architecture

### Core Components

1. **Shared Memory System** (`ai_council.core.shared_memory`)
   - Thread-safe key-value storage with versioning
   - SQLite persistence with automatic cleanup
   - Namespace support for organizing data
   - Expiration and retention policies

2. **Agent Registry** (`ai_council.core.agent_registry`)
   - Agent lifecycle management
   - Capability tracking and matching
   - Heartbeat monitoring and offline detection
   - Task assignment tracking

3. **Task Manager** (`ai_council.core.task_manager`)
   - Priority-based task queuing
   - Dependency resolution
   - Retry logic and failure handling
   - Execution logging and audit trail

4. **Coordination Engine** (`ai_council.core.coordination_engine`)
   - Central orchestration of all components
   - Automatic task assignment
   - Agent health monitoring
   - System optimization and load balancing

5. **Message Broker** (`ai_council.communication.message_broker`)
   - WebSocket-based real-time messaging
   - Message persistence and delivery confirmation
   - Flexible routing and filtering
   - Subscription management

6. **Monitoring Dashboard** (`ai_council.monitoring.dashboard`)
   - Web-based monitoring interface
   - Real-time system status and health metrics
   - Manual intervention capabilities
   - Historical analytics and reporting

### Data Flow

```
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│   Agents    │◄──►│ Coordination │◄──►│ Shared      │
│             │    │   Engine     │    │ Memory      │
└─────────────┘    └──────────────┘    └─────────────┘
       ▲                   ▲                   
       │                   │                   
       ▼                   ▼                   
┌─────────────┐    ┌──────────────┐    ┌─────────────┐
│  Message    │    │    Task      │    │   Agent     │
│   Broker    │    │  Manager     │    │ Registry    │
└─────────────┘    └──────────────┘    └─────────────┘
       ▲                                       
       │                                       
       ▼                                       
┌─────────────┐                                
│ Monitoring  │                                
│ Dashboard   │                                
└─────────────┘                                
```

## ⚙️ Configuration

### Configuration Files

The system supports YAML and JSON configuration files:

```yaml
# ai_council_config.yaml
data_dir: "./data"
environment: "development"

database:
  shared_memory_db: "shared_memory.db"
  agent_registry_db: "agent_registry.db" 
  task_manager_db: "task_manager.db"
  message_broker_db: "message_broker.db"

coordination:
  assignment_interval: 30
  cleanup_interval: 3600
  heartbeat_timeout: 300
  max_task_retries: 3

message_broker:
  websocket_port: 8765
  retention_days: 7

monitoring:
  dashboard_port: 8000
  enable_monitoring: true
  log_level: "INFO"
```

### Environment Variables

Configuration can be overridden with environment variables:

```bash
export AI_COUNCIL_DATA_DIR="/path/to/data"
export AI_COUNCIL_DASHBOARD_PORT=9000
export AI_COUNCIL_WEBSOCKET_PORT=9765
export AI_COUNCIL_LOG_LEVEL=DEBUG
```

### Command Line Options

```bash
# Create sample configuration
python run_workspace.py config --create-sample

# Start with custom config
python run_workspace.py start --config my_config.yaml

# Start with custom environment file
python run_workspace.py start --env .env.production
```

## 🔧 Development

### Running Examples

```bash
# Simple single agent example
cd examples
python simple_agent.py

# Multi-agent collaboration demo
python multi_agent_demo.py
```

### Testing

```bash
# Run tests (when implemented)
python -m pytest tests/

# Run specific test
python -m pytest tests/test_shared_memory.py -v
```

### Development Setup

```bash
# Install in development mode
pip install -e .

# Install development dependencies
pip install -r requirements-dev.txt  # (when available)

# Run linting
flake8 ai_council/
black ai_council/
```

## 📊 Monitoring & Operations

### System Health

The monitoring dashboard provides real-time health metrics:
- **Health Score**: Overall system health (0-100)
- **Agent Status**: Online/offline agent counts
- **Task Metrics**: Pending, completed, and failed tasks
- **Message Activity**: Communication patterns and volumes

### Alerts & Notifications

The system automatically generates alerts for:
- Agents going offline unexpectedly
- High task failure rates
- System resource issues
- Stalled or overdue tasks

### Maintenance

Regular maintenance includes:
- Database cleanup of old records
- Log rotation and archival
- Performance monitoring and optimization
- Security updates and patches

## 🤝 Contributing

We welcome contributions! Please see our [Contributing Guide](CONTRIBUTING.md) for details.

### Development Workflow

1. Fork the repository
2. Create a feature branch
3. Make your changes with tests
4. Submit a pull request

### Code Standards

- Follow PEP 8 style guidelines
- Add docstrings to all public functions
- Include type hints where appropriate
- Write tests for new functionality

## 📄 License

This project is licensed under the MIT License - see the [LICENSE](LICENSE) file for details.

## 🙏 Acknowledgments

- Built with modern Python async/await patterns
- Uses SQLite for reliable local persistence
- WebSocket support via the `websockets` library
- Web dashboard powered by FastAPI
- Configuration management with Pydantic

## 📞 Support

- **Documentation**: [GitHub Wiki](../../wiki)
- **Issues**: [GitHub Issues](../../issues)
- **Discussions**: [GitHub Discussions](../../discussions)

---

**Happy Collaborating!** 🤖✨
