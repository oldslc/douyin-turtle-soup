import { useGameStore } from '@/stores/gameStore';
import { GlassCard } from '@/components/common/GlassCard';
import { Trophy, Medal, Award } from 'lucide-react';

const RANK_ICONS = [Trophy, Medal, Award];
const RANK_COLORS = ['text-accent', 'text-muted-foreground', 'text-muted-foreground/70'];

/**
 * 贡献榜组件
 * 显示揭示贡献排行
 */
export function ContributionBoard() {
  const { contributions } = useGameStore();

  return (
    <GlassCard className="p-4" variant="default">
      <h3 className="font-semibold text-foreground mb-3 flex items-center gap-2 text-sm">
        <Trophy className="w-4 h-4 text-accent" />
        揭示贡献榜
      </h3>

      {contributions.length === 0 ? (
        <div className="text-center text-muted-foreground text-sm py-4">
          暂无贡献记录
        </div>
      ) : (
        <div className="space-y-2">
          {contributions.slice(0, 5).map((record, index) => {
            const Icon = RANK_ICONS[index] || Award;
            const colorClass = RANK_COLORS[index] || 'text-muted-foreground/50';
            const rankEmoji = index === 0 ? '🥇' : index === 1 ? '🥈' : index === 2 ? '🥉' : `${index + 1}.`;

            return (
              <div
                key={record.user}
                className="flex items-center justify-between p-2 rounded-lg bg-muted/20"
              >
                <div className="flex items-center gap-2">
                  <span className="text-lg">{rankEmoji}</span>
                  <span className="text-sm font-medium text-foreground">
                    {record.user}
                  </span>
                </div>
                <div className="flex items-center gap-1 text-sm text-muted-foreground">
                  <Icon className={cn('w-4 h-4', colorClass)} />
                  <span>揭示{record.revealedCount}字</span>
                </div>
              </div>
            );
          })}
        </div>
      )}
    </GlassCard>
  );
}

// 导入 cn
import { cn } from '@/lib/utils';
