import { useGameStore } from '@/stores/gameStore';
import { GlassCard } from '@/components/common/GlassCard';
import { cn } from '@/lib/utils';

/**
 * 双进度条组件
 * 揭示进度 + 点赞进度
 */
export function ProgressBars() {
  const { charStates, likeProgress, likeThreshold } = useGameStore();

  // 计算揭示进度
  const contentWords = charStates.filter((s) => s.isContentWord);
  const revealedCount = contentWords.filter((s) => s.revealed).length;
  const totalContentWords = contentWords.length;
  const revealProgress = totalContentWords === 0 ? 0 : Math.round((revealedCount / totalContentWords) * 100);
  const revealRemaining = totalContentWords - revealedCount;

  // 点赞进度
  const likePercentage = Math.min((likeProgress / likeThreshold) * 100, 100);
  const likeRemaining = likeThreshold - likeProgress;

  return (
    <GlassCard className="p-2" variant="default">
      <div className="space-y-2">
        {/* 揭示进度 - 缩小版 */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium text-foreground">揭示进度</span>
            <span className="text-xs text-muted-foreground">
              {revealedCount}/{totalContentWords}
            </span>
          </div>
          <div className="h-1.5 bg-muted/30 rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full transition-all duration-500 ease-out',
                revealProgress >= 80 ? 'bg-success' : 'bg-primary'
              )}
              style={{ width: `${revealProgress}%` }}
            />
          </div>
          <div className="mt-0.5 text-[10px] text-muted-foreground">
            还剩 {revealRemaining} 字
          </div>
        </div>

        {/* 点赞进度 - 缩小版 */}
        <div>
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium text-foreground">点赞进度</span>
            <span className="text-xs text-muted-foreground">
              {likeProgress}/{likeThreshold}
            </span>
          </div>
          <div className="h-1.5 bg-muted/30 rounded-full overflow-hidden">
            <div
              className={cn(
                'h-full rounded-full transition-all duration-500 ease-out',
                likePercentage >= 80 ? 'bg-accent' : 'bg-secondary'
              )}
              style={{ width: `${likePercentage}%` }}
            />
          </div>
          <div className="mt-0.5 text-[10px] text-muted-foreground">
            还差 {likeRemaining} 赞
          </div>
        </div>
      </div>
    </GlassCard>
  );
}
