import { useGameStore } from '@/stores/gameStore';
import { GlassCard } from '@/components/common/GlassCard';
import { Radio, Target, Heart, Clock } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useEffect, useState } from 'react';

/**
 * 底部状态栏组件
 * 直播中 | 猜测次数 | 赞数 | 揭示进度 | 游戏时长
 */
export function StatusBar() {
  const { phase, guessCount, likeProgress, charStates, startTime } = useGameStore();
  const [duration, setDuration] = useState(0);

  // 计算揭示进度
  const contentWords = charStates.filter((s) => s.isContentWord);
  const revealedCount = contentWords.filter((s) => s.revealed).length;
  const totalContentWords = contentWords.length;
  const revealProgress = totalContentWords === 0 ? 0 : Math.round((revealedCount / totalContentWords) * 100);

  // 更新游戏时长
  useEffect(() => {
    if (phase === 'idle' || startTime === 0) {
      setDuration(0);
      return;
    }

    const interval = setInterval(() => {
      setDuration(Math.floor((Date.now() - startTime) / 1000));
    }, 1000);

    return () => clearInterval(interval);
  }, [phase, startTime]);

  // 格式化时长
  const formatDuration = (seconds: number) => {
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}分${secs.toString().padStart(2, '0')}秒`;
  };

  return (
    <GlassCard className="p-3" variant="default">
      <div className="flex items-center justify-between gap-4">
        {/* 直播中状态 */}
        <div className="flex items-center gap-2">
          <Radio className={cn(
            'w-4 h-4',
            phase !== 'idle' ? 'text-success animate-pulse' : 'text-muted-foreground'
          )} />
          <span className={cn(
            'text-sm font-medium',
            phase !== 'idle' ? 'text-success' : 'text-muted-foreground'
          )}>
            {phase !== 'idle' ? '直播中' : '未开始'}
          </span>
        </div>

        {/* 分隔线 */}
        <div className="w-px h-6 bg-border/50" />

        {/* 猜测次数 */}
        <div className="flex items-center gap-2">
          <Target className="w-4 h-4 text-primary" />
          <span className="text-sm text-foreground">{guessCount}次猜测</span>
        </div>

        {/* 分隔线 */}
        <div className="w-px h-6 bg-border/50" />

        {/* 赞数 */}
        <div className="flex items-center gap-2">
          <Heart className="w-4 h-4 text-rose-500" />
          <span className="text-sm text-foreground">{likeProgress}赞</span>
        </div>

        {/* 分隔线 */}
        <div className="w-px h-6 bg-border/50" />

        {/* 揭示进度 */}
        <div className="flex items-center gap-2">
          <div className="w-4 h-4 rounded-full bg-primary/20 flex items-center justify-center">
            <span className="text-[10px] text-primary font-bold">{revealProgress}%</span>
          </div>
          <span className="text-sm text-foreground">揭示进度</span>
        </div>

        {/* 分隔线 */}
        <div className="w-px h-6 bg-border/50 hidden sm:block" />

        {/* 游戏时长 */}
        <div className="hidden sm:flex items-center gap-2">
          <Clock className="w-4 h-4 text-muted-foreground" />
          <span className="text-sm text-muted-foreground">{formatDuration(duration)}</span>
        </div>
      </div>
    </GlassCard>
  );
}
