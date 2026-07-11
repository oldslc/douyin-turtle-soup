import { useState } from 'react';
import { useGameStore } from '@/stores/gameStore';
import { GlassCard } from '@/components/common/GlassCard';
import { cn } from '@/lib/utils';
import { ChevronDown, ChevronUp } from 'lucide-react';

/**
 * 汤底展示组件
 * 显示汤面（可收起）和逐字解密区（核心视觉焦点）
 */
export function SoupDisplay() {
  const { currentSoup, charStates, phase } = useGameStore();
  const [showSurface, setShowSurface] = useState(true);

  if (!currentSoup) {
    return (
      <GlassCard className="h-full p-8 text-center flex items-center justify-center" variant="default">
        <p className="text-muted-foreground text-lg">点击"开始游戏"开始新的一局</p>
      </GlassCard>
    );
  }

  // 计算揭示进度
  const contentWords = charStates.filter((s) => s.isContentWord);
  const revealedCount = contentWords.filter((s) => s.revealed).length;
  const totalContentWords = contentWords.length;
  const progress = totalContentWords === 0 ? 0 : Math.round((revealedCount / totalContentWords) * 100);

  return (
    <div className="h-full flex flex-col gap-4">
      {/* 汤面播报区（可收起） */}
      <GlassCard className="overflow-hidden shrink-0" variant="default">
        <button
          onClick={() => setShowSurface(!showSurface)}
          className="w-full p-4 flex items-center justify-between hover:bg-white/5 transition-colors"
        >
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-primary animate-pulse" />
            <span className="font-semibold text-foreground">汤面</span>
          </div>
          {showSurface ? (
            <ChevronUp className="w-5 h-5 text-muted-foreground" />
          ) : (
            <ChevronDown className="w-5 h-5 text-muted-foreground" />
          )}
        </button>
        
        {showSurface && (
          <div className="px-4 pb-4 animate-in slide-in-from-top-2 duration-300">
            <p className="text-foreground leading-relaxed text-base">
              {currentSoup.surface}
            </p>
          </div>
        )}
      </GlassCard>

      {/* 逐字揭示区（核心视觉焦点） */}
      <GlassCard className="p-6 relative flex-1" variant="primary" glow>
        {/* 揭示进度指示 */}
        <div className="absolute top-4 right-4 flex items-center gap-2 text-sm">
          <span className="text-muted-foreground">揭示进度</span>
          <span className="font-bold text-primary">{progress}%</span>
          <span className="text-muted-foreground text-xs">
            ({revealedCount}/{totalContentWords})
          </span>
        </div>

        {/* 汤底文字 - 大字显示 */}
        <div className="h-full flex items-center justify-center">
          <div className="inline-block text-left max-h-full overflow-y-auto">
            {charStates.map((state, index) => {
              const isRevealed = state.revealed;
              const isContent = state.isContentWord;

              return (
                <span
                  key={index}
                  className={cn(
                    'inline-block transition-all duration-300 font-medium',
                    // 实词未揭示时显示占位符
                    isContent && !isRevealed
                      ? 'text-2xl md:text-3xl text-muted-foreground/30 mx-0.5 select-none'
                      : 'text-xl md:text-2xl text-foreground',
                    // 刚揭示的动画效果
                    isRevealed && isContent && 'animate-in fade-in zoom-in duration-500',
                    // 虚词样式稍淡
                    !isContent && 'text-muted-foreground/70'
                  )}
                  style={{
                    minWidth: isContent && !isRevealed ? '1.5em' : undefined,
                    textAlign: 'center',
                  }}
                >
                  {isRevealed ? state.char : isContent ? '▓' : state.char}
                </span>
              );
            })}
          </div>
        </div>

        {/* 通关提示 */}
        {phase === 'completed' && (
          <div className="absolute bottom-4 left-4 right-4 p-4 bg-success/10 border border-success/30 rounded-lg animate-in fade-in slide-in-from-bottom-4 duration-500">
            <p className="text-success font-semibold text-center text-lg">
              🎉 恭喜！谜题已完全揭开！
            </p>
            <p className="text-success/70 text-center text-sm mt-1">
              5秒后自动进入下一局
            </p>
          </div>
        )}
      </GlassCard>
    </div>
  );
}
