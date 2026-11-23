from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator


class ProjectInput(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra="forbid")

    name: str = Field(min_length=1, max_length=100)
    description: str = Field(default="", max_length=2000)
    base_url: str = Field(min_length=1, max_length=2048)

    @field_validator("base_url")
    @classmethod
    def validate_base_url(cls, value: str) -> str:
        url = HttpUrl(value)
        if url.username or url.password or url.query or url.fragment:
            raise ValueError("Base URL must not contain credentials, query parameters or fragments")
        normalized = str(url)
        if len(normalized) > 2048:
            raise ValueError("Normalized base URL must not exceed 2048 characters")
        return normalized


class ProjectRead(ProjectInput):
    model_config = ConfigDict(from_attributes=True)

    id: str
    created_at: str
    updated_at: str


class ProjectList(BaseModel):
    items: list[ProjectRead]
    total: int
    limit: int
    offset: int
