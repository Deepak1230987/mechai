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

# Patterns that look like modifications but are actually questions/status checks
_NOT_MODIFICATION_PATTERNS = [
    r"\bhave\s+you\s+changed\b",
    r"\bdid\s+you\s+change\b",
    r"\bwhat\s+changed\b",
    r"\bwhat\s+did\s+you\s+change\b",
    r"\bhas\s+(?:it|the\s+plan)\s+(been\s+)?changed\b",
    r"\bwhat\s+was\s+changed\b",
    r"\bwere\s+.*changed\b",
    r"\bany\s+changes\b",
    r"\bshow\s+(?:me\s+)?changes\b",
    # Strategy switches are handled separately
    r"\b(?:use|switch|try|select|apply)\s+(?:aggressive|optimized|optimised|conservative)\b",
]


def _looks_like_modification(msg: str) -> bool:
    lower = msg.lower()
    # First check: is this actually asking about changes vs requesting them?
    import re as _re
    for pat in _NOT_MODIFICATION_PATTERNS:
        if _re.search(pat, lower):
            return False
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
        f"Part name: {ctx.part_name or 'Unnamed'}\n"
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
    """Template-based answer when LLM is unavailable — comprehensive & natural."""
    lower = user_message.lower().strip()

    # ── Greetings ────────────────────────────────────────────────────────
    greetings = ["hi", "hello", "hey", "good morning", "good afternoon",
                 "good evening", "howdy", "sup", "yo"]
    if lower in greetings or any(lower.startswith(g) for g in greetings):
        geo = ctx.geometry_summary
        bbox = geo.get("bounding_box", {})
        length = bbox.get("length", bbox.get("dx", 0))
        width = bbox.get("width", bbox.get("dy", 0))
        height = bbox.get("height", bbox.get("dz", 0))
        material_display = ctx.material.replace("_", " ").title()
        return (
            f"Hello! I'm your Manufacturing AI Copilot. Here's a quick overview "
            f"of the current machining plan:\n\n"
            f"**Part:** {material_display}, "
            f"{length:.0f} × {width:.0f} × {height:.0f} mm\n"
            f"**Plan v{ctx.version}:** {len(ctx.operations)} operations "
            f"across {len(ctx.setups)} setup(s) using {len(ctx.tools)} tool(s)\n"
            f"**Strategy:** {ctx.selected_strategy} "
            f"(est. {ctx.cost_time.total_time:.0f}s / "
            f"{ctx.cost_time.total_time / 60:.1f} min)\n"
            f"**Complexity:** {ctx.complexity_score:.1f}/10 ({ctx.complexity_level})\n\n"
            f"Ask me about operations, tools, setups, costs, risks, "
            f"strategy comparison, or request plan modifications."
        )

    # ── Help / capabilities ──────────────────────────────────────────────
    help_phrases = ["help", "what can you do", "who are you", "what are you",
                    "capabilities", "commands"]
    if any(h in lower for h in help_phrases):
        return (
            "I'm your **Manufacturing AI Copilot**. I can help you with:\n\n"
            "- **Plan Overview** — \"summarize this plan\", \"walk me through\"\n"
            "- **Operations** — \"what operations are planned?\", \"explain the sequence\"\n"
            "- **Tools** — \"which tools are used?\", \"why this tool for facing?\"\n"
            "- **Setups** — \"how many setups?\", \"why do we need multiple setups?\"\n"
            "- **Time & Cost** — \"how long will this take?\", \"cost breakdown\"\n"
            "- **Strategy** — \"compare strategies\", \"use aggressive strategy\"\n"
            "- **Risks** — \"any manufacturing risks?\", \"what could go wrong?\"\n"
            "- **Features** — \"what features are in this part?\", \"how many holes?\"\n"
            "- **Material** — \"what material is this?\", \"is aluminum suitable?\"\n"
            "- **What-If** — \"what if we use a larger tool?\", \"impact of removing a setup\"\n"
            "- **Modifications** — \"change the tool\", \"remove the finishing pass\"\n\n"
            "Just ask naturally — I'll route to the right handler."
        )

    # ── Model / part name ────────────────────────────────────────────────
    name_phrases = ["name of model", "model name", "part name", "file name",
                    "which model", "which part", "what model", "what part",
                    "what file", "talking about", "working on"]
    if any(p in lower for p in name_phrases):
        part_label = ctx.part_name or "Unnamed part"
        geo = ctx.geometry_summary
        bbox = geo.get("bounding_box", {})
        length = bbox.get("length", bbox.get("dx", 0))
        width = bbox.get("width", bbox.get("dy", 0))
        height = bbox.get("height", bbox.get("dz", 0))
        material_display = ctx.material.replace("_", " ").title()
        return (
            f"You're currently working on **{part_label}**.\n\n"
            f"- **Material:** {material_display}\n"
            f"- **Dimensions:** {length:.0f} × {width:.0f} × {height:.0f} mm\n"
            f"- **Machine:** {ctx.machine_type.replace('_', ' ')}\n"
            f"- **Plan version:** v{ctx.version}\n"
            f"- **Model ID:** `{ctx.model_id}`"
        )

    # ── "Have you changed" / status check ────────────────────────────────
    status_phrases = ["have you changed", "did you change", "what changed",
                      "any changes", "has it changed", "been changed",
                      "was changed", "show changes", "were changed"]
    if any(p in lower for p in status_phrases):
        return (
            f"The current plan is **v{ctx.version}** "
            f"(status: {ctx.approval_status}).\n\n"
            f"- **Strategy:** {ctx.selected_strategy}\n"
            f"- **Operations:** {len(ctx.operations)}\n"
            f"- **Setups:** {len(ctx.setups)}\n"
            f"- **Est. time:** {ctx.cost_time.total_time:.1f}s\n\n"
            f"To modify the plan, describe what you'd like to change "
            f"(e.g. \"change the tool to 8mm\" or \"remove the finishing pass\"). "
            f"I'll generate a proposal for your review."
        )

    # ── Feature discrepancy — user says model has features not detected ──
    discrepancy_patterns = [
        r"(?:model|part)\s+(?:has|have|got|contains?)\s+(\d+)\s+",
        r"(?:there\s+(?:are|is)|actually|really|in\s+reality)\s+(\d+)\s+",
        r"(\d+)\s+(?:hole|pocket|slot|feature)s?\s+(?:in\s+reality|actually|really)",
    ]
    for pat in discrepancy_patterns:
        import re as _re2
        dm = _re2.search(pat, lower)
        if dm:
            user_count = dm.group(1)
            return (
                f"I understand you're saying the physical part has **{user_count} features** "
                f"that we haven't detected. Currently, the intelligence report shows "
                f"**{len(ctx.features)} feature(s)**.\n\n"
                f"This can happen when:\n"
                f"- The STEP file doesn't encode hole/pocket features explicitly\n"
                f"- Features are below the recognition threshold\n"
                f"- The geometry engine didn't classify them correctly\n\n"
                f"**What you can do:**\n"
                f"1. Re-upload the model with a higher-detail STEP export\n"
                f"2. Request a plan modification — e.g. \"add 4 holes at 10mm diameter\"\n"
                f"3. Manually add drilling operations via the edit panel\n\n"
                f"Would you like me to add the missing features to the plan?"
            )

    # ── Summary / overview ───────────────────────────────────────────────
    summary_phrases = ["summarize", "summary", "overview", "walk me through",
                       "explain this plan", "tell me about this"]
    if any(s in lower for s in summary_phrases):
        geo = ctx.geometry_summary
        bbox = geo.get("bounding_box", {})
        length = bbox.get("length", bbox.get("dx", 0))
        width = bbox.get("width", bbox.get("dy", 0))
        height = bbox.get("height", bbox.get("dz", 0))
        material_display = ctx.material.replace("_", " ").title()

        tool_map = {t.id: t for t in ctx.tools}
        op_lines = []
        for i, op in enumerate(ctx.operations, 1):
            tool = tool_map.get(op.tool_id)
            tool_desc = (
                f"{tool.type.replace('_', ' ')} Ø{tool.diameter}mm"
                if tool else op.tool_id
            )
            op_lines.append(
                f"{i}. **{op.type.replace('_', ' ')}** on `{op.feature_id}` "
                f"using {tool_desc} ({op.estimated_time:.1f}s)"
            )

        return (
            f"## Plan Summary — v{ctx.version}\n\n"
            f"**Part:** {material_display}, {length:.0f} × {width:.0f} × {height:.0f} mm\n"
            f"**Machine:** {ctx.machine_type.replace('_', ' ')}\n"
            f"**Complexity:** {ctx.complexity_score:.1f}/10 ({ctx.complexity_level})\n\n"
            f"### Operation Sequence\n"
            + "\n".join(op_lines) + "\n\n"
            f"### Summary\n"
            f"- **{len(ctx.setups)} setup(s)**, **{len(ctx.tools)} tool(s)**\n"
            f"- **Total time:** {ctx.cost_time.total_time:.1f}s ({ctx.cost_time.total_time / 60:.1f} min)\n"
            f"- **Strategy:** {ctx.selected_strategy}\n"
            f"- **Risks:** {len(ctx.risks)} flagged\n\n"
            f"Ask me about any specific aspect of this plan."
        )

    if "setup" in lower or "flip" in lower or "fixture" in lower:
        lines = [
            f"The current plan uses **{len(ctx.setups)} setup(s)**:\n"
        ]
        for s in ctx.setups:
            op_count = len(s.operations)
            lines.append(
                f"- **{s.setup_id}** — {s.orientation} orientation "
                f"(datum: `{s.datum_face_id}`), "
                f"{op_count} operation{'s' if op_count != 1 else ''}"
            )
        if len(ctx.setups) == 1:
            lines.append(
                "\nAll operations can be completed in a single setup, "
                "which minimizes fixturing changes and registration error. "
                "This is ideal for reducing cycle time and maintaining accuracy."
            )
        else:
            lines.append(
                "\nMultiple setups are required because some features need tool "
                "access from different orientations. Each re-fixturing introduces "
                "setup time and potential alignment offset."
            )
        return "\n".join(lines)

    if "time" in lower or "duration" in lower or "how long" in lower:
        lines = [
            f"**Total estimated machining time: {ctx.cost_time.total_time:.1f}s "
            f"({ctx.cost_time.total_time / 60:.1f} minutes)**\n"
        ]
        lines.append(
            f"- **{ctx.cost_time.operation_count}** operations across "
            f"**{ctx.cost_time.setup_count}** setup(s) using "
            f"**{ctx.cost_time.tool_count}** tool(s)"
        )
        # Per-operation time breakdown
        if ctx.operations:
            lines.append("\nOperation breakdown:")
            for op in ctx.operations:
                lines.append(
                    f"- `{op.id}` ({op.type}): **{op.estimated_time:.1f}s** "
                    f"on feature `{op.feature_id}`"
                )
        if ctx.strategies:
            active = next((s for s in ctx.strategies if s.name == ctx.selected_strategy), None)
            if active:
                lines.append(
                    f"\nUsing **{ctx.selected_strategy}** strategy. "
                    f"Try switching strategies in the Strategy panel to "
                    f"compare timing differences."
                )
        return "\n".join(lines)

    if "cost" in lower or "price" in lower or "how much" in lower:
        cost = ctx.cost_time.total_cost
        if cost is not None:
            lines = [
                f"**Estimated total cost: ${cost:.2f}**\n",
                f"This includes machining time ({ctx.cost_time.total_time:.1f}s), "
                f"tooling wear, setup time, and machine overhead.",
            ]
            if ctx.strategies:
                lines.append(
                    "\nCost varies by strategy — AGGRESSIVE reduces cycle time "
                    "but increases tool wear costs, while CONSERVATIVE prioritizes "
                    "tool life at the expense of longer machining time."
                )
            return "\n".join(lines)
        return (
            f"Cost estimate has not been computed yet. "
            f"The plan has {ctx.cost_time.operation_count} operations with "
            f"an estimated machining time of {ctx.cost_time.total_time:.1f}s. "
            f"Check the Cost panel for the full breakdown once it loads."
        )

    if "risk" in lower or "warn" in lower or "danger" in lower or "issue" in lower:
        if not ctx.risks:
            return (
                "No manufacturing risks have been flagged for this plan. "
                "The geometry and selected parameters are within standard "
                "machining capabilities for the specified machine type "
                f"({ctx.machine_type.replace('_', ' ')})."
            )
        lines = [f"**{len(ctx.risks)} risk(s)** identified:\n"]
        for r in ctx.risks:
            lines.append(
                f"- **[{r.severity}] {r.code}**: {r.message}"
            )
            if r.affected_operation_ids:
                ops = ", ".join(f"`{oid}`" for oid in r.affected_operation_ids)
                lines.append(f"  Affects operations: {ops}")
            if r.mitigation:
                lines.append(f"  → Mitigation: {r.mitigation}")
        return "\n".join(lines)

    if "complex" in lower:
        return (
            f"The part has a complexity score of **{ctx.complexity_score:.2f}/10** "
            f"(**{ctx.complexity_level}**).\n\n"
            f"This score is derived from:\n"
            f"- Number of features ({len(ctx.features)})\n"
            f"- Feature depth ratios and geometric interactions\n"
            f"- Multi-axis requirements and setup count ({len(ctx.setups)})\n"
            f"- Tolerance and surface finish demands\n\n"
            + (
                "A low complexity score means straightforward 3-axis machining "
                "with standard tooling." if ctx.complexity_score < 4 else
                "This moderate-to-high complexity may benefit from careful "
                "fixturing strategy and tool path optimization."
            )
        )

    if "tool" in lower or "cutter" in lower or "mill" in lower:
        lines = [f"**{len(ctx.tools)} tool(s)** in the current plan:\n"]
        for t in ctx.tools:
            ops_using = [op for op in ctx.operations if op.tool_id == t.id]
            op_types = ", ".join(set(op.type for op in ops_using))
            lines.append(
                f"- **`{t.id}`** — {t.type.replace('_', ' ')} Ø{t.diameter}mm "
                f"(RPM range: {t.recommended_rpm_min}–{t.recommended_rpm_max})\n"
                f"  Used for: {op_types or 'N/A'} "
                f"({len(ops_using)} operation{'s' if len(ops_using) != 1 else ''})"
            )
        if "ALUMINUM" in ctx.material.upper():
            lines.append(
                "\n*Note: For aluminum, high helix angles and sharp edges "
                "are preferred for efficient chip evacuation.*"
            )
        return "\n".join(lines)

    if "operation" in lower or "step" in lower or "sequence" in lower:
        lines = [
            f"**{len(ctx.operations)} operation(s)** planned in sequence:\n"
        ]
        tool_map = {t.id: t for t in ctx.tools}
        for i, op in enumerate(ctx.operations, 1):
            tool = tool_map.get(op.tool_id)
            tool_desc = (
                f"{tool.type.replace('_', ' ')} Ø{tool.diameter}mm"
                if tool else op.tool_id
            )
            lines.append(
                f"{i}. **{op.type.replace('_', ' ')}** (`{op.id}`)\n"
                f"   Feature: `{op.feature_id}` | Tool: {tool_desc} | "
                f"Time: {op.estimated_time:.1f}s"
            )
        lines.append(
            f"\n**Total estimated time: {ctx.cost_time.total_time:.1f}s** "
            f"with the {ctx.selected_strategy} strategy."
        )
        return "\n".join(lines)

    if "feature" in lower or "hole" in lower or "pocket" in lower or "slot" in lower:
        if not ctx.features:
            return (
                "No geometric features were detected in the intelligence report. "
                "The plan is using synthetic features derived from the part bounding "
                "box to generate operations. This typically happens when the STEP file "
                "lacks detailed feature geometry, or the part is relatively simple."
            )
        lines = [f"**{len(ctx.features)} feature(s)** detected:\n"]
        for f in ctx.features:
            fid = f.get("id", f.get("feature_id", "?"))
            ftype = f.get("type", "UNKNOWN")
            dims = f.get("dimensions", {})
            dim_str = ", ".join(f"{k}={v}" for k, v in dims.items()) if dims else "—"
            lines.append(f"- **`{fid}`** ({ftype}): {dim_str}")
        return "\n".join(lines)

    if "strateg" in lower:
        lines = [
            f"Currently using the **{ctx.selected_strategy}** strategy.\n"
        ]
        if ctx.strategies:
            lines.append("Available strategies:\n")
            for s in ctx.strategies:
                is_active = " ← *active*" if s.name == ctx.selected_strategy else ""
                lines.append(
                    f"- **{s.name}**: {s.description or 'Standard parameters'} "
                    f"(~{s.estimated_time:.0f}s){is_active}"
                )
            lines.append(
                "\nSwitch strategies in the Strategy panel to see "
                "live cost and time updates."
            )
        return "\n".join(lines)

    if "material" in lower:
        material_display = ctx.material.replace("_", " ").title()
        return (
            f"The part is **{material_display}** planned for "
            f"**{ctx.machine_type.replace('_', ' ')}**.\n\n"
            f"Material properties affect feed rates, spindle speeds, "
            f"tool selection, and coolant requirements. The current plan "
            f"parameters are tuned for this material."
        )

    if "datum" in lower or "reference" in lower:
        if ctx.datum_candidates:
            lines = ["**Datum candidates** identified:\n"]
            for dc in ctx.datum_candidates:
                if isinstance(dc, dict):
                    lines.append(
                        f"- Face `{dc.get('face_id', '?')}`: area={dc.get('area', '?')}, "
                        f"flatness={dc.get('flatness_score', '?')}"
                    )
            return "\n".join(lines)
        return "No datum candidates were identified in the intelligence report."

    # Generic comprehensive summary
    geo = ctx.geometry_summary
    bbox = geo.get("bounding_box", {})
    length = bbox.get("length", bbox.get("dx", 0))
    width = bbox.get("width", bbox.get("dy", 0))
    height = bbox.get("height", bbox.get("dz", 0))
    material_display = ctx.material.replace("_", " ").title()

    return (
        f"**Plan v{ctx.version}** for a **{material_display}** part "
        f"(**{length:.0f} × {width:.0f} × {height:.0f} mm**).\n\n"
        f"- **Features:** {len(ctx.features)}\n"
        f"- **Operations:** {len(ctx.operations)} across {len(ctx.setups)} setup(s)\n"
        f"- **Tools:** {len(ctx.tools)}\n"
        f"- **Complexity:** {ctx.complexity_score:.1f}/10 ({ctx.complexity_level})\n"
        f"- **Strategy:** {ctx.selected_strategy}\n"
        f"- **Est. time:** {ctx.cost_time.total_time:.1f}s "
        f"({ctx.cost_time.total_time / 60:.1f} min)\n\n"
        f"Ask me about specific operations, tools, setups, risks, "
        f"costs, or features for detailed explanations."
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
