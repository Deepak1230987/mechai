/**
 * ChatPanel — conversational AI chat with scrollable messages,
 * input bar, and thinking indicator.
 */

import { useRef, useEffect, useState } from "react";
import { useConversation } from "@/hooks/useConversation";
import { useWorkspaceStore } from "@/store/workspaceStore";
import { MessageBubble } from "./MessageBubble";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { Bot, Send, Sparkles } from "lucide-react";

export function ChatPanel() {
  const { conversationHistory, sendMessage, isThinking } = useConversation();
  const modelName = useWorkspaceStore((s) => s.modelName);
  const modelId = useWorkspaceStore((s) => s.modelId);
  const plan = useWorkspaceStore((s) => s.plan);
  const [input, setInput] = useState("");
  const scrollRef = useRef<HTMLDivElement>(null);

  // Auto-scroll to bottom
  useEffect(() => {
    const el = scrollRef.current;
    if (el) {
      el.scrollTop = el.scrollHeight;
    }
  }, [conversationHistory.length, isThinking]);

  const handleSend = () => {
    const text = input.trim();
    if (!text || isThinking) return;
    setInput("");
    sendMessage(text);
  };

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  return (
    <div className="flex flex-col h-full">
      {/* Header */}
      <div className="flex items-center gap-2 border-b border-border px-3 py-2">
        <Sparkles className="h-4 w-4 text-primary" />
        <span className="text-xs font-semibold text-foreground">
          Manufacturing AI
        </span>
        <span className="text-[10px] text-muted-foreground ml-auto">
          {modelName ?? ""}
        </span>
      </div>

      {/* Messages */}
      <ScrollArea className="flex-1 min-h-0">
        <div ref={scrollRef} className="space-y-3 p-3">
          {conversationHistory.length === 0 && !isThinking && (
            <div className="flex flex-col items-center justify-center py-8 text-center">
              <Bot className="h-10 w-10 text-muted-foreground/20 mb-3" />
              {!plan ? (
                <>
                  <p className="text-sm text-muted-foreground mb-1">
                    Generating machining plan…
                  </p>
                  <p className="text-xs text-muted-foreground/60 max-w-[240px]">
                    Chat will be available once the plan is ready.
                  </p>
                </>
              ) : (
                <>
                  <p className="text-sm text-muted-foreground mb-1">
                    Ask about your machining plan
                  </p>
                  <p className="text-xs text-muted-foreground/60 max-w-[240px]">
                    "Why did you choose this tool?" "Can we reduce setups?"
                    "What if I use aluminum?"
                  </p>
                </>
              )}
            </div>
          )}

          {conversationHistory.map((msg) => (
            <MessageBubble key={msg.id} message={msg} />
          ))}

          {/* Thinking indicator */}
          {isThinking && (
            <div className="flex items-center gap-2.5">
              <div className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-muted">
                <Bot className="h-3.5 w-3.5 text-muted-foreground" />
              </div>
              <div className="rounded-lg bg-muted px-3 py-2 rounded-bl-sm">
                <div className="flex items-center gap-1">
                  <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:0ms]" />
                  <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:150ms]" />
                  <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/50 animate-bounce [animation-delay:300ms]" />
                </div>
              </div>
            </div>
          )}
        </div>
      </ScrollArea>

      {/* Input bar */}
      <div className="border-t border-border p-2">
        <div className="flex items-end gap-2">
          <Textarea
            placeholder="Ask about your manufacturing plan…"
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            rows={1}
            className="min-h-[36px] max-h-[100px] resize-none text-sm bg-muted/30 border-border/50"
          />
          <Button
            size="icon"
            className="h-9 w-9 shrink-0"
            disabled={!input.trim() || isThinking || !modelId || !plan}
            onClick={handleSend}
          >
            <Send className="h-4 w-4" />
          </Button>
        </div>
      </div>
    </div>
  );
}
