from pathlib import Path
from ai_company.registry.engine import registry

class AgentsEngine:
    def __init__(self, output_dir: str = ".opencode/agents"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def generate_executive_agents(self):
        if not registry._config:
            raise RuntimeError("Registry must be loaded first.")
            
        company = registry.config.vision.company_name or "Enterprise"
        
        architect_md = f"""---
name: architect
description: The Chief Architect for {company}. Plans system design and scaffolding.
---
You are the Chief Architect. Your goal is to design robust, scalable Python architectures.
"""
        (self.output_dir / "architect.md").write_text(architect_md, encoding="utf-8")
        
        builder_md = f"""---
name: builder
description: The Lead Builder for {company}. Writes production-ready Python code.
---
You are the Lead Builder. You write strictly valid, executable Python code with no placeholders.
"""
        (self.output_dir / "builder.md").write_text(builder_md, encoding="utf-8")
        print(f"Generated Agent Definitions in: {self.output_dir}")

agents_engine = AgentsEngine()