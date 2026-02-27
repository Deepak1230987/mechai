import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, Bot, AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { ChatMessage, type ChatMessageData } from "./ChatMessage";

// ─── Props ───────────────────────────────────────────────────────────────────

interface CopilotChatPanelProps {
  /** Current plan model ID for localStorage. */
  modelId: string;
  /** Current plan version displayed in the header. */
  version: number;
  /** Whether the operations editor has unsaved manual edits. */
  dirty: boolean;
  /** Called when copilot returns an updated plan. Parent decides how to apply. */
  onPlanUpdated: (plan: Record<string, unknown>, version: number) => void;
  /** Called when user clicks "Apply Changes" on a proposed plan. */
  onPlanProposed: (plan: Record<string, unknown>) => void;
  /** Function that calls the backend chat endpoint. */
  sendMessage: (message: string) => Promise<{
    type: "conversation" | "plan_update" | "plan_proposal";
    message?: string;
    explanation?: string;
    machining_plan?: Record<string, unknown>;
    proposed_plan?: Record<string, unknown>;
    version?: number;
  }>;
}

// ─── Component ──────────────────────────────────────────────────────────────

export function CopilotChatPanel({
  modelId,
  version,
  dirty,
  onPlanUpdated,
  onPlanProposed,
  sendMessage,
}: CopilotChatPanelProps) {
  const scrollEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  // Read initial messages from local storage or use default
  const [messages, setMessages] = useState<ChatMessageData[]>(() => {
    const defaultMessages: ChatMessageData[] = [
      {
        id: "welcome",
        role: "copilot",
        content:
          "Hi! I'm MechAI Copilot. Ask me to modify your machining plan — change tools, adjust feed rates, reorder operations, or switch strategies. I'll explain every change.",
        timestamp: new Date(),
      },
    ];

    try {
      const saved = localStorage.getItem(`copilot_chat_${modelId}`);
      if (saved) {
        return JSON.parse(saved);
      }
    } catch {
      // Ignore parse errors
    }
    return defaultMessages;
  });

  // Save to local storage whenever messages change
  useEffect(() => {
    try {
      localStorage.setItem(`copilot_chat_${modelId}`, JSON.stringify(messages));
    } catch {
      // Ignore quota errors, etc.
    }
  }, [messages, modelId]);

  // ── Auto-scroll on new messages ────────────────────────────────────────
  useEffect(() => {
    scrollEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages, sending]);

  // ── Send handler ───────────────────────────────────────────────────────
  const handleSend = useCallback(async () => {
    const text = input.trim();
    if (!text || sending) return;

    // Append user message
    const userMsg: ChatMessageData = {
      id: `user_${Date.now()}`,
      role: "user",
      content: text,
      timestamp: new Date(),
    };
    setMessages((prev) => [...prev, userMsg]);
    setInput("");
    setSending(true);

    try {
      const result = await sendMessage(text);

      if (result.type === "conversation") {
        // Append copilot general message
        const copilotMsg: ChatMessageData = {
          id: `copilot_${Date.now()}`,
          role: "copilot",
          content: result.message || "Something went wrong processing your message.",
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, copilotMsg]);
      } else if (result.type === "plan_proposal" && result.proposed_plan) {
        // Append copilot proposal message
        const copilotMsg: ChatMessageData = {
          id: `copilot_${Date.now()}`,
          role: "copilot",
          content: result.explanation || "I've drafted a plan update. Click below to apply it.",
          proposedPlan: result.proposed_plan,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, copilotMsg]);
      } else {
        // Fallback legacy plan_update direct commit
        const copilotMsg: ChatMessageData = {
          id: `copilot_${Date.now()}`,
          role: "copilot",
          content: result.explanation || "Plan modified successfully.",
          version: result.version,
          timestamp: new Date(),
        };
        setMessages((prev) => [...prev, copilotMsg]);

        // Notify parent to update plan
        if (result.machining_plan && result.version !== undefined) {
          onPlanUpdated(result.machining_plan, result.version);
        }
      }
    } catch (err) {
      const errorMsg: ChatMessageData = {
        id: `error_${Date.now()}`,
        role: "copilot",
        content: `Sorry, I couldn't process that request. ${
          err instanceof Error ? err.message : "Please try again."
        }`,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, errorMsg]);
    } finally {
      setSending(false);
      textareaRef.current?.focus();
    }
  }, [input, sending, sendMessage, onPlanUpdated]);

  // ── Keyboard: Enter to send, Shift+Enter for newline ───────────────────
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" && !e.shiftKey) {
        e.preventDefault();
        handleSend();
      }
    },
    [handleSend],
  );

  return (
    <div className="flex flex-col h-full min-h-0 overflow-hidden rounded-xl border border-white/10 bg-background/60 shadow-2xl backdrop-blur-xl transition-all duration-500 hover:border-white/20 hover:shadow-indigo-500/10">
      {/* Header */}
      <div className="flex items-center justify-between border-b border-white/10 bg-linear-to-r from-background/40 via-background/20 to-indigo-900/10 px-4 py-3 backdrop-blur-md">
        <div className="flex items-center gap-2">
          <div className="flex size-7 items-center justify-center rounded-full bg-primary/20 text-primary shadow-[0_0_15px_rgba(37,99,235,0.2)]">
            <Bot className="size-4" />
          </div>
          <span className="bg-linear-to-r from-foreground to-foreground/70 bg-clip-text text-sm font-semibold tracking-wide text-transparent">
            MechAI Copilot
          </span>
        </div>
        <Badge variant="outline" className="border-indigo-500/30 bg-indigo-500/10 font-mono text-xs text-indigo-300">
          v{version}
        </Badge>
      </div>

      {/* Dirty warning */}
      {dirty && (
        <div className="flex items-center gap-2 border-b bg-amber-50 px-4 py-2 text-xs text-amber-700 dark:bg-amber-950/30 dark:text-amber-400">
          <AlertTriangle className="size-3.5 shrink-0" />
          <span>
            You have unsaved manual edits. Copilot changes will replace them.
          </span>
        </div>
      )}

      {/* Messages */}
      <ScrollArea className="flex-1 min-h-0 max-h-full p-2">
        <div className="flex flex-col gap-0.5">
          {messages.map((msg, i) => {
            // Group messages by sender for visual continuity
            const prev = messages[i - 1];
            const isGrouped = prev && prev.role === msg.role;
            return (
              <div key={msg.id} className={isGrouped ? "-mt-2" : "mt-2 first:mt-0"}>
                <ChatMessage message={msg} onApplyProposal={onPlanProposed} />
              </div>
            );
          })}

          {/* Typing indicator */}
          {sending && (
            <div className="flex items-center gap-2 px-2 py-3 text-xs text-muted-foreground animate-pulse">
              <Loader2 className="size-3.5 animate-spin" />
              Copilot is thinking…
            </div>
          )}

          {/* Scroll anchor */}
          <div ref={scrollEndRef} />
        </div>
      </ScrollArea>

      {/* Input area */}
      <div className="border-t border-white/10 bg-background/40 p-3 backdrop-blur-md">
        <div className="flex gap-2">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="e.g. Switch to carbide end mills for better surface finish…"
            className="min-h-10 max-h-40 resize-y rounded-xl border-white/10 bg-background/50 text-sm focus-visible:ring-indigo-500/50 focus-visible:border-indigo-400/40 transition-all"
            rows={1}
            disabled={sending}
            style={{ minHeight: 40, maxHeight: 160, overflow: 'auto' }}
            autoFocus
          />
          <Button
            size="icon"
            onClick={handleSend}
            disabled={sending || !input.trim()}
            className="shrink-0 self-end rounded-xl shadow-lg transition-all duration-300 hover:scale-105 hover:shadow-indigo-500/25 active:scale-95"
            tabIndex={0}
            aria-label="Send message"
          >
            {sending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Send className="size-4" />
            )}
          </Button>
        </div>
        <p className="mt-2 text-center text-[10px] text-muted-foreground/70">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
