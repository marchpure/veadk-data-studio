import json
from typing import Any

from agents import function_tool
from agents.run_context import RunContextWrapper

from server.utils.custom_logger import get_logger

logger = get_logger(__name__)

VALID_ACTIONS = {"start_plan", "start_step", "complete_step", "fail_step", "complete_plan"}

PLAN_GATE_ERROR = json.dumps(
    {
        "success": False,
        "error": "Plan mode is active and no plan has been proposed yet. You cannot call execution tools before proposing a plan. "
        "You may use exploration tools (search_datasets, get_dataset_schema_by_id, get_database_schema) to understand the data first. "
        "Then call emit_plan_status(action='start_plan', steps_json='[{\"name\": \"...\"},...]') to propose your plan.",
    }
)


def check_plan_gate(ctx: RunContextWrapper[Any]) -> str | None:
    if ctx.context.get("plan_mode") and not ctx.context.get("plan_started"):
        return PLAN_GATE_ERROR
    return None


@function_tool
async def emit_plan_status(
    ctx: RunContextWrapper[Any],
    action: str,
    steps_json: str = "",
    step_number: int = 0,
) -> str:
    """
    Emit plan status events to update the UI with execution progress.
    Use this for complex tasks (3+ steps) to show real-time progress.

    Args:
        ctx: Run context wrapper
        action: One of "start_plan", "start_step", "complete_step", "fail_step", "complete_plan"
        steps_json: JSON array of plan steps (required for start_plan).
                    Format: '[{"name": "Step name", "description": "Optional description"}, ...]'
        step_number: Current step number (1-indexed, required for start_step/complete_step/fail_step)

    Returns:
        JSON confirmation of the status event.

    Usage:
        1. Create plan with all steps:
           emit_plan_status(
               action="start_plan",
               steps_json='[{"name": "Query sales data"}, {"name": "Create chart"}, {"name": "Build dashboard"}]'
           )

        2. Execute each step:
           emit_plan_status(action="start_step", step_number=1)
           → Do the work for step 1
           emit_plan_status(action="complete_step", step_number=1)

        3. Repeat for each step, then finish:
           emit_plan_status(action="complete_plan")
    """
    notebook_id = ctx.context.get("notebook_id")

    logger.info(
        f"[PLAN] emit_plan_status called: action={action}, steps_json={steps_json[:100] if steps_json else 'None'}, step_number={step_number}"
    )

    if action not in VALID_ACTIONS:
        return json.dumps({"success": False, "error": f"Invalid action. Must be one of: {VALID_ACTIONS}"})

    event_data = {
        "action": action,
        "notebook_id": str(notebook_id) if notebook_id else None,
    }

    if action == "start_plan":
        if not steps_json:
            return json.dumps({"success": False, "error": "steps_json is required for start_plan"})

        try:
            steps = json.loads(steps_json)
            if not isinstance(steps, list) or len(steps) == 0:
                return json.dumps({"success": False, "error": "steps_json must be a non-empty JSON array"})
        except json.JSONDecodeError as e:
            return json.dumps({"success": False, "error": f"Invalid JSON in steps_json: {e}"})

        formatted_steps = []
        for idx, step in enumerate(steps):
            if isinstance(step, dict):
                formatted_steps.append(
                    {
                        "name": step.get("name", f"Step {idx + 1}"),
                        "description": step.get("description", ""),
                    }
                )
            elif isinstance(step, str):
                formatted_steps.append({"name": step, "description": ""})

        event_data["steps"] = formatted_steps
        event_data["total_steps"] = len(formatted_steps)

        ctx.context["plan_started"] = True
        ctx.context["current_plan"] = {
            "steps": formatted_steps,
            "total_steps": len(formatted_steps),
        }

        logger.info(f"[PLAN] Created plan with {len(formatted_steps)} steps")

        ctx.context["emit_plan_status"] = event_data
        return json.dumps(
            {
                "success": True,
                "action": action,
                "total_steps": len(formatted_steps),
                "steps": [s["name"] for s in formatted_steps],
                "message": f"Plan created with {len(formatted_steps)} steps. Present the plan to the user and wait for their approval before executing.",
            }
        )

    elif action in ("start_step", "complete_step", "fail_step"):
        if step_number <= 0:
            return json.dumps({"success": False, "error": "step_number is required for step actions"})

        event_data["step_number"] = step_number

        current_plan = ctx.context.get("current_plan", {})
        if current_plan:
            event_data["total_steps"] = current_plan.get("total_steps", 0)

        logger.info(f"[PLAN] {action} - step {step_number}")

        ctx.context["emit_plan_status"] = event_data

        steps = current_plan.get("steps", [])
        step_name = steps[step_number - 1]["name"] if step_number <= len(steps) else f"Step {step_number}"
        remaining = [s["name"] for s in steps[step_number:]]

        if action == "start_step":
            return json.dumps(
                {
                    "success": True,
                    "action": action,
                    "step_number": step_number,
                    "current_step": step_name,
                    "remaining_steps": remaining,
                    "message": f"Now execute step {step_number}: {step_name}. Follow this step exactly as planned.",
                }
            )
        else:
            return json.dumps(
                {
                    "success": True,
                    "action": action,
                    "step_number": step_number,
                    "completed_step": step_name,
                    "remaining_steps": remaining,
                    "message": f"Step {step_number} '{step_name}' completed. "
                    + (f"Next: {remaining[0]}" if remaining else "All steps done — call complete_plan."),
                }
            )

    elif action == "complete_plan":
        ctx.context.pop("current_plan", None)
        logger.info("[PLAN] Plan completed")

    ctx.context["emit_plan_status"] = event_data

    return json.dumps({"success": True, "action": action, "message": f"Plan status '{action}' emitted"})


def get_plan_tools():
    """Return list of plan-related tools."""
    return [emit_plan_status]
