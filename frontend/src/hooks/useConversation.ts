/**
 * useConversation — chat with the intelligence engine.
 *
 * Handles the full response lifecycle:
 *   • Regular answers → display as markdown
 *   • strategy_change → apply strategy + update cost/time panels
 *   • modification_redirect → forward to refinement engine → show results
 */

import { useCallback, useState } from "react";
import { useWorkspaceStore } from "@/store/workspaceStore";
import { queryIntelligence } from "@/lib/intelligence-api";
import { chatRefinePlan } from "@/lib/planning-api";
import { getCostBreakdown, getTimeBreakdown } from "@/lib/intelligence-api";
import type { ConversationMessage } from "@/types/intelligence";

/** Format structured data as readable text when no message is provided. */
function _formatFallback(data: unknown): string {
  if (!data) return "I processed your request but received no details.";
  if (typeof data === "string") return data;

  // If the data object has a message/answer/summary field, use it
  if (typeof data === "object" && data !== null) {
    const obj = data as Record<string, unknown>;
    if (typeof obj.message === "string" && obj.message) return obj.message;
    if (typeof obj.answer === "string" && obj.answer) return obj.answer;
    if (typeof obj.summary === "string" && obj.summary) return obj.summary;
  }

  // Last resort: formatted JSON in a code block
  try {
    return "```json\n" + JSON.stringify(data, null, 2) + "\n```";
  } catch {
    return "I processed your request. Check the workspace panels for updated data.";
  }
}

export function useConversation() {
  const {
    modelId,
    modelName,
    addMessage,
    conversationHistory,
    plan,
    setSelectedStrategy,
    setCost,
    setTime,
    setPlan,
  } = useWorkspaceStore();
  const [isThinking, setIsThinking] = useState(false);

  // ── Handle actionable response types ──────────────────────────────────
  const _handleStrategyChange = useCallback(
    async (res: { data?: Record<string, unknown>; message?: string }) => {
      const target = (res.data as Record<string, unknown>)?.strategy as string;
      if (!target || !modelId) return;

      setSelectedStrategy(target);

      // Recalculate cost & time with the new strategy
      try {
        const [costRes, timeRes] = await Promise.all([
          getCostBreakdown(modelId, undefined, target),
          getTimeBreakdown(modelId, undefined, target),
        ]);
        setCost(costRes.data);
        setTime(timeRes.data);
      } catch {
        // Cost/time panels keep previous data
      }
    },
    [modelId, setSelectedStrategy, setCost, setTime],
  );

  const _handleModificationRedirect = useCallback(
    async (originalMessage: string): Promise<string> => {
      const planId = plan?.plan_id;
      if (!planId) {
        return (
          "I'd like to modify the plan, but no plan ID is available yet. "
          + "Please wait for the plan to finish generating."
        );
      }

      try {
        const refRes = await chatRefinePlan(planId, {
          user_message: originalMessage,
        });

        if (refRes.type === "plan_update" && refRes.machining_plan) {
          // Plan was directly updated (e.g. confirmed, rollback)
          setPlan(refRes.machining_plan as unknown as Parameters<typeof setPlan>[0]);
          return (
            refRes.explanation ||
            refRes.message ||
            "Plan has been updated successfully."
          );
        }

        if (refRes.type === "plan_proposal" && refRes.proposed_plan) {
          // A proposal was generated — show the diff summary
          return (
            (refRes.explanation
              ? `**Proposed changes:**\n\n${refRes.explanation}\n\n`
              : "") +
            "Type **\"confirm\"** to apply these changes, or **\"reject\"** to discard them."
          );
        }

        // Conversation-type response from refinement (e.g. "be more specific")
        return (
          refRes.message ||
          refRes.explanation ||
          "I couldn't identify specific changes. Could you be more specific?"
        );
      } catch (err) {
        return `Refinement failed: ${err instanceof Error ? err.message : "Unknown error"}`;
      }
    },
    [plan, setPlan],
  );

  // ── Main send handler ─────────────────────────────────────────────────
  const sendMessage = useCallback(
    async (text: string) => {
      if (!modelId || !text.trim()) return null;

      // Add user message
      const userMsg: ConversationMessage = {
        id: crypto.randomUUID(),
        role: "user",
        content: text,
        timestamp: new Date().toISOString(),
      };
      addMessage(userMsg);
      setIsThinking(true);

      try {
        const res = await queryIntelligence(modelId, {
          user_message: text,
          plan_id: plan?.plan_id ?? undefined,
          version: plan?.version ?? undefined,
          part_name: modelName || undefined,
        });

        // ── Strategy change → execute it silently + show message ────────
        if (res.type === "strategy_change") {
          await _handleStrategyChange(res);
        }

        // ── Modification redirect → forward to refinement engine ────────
        if (res.type === "modification_redirect") {
          const refinementMessage = await _handleModificationRedirect(text);
          const assistantMsg: ConversationMessage = {
            id: crypto.randomUUID(),
            role: "assistant",
            content: refinementMessage,
            timestamp: new Date().toISOString(),
            type: "refinement_result",
          };
          addMessage(assistantMsg);
          return res;
        }

        // ── Standard response ───────────────────────────────────────────
        const assistantMsg: ConversationMessage = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: res.message || _formatFallback(res.data),
          timestamp: new Date().toISOString(),
          type: res.type,
          data: res.data,
        };
        addMessage(assistantMsg);
        return res;
      } catch (err) {
        const errorMsg: ConversationMessage = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: `Error: ${err instanceof Error ? err.message : "Request failed"}`,
          timestamp: new Date().toISOString(),
          type: "error",
        };
        addMessage(errorMsg);
        return null;
      } finally {
        setIsThinking(false);
      }
    },
    [
      modelId,
      modelName,
      addMessage,
      plan,
      _handleStrategyChange,
      _handleModificationRedirect,
    ],
  );

  return { conversationHistory, sendMessage, isThinking };
}
