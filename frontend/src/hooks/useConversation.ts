/**
 * useConversation — chat with the intelligence engine.
 */

import { useCallback, useState } from "react";
import { useWorkspaceStore } from "@/store/workspaceStore";
import { queryIntelligence } from "@/lib/intelligence-api";
import type { ConversationMessage } from "@/types/intelligence";

export function useConversation() {
  const { modelId, addMessage, conversationHistory } = useWorkspaceStore();
  const [isThinking, setIsThinking] = useState(false);

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
        });

        const assistantMsg: ConversationMessage = {
          id: crypto.randomUUID(),
          role: "assistant",
          content: res.message || JSON.stringify(res.data, null, 2),
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
    [modelId, addMessage],
  );

  return { conversationHistory, sendMessage, isThinking };
}
