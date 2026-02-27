import { useState, useRef, useEffect, useCallback } from "react";
import { Send, Loader2, Bot, AlertTriangle } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Badge } from "@/components/ui/badge";
import { ChatMessage, type ChatMessageData } from "./ChatMessage";

// ─── Props ───────────────────────────────────────────────────────────────────

interface CopilotChatPanelProps {
  /** Current plan version displayed in the header. */
  version: number;
  /** Whether the operations editor has unsaved manual edits. */
  dirty: boolean;
  /** Called when copilot returns an updated plan. Parent decides how to apply. */
  onPlanUpdated: (plan: Record<string, unknown>, version: number) => void;
  /** Function that calls the backend chat endpoint. */
  sendMessage: (message: string) => Promise<{
    explanation: string;
    machining_plan: Record<string, unknown>;
    version: number;
  }>;
}

// ─── Component ──────────────────────────────────────────────────────────────

export function CopilotChatPanel({
  version,
  dirty,
  onPlanUpdated,
  sendMessage,
}: CopilotChatPanelProps) {
  const [messages, setMessages] = useState<ChatMessageData[]>([
    {
      id: "welcome",
      role: "copilot",
      content:
        "Hi! I'm MechAI Copilot. Ask me to modify your machining plan — change tools, adjust feed rates, reorder operations, or switch strategies. I'll explain every change.",
      timestamp: new Date(),
    },
  ]);
  const [input, setInput] = useState("");
  const [sending, setSending] = useState(false);

  const scrollEndRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);

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

      // Append copilot explanation
      const copilotMsg: ChatMessageData = {
        id: `copilot_${Date.now()}`,
        role: "copilot",
        content: result.explanation,
        version: result.version,
        timestamp: new Date(),
      };
      setMessages((prev) => [...prev, copilotMsg]);

      // Notify parent to update plan
      onPlanUpdated(result.machining_plan, result.version);
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
    <div className="flex h-full flex-col rounded-lg border bg-background">
      {/* Header */}
      <div className="flex items-center justify-between border-b px-4 py-3">
        <div className="flex items-center gap-2">
          <Bot className="size-5 text-primary" />
          <span className="text-sm font-semibold">MechAI Copilot</span>
        </div>
        <Badge variant="outline" className="font-mono text-xs">
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
      <ScrollArea className="flex-1 p-2">
        <div className="flex flex-col">
          {messages.map((msg) => (
            <ChatMessage key={msg.id} message={msg} />
          ))}

          {/* Typing indicator */}
          {sending && (
            <div className="flex items-center gap-2 px-2 py-3 text-xs text-muted-foreground">
              <Loader2 className="size-3.5 animate-spin" />
              Copilot is thinking…
            </div>
          )}

          {/* Scroll anchor */}
          <div ref={scrollEndRef} />
        </div>
      </ScrollArea>

      {/* Input area */}
      <div className="border-t p-3">
        <div className="flex gap-2">
          <Textarea
            ref={textareaRef}
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="e.g. Switch to carbide end mills for better surface finish…"
            className="min-h-10 max-h-30 resize-none text-sm"
            rows={1}
            disabled={sending}
          />
          <Button
            size="icon"
            onClick={handleSend}
            disabled={sending || !input.trim()}
            className="shrink-0 self-end"
          >
            {sending ? (
              <Loader2 className="size-4 animate-spin" />
            ) : (
              <Send className="size-4" />
            )}
          </Button>
        </div>
        <p className="mt-1.5 text-[10px] text-muted-foreground">
          Enter to send · Shift+Enter for new line
        </p>
      </div>
    </div>
  );
}
