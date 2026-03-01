/**
 * MessageBubble — renders a single user or assistant chat message.
 */

import { cn } from "@/lib/utils";
import { Bot, User } from "lucide-react";
import type { ConversationMessage } from "@/types/intelligence";

interface MessageBubbleProps {
  message: ConversationMessage;
}

export function MessageBubble({ message }: MessageBubbleProps) {
  const isUser = message.role === "user";

  return (
    <div
      className={cn(
        "flex gap-2.5 max-w-[92%]",
        isUser ? "ml-auto flex-row-reverse" : "",
      )}
    >
      {/* Avatar */}
      <div
        className={cn(
          "flex h-7 w-7 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary/20" : "bg-muted",
        )}
      >
        {isUser ? (
          <User className="h-3.5 w-3.5 text-primary" />
        ) : (
          <Bot className="h-3.5 w-3.5 text-muted-foreground" />
        )}
      </div>

      {/* Bubble */}
      <div
        className={cn(
          "rounded-lg px-3 py-2 text-sm leading-relaxed",
          isUser
            ? "bg-primary text-primary-foreground rounded-br-sm"
            : "bg-muted text-foreground rounded-bl-sm",
        )}
      >
        {/* Render content — for now as text, could extend with markdown */}
        <p className="whitespace-pre-wrap break-words">{message.content}</p>

        {/* Timestamp */}
        <p
          className={cn(
            "text-[9px] mt-1",
            isUser ? "text-primary-foreground/50" : "text-muted-foreground/50",
          )}
        >
          {message.timestamp
            ? new Date(message.timestamp).toLocaleTimeString([], {
                hour: "2-digit",
                minute: "2-digit",
              })
            : ""}
        </p>
      </div>
    </div>
  );
}
