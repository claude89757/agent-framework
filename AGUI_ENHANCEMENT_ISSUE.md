# [Enhancement] Add Pydantic request model and OpenAPI tags support to AG-UI FastAPI endpoint

## Motivation and Context

The current implementation of `add_agent_framework_fastapi_endpoint()` in the AG-UI package has two limitations that affect API documentation and developer experience:

1. **Missing Request Body Schema**: The endpoint doesn't define a Pydantic model for the request body, which results in incomplete OpenAPI schema generation. This makes the Swagger UI less useful for API testing and documentation.

2. **No OpenAPI Tags Support**: Endpoints registered through this function are not categorized with tags, causing them to appear under the "default" category in OpenAPI documentation instead of being properly grouped.

## Problem Description

**Current Implementation:**
```python
@app.post(path)
async def agent_endpoint(request: Request):
    input_data = await request.json()
    # ...
```

**Issues:**
- The Swagger UI cannot display the proper request body structure
- No automatic request validation based on schema
- All AG-UI endpoints appear uncategorized in OpenAPI docs

## Proposed Solution

### 1. Add AGUIRequest Pydantic Model

Create a Pydantic model in `_types.py` to define the request structure:

```python
from typing import Any, Optional
from pydantic import BaseModel, Field


class AGUIRequest(BaseModel):
    """Request model for AG-UI endpoints."""
    
    messages: list[dict[str, Any]] = Field(
        ..., 
        description="AG-UI format messages array"
    )
    run_id: Optional[str] = Field(
        None, 
        description="Optional run identifier for tracking"
    )
    thread_id: Optional[str] = Field(
        None, 
        description="Optional thread identifier for conversation context"
    )
    state: Optional[dict[str, Any]] = Field(
        None, 
        description="Optional shared state for agentic generative UI"
    )
```

### 2. Add Tags Parameter Support

Update `add_agent_framework_fastapi_endpoint()` signature:

```python
def add_agent_framework_fastapi_endpoint(
    app: FastAPI,
    agent: AgentProtocol | AgentFrameworkAgent,
    path: str = "/",
    state_schema: Any | None = None,
    predict_state_config: dict[str, dict[str, str]] | None = None,
    allow_origins: list[str] | None = None,
    default_state: dict[str, Any] | None = None,
    tags: list[str] | None = None,  # NEW parameter
) -> None:
```

And use it in the decorator:

```python
@app.post(path, tags=tags or ["AG-UI"])
async def agent_endpoint(request_body: AGUIRequest):
    input_data = request_body.model_dump(exclude_none=True)
    # ... rest of the implementation
```

### 3. Export Constants

Add a default tags constant in `__init__.py`:

```python
DEFAULT_TAGS = ["AG-UI"]
```

## Benefits

1. **Better API Documentation**: Swagger UI will show complete request schema with field descriptions
2. **Automatic Validation**: Pydantic will validate incoming requests automatically
3. **Organized API Docs**: Endpoints will be properly grouped under "AG-UI" tag instead of "default"
4. **Improved Developer Experience**: Developers can see what fields are required/optional directly in the API docs
5. **Type Safety**: Better IDE support and type checking

## Testing Considerations

- Update existing tests that expect status code 200 for invalid JSON to expect 422 (Unprocessable Entity) due to Pydantic validation
- Add tests to verify OpenAPI schema generation includes the request model
- Add tests to verify tags appear correctly in the OpenAPI documentation

## Related Files

- `python/packages/ag-ui/agent_framework_ag_ui/_endpoint.py`
- `python/packages/ag-ui/agent_framework_ag_ui/_types.py`
- `python/packages/ag-ui/agent_framework_ag_ui/__init__.py`
- `python/packages/ag-ui/tests/test_endpoint.py`

## Additional Context

This enhancement aligns with FastAPI best practices and improves the overall quality of the AG-UI package's API surface. The changes are backwards compatible for existing code but will improve the OpenAPI documentation and validation behavior.

---

**Suggested Labels:**
- `enhancement`
- `python`
- `ag-ui`
- `documentation`
