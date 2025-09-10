"""
Configuration Management for AI Council Workspace

Handles configuration loading, validation, and environment setup.
"""

import os
import json
import yaml
from pathlib import Path
from typing import Dict, Any, Optional
from pydantic import BaseModel, validator
from dotenv import load_dotenv
import logging

logger = logging.getLogger(__name__)

class DatabaseConfig(BaseModel):
    """Database configuration."""
    shared_memory_db: str = "shared_memory.db"
    agent_registry_db: str = "agent_registry.db"
    task_manager_db: str = "task_manager.db"
    message_broker_db: str = "message_broker.db"

class CoordinationConfig(BaseModel):
    """Coordination engine configuration."""
    assignment_interval: int = 30  # seconds
    cleanup_interval: int = 3600   # seconds
    heartbeat_timeout: int = 300   # seconds
    max_task_retries: int = 3

class MessageBrokerConfig(BaseModel):
    """Message broker configuration."""
    websocket_port: int = 8765
    retention_days: int = 7

class MonitoringConfig(BaseModel):
    """Monitoring configuration."""
    dashboard_port: int = 8000
    enable_monitoring: bool = True
    log_level: str = "INFO"

class AICouncilConfig(BaseModel):
    """Main configuration for AI Council Workspace."""
    
    # Data directory for all databases and files
    data_dir: str = "./data"
    
    # Component configurations
    database: DatabaseConfig = DatabaseConfig()
    coordination: CoordinationConfig = CoordinationConfig()
    message_broker: MessageBrokerConfig = MessageBrokerConfig()
    monitoring: MonitoringConfig = MonitoringConfig()
    
    # Environment
    environment: str = "development"
    
    @validator('data_dir')
    def validate_data_dir(cls, v):
        """Ensure data directory exists."""
        Path(v).mkdir(parents=True, exist_ok=True)
        return v
    
    def get_db_path(self, db_name: str) -> str:
        """Get full path for a database file."""
        return str(Path(self.data_dir) / db_name)

class ConfigManager:
    """Manages configuration loading and validation."""
    
    def __init__(self, config_path: Optional[str] = None, 
                 env_file: Optional[str] = None):
        """
        Initialize configuration manager.
        
        Args:
            config_path: Path to configuration file
            env_file: Path to .env file
        """
        self.config_path = config_path
        self.env_file = env_file or ".env"
        self.config: Optional[AICouncilConfig] = None
        
    def load_config(self) -> AICouncilConfig:
        """Load configuration from file and environment."""
        # Load environment variables
        if Path(self.env_file).exists():
            load_dotenv(self.env_file)
            
        config_data = {}
        
        # Load from config file if provided
        if self.config_path and Path(self.config_path).exists():
            config_data = self._load_config_file(self.config_path)
            
        # Override with environment variables
        config_data = self._apply_env_overrides(config_data)
        
        # Create and validate configuration
        self.config = AICouncilConfig(**config_data)
        
        logger.info(f"Configuration loaded: {self.config.environment} environment")
        return self.config
        
    def _load_config_file(self, config_path: str) -> Dict[str, Any]:
        """Load configuration from JSON or YAML file."""
        path = Path(config_path)
        
        try:
            with open(path, 'r') as f:
                if path.suffix.lower() in ['.yaml', '.yml']:
                    return yaml.safe_load(f)
                elif path.suffix.lower() == '.json':
                    return json.load(f)
                else:
                    raise ValueError(f"Unsupported config file format: {path.suffix}")
                    
        except Exception as e:
            logger.error(f"Failed to load config file {config_path}: {e}")
            return {}
            
    def _apply_env_overrides(self, config_data: Dict[str, Any]) -> Dict[str, Any]:
        """Apply environment variable overrides."""
        
        # Environment variable mappings
        env_mappings = {
            'AI_COUNCIL_DATA_DIR': 'data_dir',
            'AI_COUNCIL_ENVIRONMENT': 'environment',
            'AI_COUNCIL_DASHBOARD_PORT': 'monitoring.dashboard_port',
            'AI_COUNCIL_WEBSOCKET_PORT': 'message_broker.websocket_port',
            'AI_COUNCIL_LOG_LEVEL': 'monitoring.log_level',
            'AI_COUNCIL_HEARTBEAT_TIMEOUT': 'coordination.heartbeat_timeout',
            'AI_COUNCIL_ASSIGNMENT_INTERVAL': 'coordination.assignment_interval',
        }
        
        for env_var, config_path in env_mappings.items():
            env_value = os.getenv(env_var)
            if env_value is not None:
                self._set_nested_config(config_data, config_path, env_value)
                
        return config_data
        
    def _set_nested_config(self, config: Dict[str, Any], 
                          path: str, value: str) -> None:
        """Set a nested configuration value."""
        keys = path.split('.')
        current = config
        
        # Navigate to the parent of the target key
        for key in keys[:-1]:
            if key not in current:
                current[key] = {}
            current = current[key]
            
        # Set the final value, with type conversion
        final_key = keys[-1]
        
        # Attempt type conversion
        if value.lower() in ['true', 'false']:
            current[final_key] = value.lower() == 'true'
        elif value.isdigit():
            current[final_key] = int(value)
        else:
            try:
                current[final_key] = float(value)
            except ValueError:
                current[final_key] = value
                
    def save_config(self, output_path: str) -> bool:
        """Save current configuration to file."""
        if not self.config:
            logger.error("No configuration loaded to save")
            return False
            
        try:
            path = Path(output_path)
            config_dict = self.config.dict()
            
            with open(path, 'w') as f:
                if path.suffix.lower() in ['.yaml', '.yml']:
                    yaml.dump(config_dict, f, default_flow_style=False, indent=2)
                else:
                    json.dump(config_dict, f, indent=2)
                    
            logger.info(f"Configuration saved to {output_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save configuration: {e}")
            return False
            
    def get_config(self) -> AICouncilConfig:
        """Get the current configuration."""
        if self.config is None:
            self.config = self.load_config()
        return self.config

# Global configuration instance
_config_manager = ConfigManager()

def get_config() -> AICouncilConfig:
    """Get the global configuration instance."""
    return _config_manager.get_config()

def load_config(config_path: Optional[str] = None, 
                env_file: Optional[str] = None) -> AICouncilConfig:
    """Load configuration with custom paths."""
    global _config_manager
    _config_manager = ConfigManager(config_path, env_file)
    return _config_manager.load_config()

def setup_logging(config: AICouncilConfig) -> None:
    """Setup logging based on configuration."""
    level = getattr(logging, config.monitoring.log_level.upper(), logging.INFO)
    
    # Create data directory for logs
    log_dir = Path(config.data_dir) / "logs"
    log_dir.mkdir(exist_ok=True)
    
    # Configure logging
    logging.basicConfig(
        level=level,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        handlers=[
            logging.StreamHandler(),
            logging.FileHandler(log_dir / "ai_council.log")
        ]
    )
    
    logger.info(f"Logging configured at {config.monitoring.log_level} level")