import yaml
from pathlib import Path
from ai_company.registry.engine import registry
from ai_company.constitution.loader import constitution

class DashboardEngine:
    def __init__(self, output_dir: str = "dashboards"):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def render_sprint_dashboard(self):
        ctx = constitution.get_session_context()
        state = ctx.get("state", {}).get("current_sprint", {})
        
        html = f"""<!DOCTYPE html>
<html>
<head><title>AI Enterprise OS Dashboard</title></head>
<body>
    <h1>AI Enterprise OS - Sprint Dashboard</h1>
    <h2>Current Sprint: {state.get('goal', 'Unknown')}</h2>
    <h3>Milestone: {state.get('milestone', 'Unknown')}</h3>
    
    <h3>Active Tasks:</h3>
    <ul>
"""
        for task in state.get("active_tasks", []):
            html += f"        <li>{task}</li>\n"
            
        html += """    </ul>
</body>
</html>"""
        
        out_file = self.output_dir / "sprint_dashboard.html"
        out_file.write_text(html, encoding="utf-8")
        print(f"Generated: {out_file}")

dashboard_engine = DashboardEngine()