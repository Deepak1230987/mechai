"""
Conversational Engine — LLM-based manufacturing Q&A.

Handles free-form user questions about the current machining plan.
The LLM always receives the full ConversationContext so it can reference
real feature IDs, datum faces, complexity scores, and risk warnings.

**Rules**:
  • Never modifies the plan — read-only explanations.
  • If the user requests a modification, returns a redirect signal
    so the caller routes to Phase B refinement engine.
  • All answers must reference concrete feature_id / operation_id values.
"""

from __future__ import annotations

import logging
from typing import Any

from pydantic import BaseModel, Field

from ai_service.conversation.context_builder import ConversationContext

logger = logging.getLogger("ai_service.conversation.conversational_engine")


# ── Response schema ───────────────────────────────────────────────────────────

class ConversationalAnswer(BaseModel):
    """Structured answer from the conversational engine."""

    answer: str = Field(..., description="Natural language answer referencing real IDs")
    referenced_feature_ids: list[str] = Field(default_factory=list)
    referenced_operation_ids: list[str] = Field(default_factory=list)
    is_modification_request: bool = Field(
        False,
        description="True if the user actually wants a plan change",
    )
    confidence: float = Field(1.0, ge=0.0, le=1.0)


# ── Modification-detection keywords ──────────────────────────────────────────

_MODIFICATION_SIGNALS = [
    "change", "modify", "reduce", "increase", "remove", "add", "replace",
    "switch to", "use instead", "swap", "can we use", "let's try",
    "minimize", "maximize", "optimize",
]


def _looks_like_modification(msg: str) -> bool:
    lower = msg.lower()
    return any(kw in lower for kw in _MODIFICATION_SIGNALS)


# ── Context → prompt builder ─────────────────────────────────────────────────

def _build_system_prompt(ctx: ConversationContext) -> str:
    """Build a system prompt that embeds the full manufacturing context."""

    feature_lines = []
    for f in ctx.features:
        fid = f.get("id", f.get("feature_id", "?"))
        ftype = f.get("type", "UNKNOWN")
        dims = f.get("dimensions", {})
        feature_lines.append(f"  - {fid}: {ftype} {dims}")

    op_lines = []
    for op in ctx.operations:
        op_lines.append(
            f"  - {op.id}: {op.type} on feature {op.feature_id}, "
            f"tool={op.tool_id}, time={op.estimated_time:.1f}s"
        )

    setup_lines = []
    for s in ctx.setups:
        setup_lines.append(
            f"  - {s.setup_id}: orientation={s.orientation}, "
            f"datum={s.datum_face_id}, ops={s.operations}"
        )

    risk_lines = []
    for r in ctx.risks:
        risk_lines.append(
            f"  - [{r.severity}] {r.code}: {r.message} "
            f"(affects {r.affected_operation_ids})"
        )

    tool_lines = []
    for t in ctx.tools:
        tool_lines.append(
            f"  - {t.id}: {t.type}, Ø{t.diameter}mm, "
            f"RPM {t.recommended_rpm_min}–{t.recommended_rpm_max}"
        )

    flag_lines = []
    for fl in ctx.manufacturability_flags:
        if isinstance(fl, dict):
            flag_lines.append(
                f"  - [{fl.get('severity', '?')}] {fl.get('code', '?')}: "
                f"{fl.get('message', '')}"
            )

    return (
        "You are a manufacturing engineering copilot. "
        "You MUST answer questions using ONLY the data below. "
        "Reference feature IDs, operation IDs, and tool IDs explicitly. "
        "Never invent geometry that is not listed. "
        "If the user asks for a plan CHANGE, respond ONLY with: "
        '"[MODIFICATION_REQUEST]" so it can be routed to the refinement engine.\n\n'
        f"── Part & Material ─────────────────────\n"
        f"Model: {ctx.model_id}\n"
        f"Material: {ctx.material}\n"
        f"Machine: {ctx.machine_type}\n"
        f"Complexity: {ctx.complexity_score:.2f} ({ctx.complexity_level})\n"
        f"Strategy: {ctx.selected_strategy}\n"
        f"Version: {ctx.version} (approval: {ctx.approval_status})\n\n"
        f"── Features ({len(ctx.features)}) ──────────────────────\n"
        + ("\n".join(feature_lines) or "  (none)") + "\n\n"
        f"── Setups ({len(ctx.setups)}) ───────────────────────\n"
        + ("\n".join(setup_lines) or "  (none)") + "\n\n"
        f"── Operations ({len(ctx.operations)}) ────────────────────\n"
        + ("\n".join(op_lines) or "  (none)") + "\n\n"
        f"── Tools ({len(ctx.tools)}) ─────────────────────────\n"
        + ("\n".join(tool_lines) or "  (none)") + "\n\n"
        f"── Risks ({len(ctx.risks)}) ─────────────────────────\n"
        + ("\n".join(risk_lines) or "  (none)") + "\n\n"
        f"── Manufacturability Flags ─────────────\n"
        + ("\n".join(flag_lines) or "  (none)") + "\n\n"
        f"── Stock Recommendation ───────────────\n"
        f"  {ctx.stock_recommendation}\n\n"
        f"── Datum Candidates ───────────────────\n"
        f"  {ctx.datum_candidates}\n\n"
        f"── Time / Cost Summary ────────────────\n"
        f"  Total time: {ctx.cost_time.total_time:.1f}s\n"
        f"  Operations: {ctx.cost_time.operation_count}\n"
        f"  Tools: {ctx.cost_time.tool_count}\n"
        f"  Setups: {ctx.cost_time.setup_count}\n"
    )


# ── Public API ────────────────────────────────────────────────────────────────

async def conversational_engine_answer(
    user_message: str,
    ctx: ConversationContext,
) -> ConversationalAnswer:
    """
    Generate a context-aware answer to a manufacturing question.

    If an LLM is configured and reachable, uses it.  Otherwise falls back
    to a deterministic template that summarises the plan.

    Returns
    -------
    ConversationalAnswer
        Contains the answer text plus any referenced feature / operation IDs.
    """

    # Quick check: is this really a modification request?
    if _looks_like_modification(user_message):
        return ConversationalAnswer(
            answer="[MODIFICATION_REQUEST]",
            is_modification_request=True,
            confidence=0.85,
        )

    system_prompt = _build_system_prompt(ctx)

    # ── Try LLM ──────────────────────────────────────────────────────────
    try:
        answer_text = await _call_llm(system_prompt, user_message)
        if answer_text:
            # Extract referenced IDs from the answer
            feat_ids = _extract_ids(answer_text, ctx.features, key="id")
            op_ids = _extract_ids_from_ops(answer_text, ctx.operations)
            return ConversationalAnswer(
                answer=answer_text,
                referenced_feature_ids=feat_ids,
                referenced_operation_ids=op_ids,
                confidence=0.9,
            )
    except Exception as exc:
        logger.warning("LLM conversational call failed: %s", exc)

    # ── Deterministic fallback ───────────────────────────────────────────
    answer_text = _deterministic_answer(user_message, ctx)
    feat_ids = _extract_ids(answer_text, ctx.features, key="id")
    op_ids = _extract_ids_from_ops(answer_text, ctx.operations)
    return ConversationalAnswer(
        answer=answer_text,
        referenced_feature_ids=feat_ids,
        referenced_operation_ids=op_ids,
        confidence=0.7,
    )


# ── LLM call ─────────────────────────────────────────────────────────────────

async def _call_llm(system_prompt: str, user_message: str) -> str | None:
    """Call the configured LLM with the manufacturing context."""
    from shared.config import get_settings

    settings = get_settings()
    api_key = getattr(settings, "GOOGLE_API_KEY", None) or getattr(settings, "OPENAI_API_KEY", None)
    if not api_key:
        return None

    try:
        from langchain_google_genai import ChatGoogleGenerativeAI
        from langchain_core.messages import SystemMessage, HumanMessage

        llm = ChatGoogleGenerativeAI(
            model="gemini-2.5-flash-lite",
            google_api_key=api_key,
            temperature=0.3,
            max_output_tokens=1024,
        )
        messages = [
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_message),
        ]
        result = await llm.ainvoke(messages)
        return result.content if result else None
    except ImportError:
        logger.debug("langchain_google_genai not installed — skipping LLM")
        return None


# ── Deterministic fallback ───────────────────────────────────────────────────

def _deterministic_answer(user_message: str, ctx: ConversationContext) -> str:
    """Template-based answer when LLM is unavailable."""
    lower = user_message.lower()

    if "setup" in lower or "flip" in lower:
        setup_desc = "; ".join(
            f"{s.setup_id} ({s.orientation}, datum={s.datum_face_id})"
            for s in ctx.setups
        )
        return (
            f"The plan uses {len(ctx.setups)} setup(s): {setup_desc}. "
            f"Multiple setups are needed when features require different "
            f"orientations or datum faces."
        )

    if "time" in lower or "duration" in lower:
        return (
            f"Total estimated machining time is {ctx.cost_time.total_time:.1f}s "
            f"across {ctx.cost_time.operation_count} operations in "
            f"{ctx.cost_time.setup_count} setup(s)."
        )

    if "cost" in lower or "price" in lower:
        cost = ctx.cost_time.total_cost
        if cost is not None:
            return f"Estimated total cost is ${cost:.2f}."
        return (
            f"Cost estimate is not yet computed. "
            f"Machining time is {ctx.cost_time.total_time:.1f}s."
        )

    if "risk" in lower or "warn" in lower:
        if not ctx.risks:
            return "No manufacturing risks have been flagged for this plan."
        risk_desc = "; ".join(
            f"[{r.severity}] {r.code} — {r.message}" for r in ctx.risks
        )
        return f"Current risks: {risk_desc}"

    if "complex" in lower:
        return (
            f"Complexity score is {ctx.complexity_score:.2f} "
            f"({ctx.complexity_level}). "
            f"This reflects feature count, depth ratios, and "
            f"multi-axis requirements."
        )

    if "tool" in lower:
        tool_desc = "; ".join(
            f"{t.id} ({t.type}, Ø{t.diameter}mm)" for t in ctx.tools
        )
        return f"Tools in current plan: {tool_desc}"

    if "operation" in lower or "step" in lower:
        op_desc = "; ".join(
            f"{op.id}: {op.type} on {op.feature_id}" for op in ctx.operations
        )
        return f"Operations: {op_desc}"

    if "feature" in lower or "hole" in lower or "pocket" in lower or "slot" in lower:
        feat_desc = "; ".join(
            f"{f.get('id', '?')}: {f.get('type', '?')}" for f in ctx.features
        )
        return f"Detected features: {feat_desc}"

    if "strateg" in lower:
        strat_desc = "; ".join(
            f"{s.name}: {s.description} (~{s.estimated_time:.0f}s)"
            for s in ctx.strategies
        )
        return (
            f"Selected strategy: {ctx.selected_strategy}. "
            f"Available: {strat_desc or 'CONSERVATIVE only'}"
        )

    # Generic summary
    return (
        f"Plan v{ctx.version} for model {ctx.model_id}: "
        f"{len(ctx.features)} features, {len(ctx.operations)} operations, "
        f"{len(ctx.setups)} setup(s), complexity {ctx.complexity_score:.2f} "
        f"({ctx.complexity_level}), strategy {ctx.selected_strategy}, "
        f"time {ctx.cost_time.total_time:.1f}s."
    )


# ── ID extraction helpers ────────────────────────────────────────────────────

def _extract_ids(
    text: str, items: list[dict], *, key: str = "id"
) -> list[str]:
    found: list[str] = []
    for item in items:
        fid = item.get(key) or item.get("feature_id", "")
        if fid and fid in text:
            found.append(fid)
    return found


def _extract_ids_from_ops(
    text: str, operations: list[OperationSpec],
) -> list[str]:
    from ai_service.schemas.machining_plan import OperationSpec  # noqa: F811

    found: list[str] = []
    for op in operations:
        if op.id in text:
            found.append(op.id)
    return found
