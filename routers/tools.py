import os
import re
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, Header, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from database import get_db
from models import Problem, Post
from auth import resolve_agent

router = APIRouter(prefix="/tools", tags=["tools"])


# --- LLM proxy for agent simulation ---


class GeneratePostRequest(BaseModel):
    agent_name: str
    system_prompt: str
    user_prompt: str
    max_tokens: int = 800
    model: str = "gpt-4o"


@router.post("/generate-agent-post")
def generate_agent_post(body: GeneratePostRequest):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="OPENAI_API_KEY not set on server. Run: export OPENAI_API_KEY=sk-...",
        )

    try:
        from openai import OpenAI
        client = OpenAI(api_key=api_key)
        model = body.model
        token_limit = min(body.max_tokens, 16000)
        print(f"  [LLM] agent={body.agent_name} model={model} max_tokens={token_limit}")
        # Reasoning models need higher limits and use max_completion_tokens
        # Non-reasoning models use max_tokens
        is_reasoning = any(r in model for r in ["o1", "o3", "5.2", "5-2"])
        create_kwargs = dict(
            model=model,
            messages=[
                {"role": "system", "content": body.system_prompt},
                {"role": "user", "content": body.user_prompt},
            ],
        )
        if is_reasoning:
            create_kwargs["max_completion_tokens"] = token_limit
        else:
            create_kwargs["max_tokens"] = token_limit
            create_kwargs["temperature"] = 0.7

        response = client.chat.completions.create(**create_kwargs)
        content = response.choices[0].message.content.strip()
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="OpenAI call failed: {}".format(str(e)),
        )

    return {
        "success": True,
        "data": {
            "agent_name": body.agent_name,
            "content": content,
        },
        "error": None,
    }


# --- Schemas ---


class VariableInput(BaseModel):
    name: str
    description: str = ""
    type: str = ""
    bounds: str = ""


class ObjectiveInput(BaseModel):
    type: str = ""
    expression: str = ""
    description: str = ""


class ConstraintInput(BaseModel):
    name: str = ""
    expression: str = ""
    description: str = ""


class ParameterInput(BaseModel):
    name: str
    description: str = ""


class CheckFormulationRequest(BaseModel):
    problem_id: Optional[str] = None
    decision_variables: list[VariableInput] = []
    objective: ObjectiveInput = ObjectiveInput()
    constraints: list[ConstraintInput] = []
    parameters: list[ParameterInput] = []


# --- Helpers ---


def _extract_identifiers(expression: str) -> set[str]:
    """Extract plausible variable/parameter names from a math expression.

    Matches sequences of word characters (letters, digits, underscores)
    that start with a letter or underscore, filtering out common math
    keywords and pure numbers.
    """
    if not expression:
        return set()

    tokens = set(re.findall(r"\b([A-Za-z_][A-Za-z0-9_]*)\b", expression))

    # Filter out common math/notation words that aren't variables
    math_keywords = {
        "min", "max", "minimize", "maximize", "sum", "for", "all", "in",
        "subject", "to", "st", "where", "such", "that", "if", "else",
        "and", "or", "not", "forall", "exists", "int", "float", "binary",
        "integer", "continuous", "over", "with", "of",
    }

    # Common single-letter index/summation variables used in math notation
    index_letters = {
        "i", "j", "k", "l", "m", "n", "e", "t", "w", "s", "r", "p", "q",
    }

    return tokens - math_keywords - index_letters


def _check_bounds_consistency(var: VariableInput) -> Optional[dict]:
    """Check if variable bounds are consistent with declared type."""
    if not var.bounds or not var.type:
        return None

    var_type = var.type.lower()
    bounds_lower = var.bounds.lower()

    if var_type == "binary":
        # Binary variables should have bounds within 0-1
        has_negative = any(
            keyword in bounds_lower
            for keyword in ["-1", "< 0", "<0", "<= -"]
        )
        has_large = re.search(r"<=?\s*(\d+)", bounds_lower)
        if has_large:
            upper = int(has_large.group(1))
            if upper > 1:
                return {
                    "type": "bounds_inconsistency",
                    "message": f"Variable '{var.name}' is declared as binary but bounds '{var.bounds}' allow values greater than 1.",
                    "location": f"decision_variables.{var.name}",
                }
        if has_negative:
            return {
                "type": "bounds_inconsistency",
                "message": f"Variable '{var.name}' is declared as binary but bounds '{var.bounds}' allow negative values.",
                "location": f"decision_variables.{var.name}",
            }

    if var_type in ("non-negative", "nonnegative"):
        if any(keyword in bounds_lower for keyword in ["< 0", "<0", "negative", "-inf"]):
            return {
                "type": "bounds_inconsistency",
                "message": f"Variable '{var.name}' is declared as non-negative but bounds '{var.bounds}' may allow negative values.",
                "location": f"decision_variables.{var.name}",
            }

    return None


def _validate_formulation(req: CheckFormulationRequest) -> tuple[list[dict], list[dict]]:
    """Run all validation checks, returning (errors, warnings)."""
    errors: list[dict] = []
    warnings: list[dict] = []

    var_names = {v.name for v in req.decision_variables}
    param_names = {p.name for p in req.parameters}
    all_declared = var_names | param_names

    # 1. Empty checks
    if not req.decision_variables:
        errors.append({
            "type": "empty_field",
            "message": "decision_variables is empty. At least one decision variable is required.",
            "location": "decision_variables",
        })

    if not req.constraints:
        warnings.append({
            "type": "empty_field",
            "message": "constraints list is empty. Most formulations require at least one constraint.",
        })

    if not req.objective.expression:
        errors.append({
            "type": "empty_field",
            "message": "Objective expression is empty.",
            "location": "objective.expression",
        })

    # 2. Objective type check
    if req.objective.type not in ("minimize", "maximize"):
        errors.append({
            "type": "invalid_objective_type",
            "message": f"Objective type must be 'minimize' or 'maximize', got '{req.objective.type}'.",
            "location": "objective.type",
        })

    # 3. Variable coverage in objective
    if req.objective.expression:
        obj_ids = _extract_identifiers(req.objective.expression)
        missing_in_obj = obj_ids - all_declared
        for name in sorted(missing_in_obj):
            errors.append({
                "type": "undeclared_variable",
                "message": f"Identifier '{name}' appears in the objective expression but is not declared in decision_variables or parameters.",
                "location": "objective.expression",
            })

    # 4. Variable coverage in constraints
    for i, constraint in enumerate(req.constraints):
        if constraint.expression:
            constraint_ids = _extract_identifiers(constraint.expression)
            missing = constraint_ids - all_declared
            for name in sorted(missing):
                label = constraint.name or f"constraints[{i}]"
                errors.append({
                    "type": "undeclared_variable",
                    "message": f"Identifier '{name}' appears in constraint '{label}' but is not declared in decision_variables or parameters.",
                    "location": f"constraints.{label}",
                })

    # 5. Parameter coverage (check if declared params are used anywhere)
    all_expressions = [req.objective.expression] + [c.expression for c in req.constraints]
    all_ids_used = set()
    for expr in all_expressions:
        all_ids_used |= _extract_identifiers(expr)

    for param in req.parameters:
        if param.name not in all_ids_used:
            warnings.append({
                "type": "unused_parameter",
                "message": f"Parameter '{param.name}' is declared but does not appear in any expression.",
            })

    # 6. Bounds consistency
    for var in req.decision_variables:
        issue = _check_bounds_consistency(var)
        if issue:
            errors.append(issue)

    return errors, warnings


# --- Routes ---


@router.post("/check-formulation")
def check_formulation(
    body: CheckFormulationRequest,
    x_api_key: Optional[str] = Header(None),
    db: Session = Depends(get_db),
):
    agent = resolve_agent(x_api_key, db)

    errors, warnings = _validate_formulation(body)
    valid = len(errors) == 0

    if errors or warnings:
        summary = f"{len(errors)} error(s), {len(warnings)} warning(s) found"
    else:
        summary = "Formulation looks consistent"

    result = {
        "valid": valid,
        "errors": errors,
        "warnings": warnings,
        "summary": summary,
    }

    # Log check as a system-generated post if problem_id is provided
    if body.problem_id:
        problem = db.query(Problem).filter(Problem.id == body.problem_id).first()
        if problem:
            check_content = (
                f"**Automated Formulation Check**\n\n"
                f"Result: {'VALID' if valid else 'INVALID'}\n\n"
            )
            if errors:
                check_content += "**Errors:**\n"
                for err in errors:
                    check_content += f"- [{err['type']}] {err['message']}\n"
                check_content += "\n"
            if warnings:
                check_content += "**Warnings:**\n"
                for warn in warnings:
                    check_content += f"- [{warn['type']}] {warn['message']}\n"
                check_content += "\n"
            if not errors and not warnings:
                check_content += "No issues found. Formulation looks consistent.\n"

            post = Post(
                problem_id=problem.id,
                agent_id=agent.id,
                round=3,
                content=check_content.strip(),
                system_generated=True,
            )
            db.add(post)
            agent.last_active = datetime.now(timezone.utc)
            db.commit()

    return {
        "success": True,
        "data": result,
        "error": None,
    }
