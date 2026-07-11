import { GlassCard } from '@/components/common/GlassCard';
import { Turtle } from 'lucide-react';

/**
 * 顶部栏组件
 */
export function Header() {
  return (
    <GlassCard className="p-4 sticky top-0 z-50" variant="default">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-xl bg-gradient-to-br from-primary to-secondary flex items-center justify-center shadow-lg">
            <Turtle className="w-6 h-6 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-foreground tracking-tight">
              CCcat 海龟汤
            </h1>
            <p className="text-xs text-muted-foreground">
              抖音直播弹幕互动游戏
            </p>
          </div>
        </div>

        {/* 连接状态指示器（可选） */}
        <div className="hidden sm:flex items-center gap-2">
          <span className="w-2 h-2 rounded-full bg-success animate-pulse" />
          <span className="text-xs text-muted-foreground">已连接</span>
        </div>
      </div>
    </GlassCard>
  );
}
