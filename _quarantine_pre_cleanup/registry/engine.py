import yaml
from pathlib import Path
from typing import Optional
from ai_company.models.company import CompanyConfig

class RegistryEngine:
    _instance: Optional['RegistryEngine'] = None
    _config: Optional[CompanyConfig] = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(RegistryEngine, cls).__new__(cls)
        return cls._instance

    def load(self, config_path: Path) -> CompanyConfig:
        if not config_path.exists():
            raise FileNotFoundError(f"Config file not found: {config_path}")
        
        with open(config_path, "r", encoding="utf-8") as f:
            raw_data = yaml.safe_load(f)
            
        self._config = CompanyConfig(**raw_data)
        return self._config

    @property
    def config(self) -> CompanyConfig:
        if self._config is None:
            raise RuntimeError("Registry not initialized. Call load() first.")
        return self._config

# Singleton instance
registry = RegistryEngine()