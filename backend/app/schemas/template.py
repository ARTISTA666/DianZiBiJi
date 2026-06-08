from pydantic import BaseModel


class TemplateRead(BaseModel):
    id: int
    name: str
    experiment_type: str
    schema_json: dict
    default_content_json: dict
    is_active: bool

    model_config = {"from_attributes": True}

