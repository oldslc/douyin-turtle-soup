import { GlassCard } from "@/components/common/GlassCard";
import { cn } from "@/lib/utils";
import { useGameStore } from "@/stores/gameStore";
import type { GiftType } from "@/types";

export interface GiftInfo {
  name: string;
  sendName: string;    // 传给后端的礼物名
  color: string;
  bgColor: string;
  effect: string;
  type: GiftType;
}

const GIFTS: GiftInfo[] = [
  { name: "点赞", sendName: "点赞", color: "text-rose-400", bgColor: "bg-rose-500/30", effect: "500赞=1字", type: "like" },
  { name: "灯牌", sendName: "粉丝灯牌", color: "text-yellow-400", bgColor: "bg-yellow-500/30", effect: "随机1句", type: "fan_light" },
  { name: "啤酒", sendName: "啤酒", color: "text-amber-400", bgColor: "bg-amber-500/30", effect: "随机1字", type: "beer" },
  { name: "棒棒糖", sendName: "棒棒糖", color: "text-pink-400", bgColor: "bg-pink-500/30", effect: "随机1句", type: "lollipop" },
  { name: "人气票", sendName: "人气票", color: "text-cyan-400", bgColor: "bg-cyan-500/30", effect: "方向提示", type: "popularity" },
  { name: "墨镜", sendName: "墨镜", color: "text-purple-400", bgColor: "bg-purple-500/30", effect: "直接通关", type: "sunglasses" },
];

const GIFT_ICONS: Record<GiftType, string> = {
  like: "❤️",
  fan_light: "⭐",
  popularity: "⚡",
  beer: "🍺",
  lollipop: "🍭",
  sunglasses: "🕶️",
};

interface GiftPanelProps {
  onSendGift?: (giftName: string) => void;
}

export function GiftPanel({ onSendGift }: GiftPanelProps) {
  const { phase, currentSoup } = useGameStore();

  const handleGiftClick = (gift: GiftInfo) => {
    if (phase !== "playing" && phase !== "reading") return;
    if (!currentSoup) return;
    if (onSendGift) {
      onSendGift(gift.sendName);
    }
  };

  return (
    <GlassCard className="p-2" variant="default">
      <div className="flex items-center gap-1">
        {GIFTS.map((gift) => (
          <button
            key={gift.name}
            onClick={() => handleGiftClick(gift)}
            disabled={phase !== "playing" && phase !== "reading"}
            className={cn(
              "flex-1 flex flex-col items-center justify-center p-2 rounded-lg transition-all duration-200 border",
              phase === "playing" || phase === "reading"
                ? "hover:scale-105 active:scale-95 cursor-pointer hover:shadow-lg"
                : "opacity-40 cursor-not-allowed",
              "bg-background/60 border-border/50 hover:border-primary/50 hover:bg-background/80"
            )}
          >
            <div className={cn("p-1.5 rounded-full mb-0.5", gift.bgColor)}>
              <span className={cn("text-sm", gift.color)}>{GIFT_ICONS[gift.type]}</span>
            </div>
            <span className="text-[10px] text-muted-foreground leading-tight">{gift.name}</span>
            <span className="text-[9px] text-accent leading-tight">{gift.effect}</span>
          </button>
        ))}
      </div>
    </GlassCard>
  );
}