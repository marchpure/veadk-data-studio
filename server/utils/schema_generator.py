import json

from server.utils.custom_logger import get_logger

logger = get_logger(__name__)


def get_json_structure(obj, max_depth=10, current_depth=0):
    try:
        if current_depth >= max_depth:
            return "..."

        if obj is None:
            return None

        if isinstance(obj, list):
            if not obj:
                return []
            structures = [get_json_structure(item, max_depth, current_depth + 1) for item in obj[:100]]
            return [merge_structures(structures)]

        if isinstance(obj, dict):
            return {key: get_json_structure(value, max_depth, current_depth + 1) for key, value in obj.items()}

        return type(obj).__name__.replace("bool", "boolean").replace("int", "integer").replace("float", "number")
    except Exception as e:
        logger.error(
            f"Failed to get JSON structure: {str(e)}",
            exc_info=True,
            posthog_context={
                "function": "get_json_structure",
                "current_depth": current_depth,
                "obj_type": type(obj).__name__,
            },
        )
        return "error"


def merge_structures(structures):
    try:
        if not structures:
            return None

        first = structures[0]
        if all(s == first for s in structures):
            return first

        if all(isinstance(s, dict) for s in structures):
            merged = {}
            all_keys = set()
            for s in structures:
                all_keys.update(s.keys())

            for key in all_keys:
                values = [s.get(key) for s in structures if key in s]
                if len({str(v) for v in values}) == 1:
                    merged[key] = values[0]
                else:
                    merged[key] = f"optional({values[0]})"
            return merged

        return f"mixed({first})"
    except Exception as e:
        logger.error(
            f"Failed to merge structures: {str(e)}",
            exc_info=True,
            posthog_context={"function": "merge_structures", "structure_count": len(structures) if structures else 0},
        )
        return None


def get_structure_from_string(json_string):
    try:
        return get_json_structure(json.loads(json_string))
    except json.JSONDecodeError as e:
        logger.error(
            f"Failed to parse JSON string: {str(e)}",
            exc_info=True,
            posthog_context={
                "function": "get_structure_from_string",
                "json_string_length": len(json_string) if json_string else 0,
            },
        )
        return None
    except Exception as e:
        logger.error(
            f"Failed to get structure from string: {str(e)}",
            exc_info=True,
            posthog_context={"function": "get_structure_from_string"},
        )
        return None


def generate_schema_from_response(response_data):
    try:
        return get_json_structure(response_data)
    except Exception as e:
        logger.error(
            f"Failed to generate schema from response: {str(e)}",
            exc_info=True,
            posthog_context={
                "function": "generate_schema_from_response",
                "response_type": type(response_data).__name__,
            },
        )
        return None
