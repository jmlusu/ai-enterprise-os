from pydantic import BaseModel, ConfigDict
from typing import Optional

class VisionConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    description: Optional[str] = None
    company_name: Optional[str] = None

class CompanyConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    vision: Optional[VisionConfig] = None