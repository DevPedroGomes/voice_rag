"use client";

import type { VoiceType } from "@/types/api";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";

const VOICES: { id: VoiceType; name: string; description: string }[] = [
  { id: "alloy", name: "Alloy", description: "Neutral and balanced" },
  { id: "ash", name: "Ash", description: "Soft and gentle" },
  { id: "ballad", name: "Ballad", description: "Warm and expressive" },
  { id: "coral", name: "Coral", description: "Clear and friendly" },
  { id: "echo", name: "Echo", description: "Smooth and calm" },
  { id: "fable", name: "Fable", description: "Warm and narrative" },
  { id: "onyx", name: "Onyx", description: "Deep and authoritative" },
  { id: "nova", name: "Nova", description: "Energetic and bright" },
  { id: "sage", name: "Sage", description: "Wise and measured" },
  { id: "shimmer", name: "Shimmer", description: "Light and airy" },
  { id: "verse", name: "Verse", description: "Poetic and melodic" },
];

interface VoiceSelectorProps {
  value: VoiceType;
  onChange: (value: VoiceType) => void;
  disabled?: boolean;
}

export function VoiceSelector({ value, onChange, disabled }: VoiceSelectorProps) {
  return (
    <div className="space-y-2">
      <label className="text-sm font-medium">Voice</label>
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger className="w-full">
          <SelectValue placeholder="Select a voice" />
        </SelectTrigger>
        <SelectContent>
          {VOICES.map((voice) => (
            <SelectItem key={voice.id} value={voice.id}>
              <div className="flex flex-col">
                <span>{voice.name}</span>
                <span className="text-xs text-muted-foreground">
                  {voice.description}
                </span>
              </div>
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
