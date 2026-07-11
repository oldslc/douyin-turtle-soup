import { useEffect, useRef } from 'react';
import { useGameStore } from '@/stores/gameStore';
import { GlassCard } from '@/components/common/GlassCard';
import { cn } from '@/lib/utils';
import type { BarrageResult } from '@/types';

const RESULT_STYLES: Record<BarrageResult, { bg: string; text: string; label: string; icon: string }> = {
  yes: {
    bg: 'bg-success/20 border-success/40',
    text: 'text-success',
    label: '是',
    icon: '🟢',
  },
  maybe: {
    bg: 'bg-warning/20 border-warning/40',
    text: 'text-warning',
    label: '是也不是',
    icon: '🟡',
  },
  no: {
    bg: 'bg-error/20 border-error/40',
    text: 'text-error',
    label: '不是',
    icon: '🔴',
  },
  irrelevant: {
    bg: 'bg-muted/20 border-muted/40',
    text: 'text-muted-foreground',
    label: '不相关',
    icon: '⚪',
  },
};

/**
 * 问答气泡组件
 * 显示弹幕问答记录（轨道B）
 */
export function QaBubble() {
  const { qaHistory } = useGameStore();
  const scrollRef = useRef<HTMLDivElement>(null);

  // 自动滚动到底部
  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [qaHistory]);

  return (
    <GlassCard className="h-full flex flex-col" variant="default">
      <div className="p-3 border-b border-border/30">
        <h3 className="font-semibold text-foreground flex items-center gap-2 text-sm">
          <span className="w-2 h-2 rounded-full bg-secondary animate-pulse" />
          问答气泡流
          <span className="text-xs text-muted-foreground ml-auto">
            {qaHistory.length} 条
          </span>
        </h3>
      </div>

      <div
        ref={scrollRef}
        className="flex-1 overflow-y-auto p-3 space-y-2"
      >
        {qaHistory.length === 0 ? (
          <div className="h-full flex items-center justify-center text-muted-foreground text-sm">
            等待弹幕提问...
          </div>
        ) : (
          qaHistory.map((record) => {
            const style = RESULT_STYLES[record.result];

            return (
              <div
                key={record.id}
                className={cn(
                  'p-2.5 rounded-lg border backdrop-blur-sm animate-in fade-in slide-in-from-right-2 duration-200',
                  style.bg
                )}
              >
                <div className="flex items-start gap-2">
                  <span className="text-sm font-medium text-foreground shrink-0">
                    {record.user}
                  </span>
                  <span className="text-sm text-foreground/80 flex-1">
                    {record.question}
                  </span>
                  <span
                    className={cn(
                      'text-xs font-bold px-2 py-0.5 rounded-full shrink-0',
                      style.text,
                      'bg-background/50'
                    )}
                  >
                    {style.label}
                  </span>
                </div>
              </div>
            );
          })
        )}
      </div>
    </GlassCard>
  );
}
