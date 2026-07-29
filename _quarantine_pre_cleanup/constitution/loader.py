import yaml
from pathlib import Path
from ai_company.registry.engine import registry

class ConstitutionLoader:
    def __init__(self):
        self.constitution_path = Path(".ai-company/constitution/rules.md")
        self.state_path = Path(".ai-company/state/current_sprint.yaml")
        
    def get_session_context(self) -> dict:
        """Loads the constitution rules, current sprint state, and registry."""
        rules = self.constitution_path.read_text(encoding="utf-8") if self.constitution_path.exists() else "No rules defined."
        
        state = {}
        if self.state_path.exists():
            with open(self.state_path, "r", encoding="utf-8") as f:
                state = yaml.safe_load(f) or {}
                
        reg_data = {}
        try:
            reg_data = registry.config.model_dump() if registry._config else {}
        except Exception:
            pass
            
        return {
            "constitution": rules,
            "state": state,
            "registry": reg_data
        }

constitution = ConstitutionLoader()