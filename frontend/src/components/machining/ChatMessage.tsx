import { Bot, User } from "lucide-react";
import { cn } from "@/lib/utils";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChatMessageData {
  id: string;
  role: "user" | "copilot";
  content: string;
  version?: number;
  proposedPlan?: Record<string, unknown>;
  timestamp: Date;
}

interface ChatMessageProps {
  message: ChatMessageData;
  onApplyProposal?: (plan: Record<string, unknown>) => void;
}

// ─── Component ───────────────────────────────────────────────────────────────

export function ChatMessage({ message, onApplyProposal }: ChatMessageProps) {
  const isUser = message.role === "user";
  return (
    <div
      className={cn(
        "flex gap-3 px-2 py-2 group animate-in fade-in slide-in-from-bottom-2 duration-300",
        isUser ? "flex-row-reverse" : "flex-row",
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex size-8 shrink-0 items-center justify-center rounded-full shadow-lg ring-2 ring-white/10 group-hover:ring-indigo-400/40 transition-all duration-200",
          isUser
            ? "bg-gradient-to-br from-primary to-indigo-600 text-primary-foreground"
            : "bg-gradient-to-br from-indigo-500/20 to-purple-500/20 text-indigo-400 border border-indigo-500/30",
        )}
        title={isUser ? "You" : "MechAI Copilot"}
      >
        {isUser ? <User className="size-4" /> : <Bot className="size-4" />}
      </div>

      {/* Bubble */}
      <div
        className={cn(
          "flex max-w-[85%] flex-col gap-1 rounded-2xl px-4 py-2.5 text-sm overflow-hidden shadow-md backdrop-blur-md border border-transparent transition-all duration-200",
          isUser
            ? "bg-gradient-to-br from-primary to-indigo-600 text-primary-foreground rounded-tr-md border-primary/30"
            : "bg-gradient-to-br from-indigo-500/10 to-purple-500/10 border border-indigo-500/20 text-foreground rounded-tl-md",
        )}
      >
        {isUser ? (
          <p className="whitespace-pre-wrap leading-relaxed break-words">
            {message.content}
          </p>
        ) : (
          <div className="prose prose-sm max-w-none break-words dark:prose-invert">
            <ReactMarkdown remarkPlugins={[remarkGfm]}>
              {message.content}
            </ReactMarkdown>
          </div>
        )}

        {/* Meta line */}
        <div
          className={cn(
            "flex items-center gap-2 text-[10px] mt-1",
            isUser ? "text-primary-foreground/60" : "text-muted-foreground",
          )}
        >
          <span suppressHydrationWarning>
            {new Date(message.timestamp).toLocaleTimeString([], {
              hour: "2-digit",
              minute: "2-digit",
            })}
          </span>
          {message.version !== undefined && (
            <span className="font-mono">→ v{message.version}</span>
          )}
        </div>

        {/* Action button for proposals */}
        {message.proposedPlan && onApplyProposal && (
          <div className="mt-3 text-right">
            <button
              onClick={() => onApplyProposal(message.proposedPlan!)}
              className="rounded-lg bg-indigo-500/30 border border-indigo-500/60 px-3 py-1.5 text-xs font-semibold text-indigo-100 shadow-md transition-all hover:bg-indigo-500/50 hover:scale-105 active:scale-95"
            >
              Apply Changes to Editor
            </button>
          </div>
        )}
      </div>
    </div>
  );
}
