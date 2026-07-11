import { useGameStore } from '@/stores/gameStore';
import { GlassCard } from '@/components/common/GlassCard';
import { ThumbsUp } from 'lucide-react';

/**
 * 点赞进度条组件
 * 显示点赞累积进度，达到阈值触发揭示
 */
export function LikeProgress() {
  const { likeProgress, likeThreshold } = useGameStore();

  const progress = Math.min((likeProgress / likeThreshold) * 100, 100);
  const remaining = likeThreshold - likeProgress;

  return (
    <GlassCard className="p-4" variant="default">
      <div className="flex items-center justify-between mb-2">
        <h3 className="font-semibold text-foreground flex items-center gap-2">
          <ThumbsUp className="w-4 h-4 text-primary" />
          点赞进度
        </h3>
        <span className="text-xs text-muted-foreground">
          {likeProgress} / {likeThreshold}
        </span>
      </div>

      {/* 进度条 */}
      <div className="relative h-3 bg-muted/30 rounded-full overflow-hidden">
        <div
          className="absolute inset-y-0 left-0 bg-gradient-to-r from-primary to-primary/80 transition-all duration-300 ease-out"
          style={{ width: `${progress}%` }}
        >
          {/* 光泽效果 */}
          <div className="absolute inset-0 bg-gradient-to-b from-white/20 to-transparent" />
        </div>

        {/* 阈值标记 */}
        <div className="absolute inset-y-0 right-0 w-0.5 bg-accent/50" />
      </div>

      {/* 提示信息 */}
      <div className="mt-2 flex items-center justify-between text-xs">
        <span className="text-muted-foreground">
          还差 <span className="text-primary font-medium">{remaining}</span> 赞揭示一字
        </span>
        {progress >= 80 && (
          <span className="text-accent animate-pulse">即将达成！</span>
        )}
      </div>
    </GlassCard>
  );
}
