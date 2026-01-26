"use client";

import type { QueryRecord } from "@/types/api";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { ScrollArea } from "@/components/ui/scroll-area";

interface ChatHistoryProps {
  queries: QueryRecord[];
  onSelect?: (query: QueryRecord) => void;
}

export function ChatHistory({ queries, onSelect }: ChatHistoryProps) {
  if (queries.length === 0) {
    return null;
  }

  return (
    <Card className="p-4">
      <h3 className="text-sm font-medium mb-3">Previous Questions</h3>
      <ScrollArea className="max-h-48">
        <div className="space-y-2">
          {queries.slice().reverse().map((query) => (
            <button
              key={query.query_id}
              onClick={() => onSelect?.(query)}
              className="w-full text-left p-3 rounded-lg bg-muted/50 hover:bg-muted transition-colors"
            >
              <p className="text-sm font-medium truncate">{query.question}</p>
              <div className="flex items-center gap-2 mt-1">
                <Badge variant="secondary" className="text-xs">
                  {query.voice}
                </Badge>
                <span className="text-xs text-muted-foreground">
                  {new Date(query.created_at).toLocaleTimeString()}
                </span>
              </div>
            </button>
          ))}
        </div>
      </ScrollArea>
    </Card>
  );
}
