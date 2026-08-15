from typing import Any


def unwrap_nested_schema(schema_data: dict[str, Any], preserve_metadata: bool = True) -> dict[str, Any]:
    """
    Unwrap nested schema structures while handling MongoDB vs SQL differences.

    MongoDB connections can have triple-nested schemas due to:
    1. Schema extraction wrapping in {schema: ...}
    2. Cache storage wrapping in {schema: ...}
    3. API response wrapping in {datasource_type, schema: ...}

    Args:
        schema_data: Schema dict that may have nested "schema" keys
        preserve_metadata: If True, keep root-level metadata fields
                          (datasource_type, database_type, datasource_name, database_name)

    Returns:
        Unwrapped schema dict with consistent structure

    Raises:
        ValueError: If schema_data is not a dict
    """
    if not isinstance(schema_data, dict):
        raise ValueError(f"schema_data must be a dict, got {type(schema_data).__name__}")

    if not schema_data:
        return {}

    has_datasource_metadata = "datasource_type" in schema_data or "database_type" in schema_data

    if preserve_metadata and has_datasource_metadata:
        return schema_data

    if not has_datasource_metadata and "schema" in schema_data:
        inner = schema_data.get("schema")

        if not isinstance(inner, dict):
            return {}

        max_depth = 3
        current = inner
        for _ in range(max_depth):
            if isinstance(current, dict) and "schema" in current:
                next_level = current.get("schema")
                if isinstance(next_level, dict):
                    current = next_level
                else:
                    break
            else:
                break

        return current if isinstance(current, dict) else {}

    return schema_data
