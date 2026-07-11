import { useGameStore } from '@/stores/gameStore';
import { Button } from '@/components/ui/button';
import { GlassCard } from '@/components/common/GlassCard';
import { Play, RotateCcw, Settings, Volume2, VolumeX, Zap } from 'lucide-react';
import { Link } from '@tanstack/react-router';
import { useState } from 'react';

/**
 * 游戏控制组件
 */
interface GameControlsProps {
  sendJsonMessage?: (data: Record<string, unknown>) => void;
}

export function GameControls({ sendJsonMessage }: GameControlsProps) {
  const { phase, startNewGame, resetGame, addGiftRecord, addToTtsQueue } = useGameStore();
  const [ttsEnabled, setTtsEnabled] = useState(true);

  const handleStart = () => {
    /* Send start_round to backend via WebSocket */
    if (sendJsonMessage) {
      sendJsonMessage({ type: 'start_round' });
    } else {
      /* Fallback: start locally */
      startNewGame();
    }
  };

  const handleReset = () => {
    if (confirm('确定要重置游戏吗？')) {
      resetGame();
    }
  };

  // 测试送人气票
  const handleTestPopularity = () => {
    addGiftRecord('测试用户', 'popularity', 1);
    addToTtsQueue('感谢测试用户的人气票，提示：想想故事的关键人物是谁？');
  };

  return (
    <GlassCard className="p-3" variant="default">
      <div className="flex items-center justify-between gap-3">
        {/* 游戏状态 */}
        <div className="flex items-center gap-2">
          <span
            className={`w-2 h-2 rounded-full ${
              phase === 'idle'
                ? 'bg-muted-foreground'
                : phase === 'reading'
                ? 'bg-primary animate-pulse'
                : phase === 'playing'
                ? 'bg-success animate-pulse'
                : 'bg-accent animate-bounce'
            }`}
          />
          <span className="text-sm text-foreground font-medium">
            {phase === 'idle' && '等待开始'}
            {phase === 'reading' && '朗读汤面'}
            {phase === 'playing' && '游戏进行中'}
            {phase === 'completed' && '已完成'}
          </span>
        </div>

        {/* 控制按钮 */}
        <div className="flex items-center gap-2">
          {/* TTS开关 */}
          <button
            onClick={() => setTtsEnabled(!ttsEnabled)}
            className={`
              p-2 rounded-lg transition-colors
              ${ttsEnabled ? 'bg-primary/20 text-primary' : 'bg-muted/20 text-muted-foreground'}
            `}
          >
            {ttsEnabled ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
          </button>

          {phase === 'idle' || phase === 'completed' ? (
            <Button
              onClick={handleStart}
              size="sm"
              className="bg-primary hover:bg-primary/90 text-primary-foreground"
            >
              <Play className="w-4 h-4 mr-1" />
              开始游戏
            </Button>
          ) : (
            <Button
              variant="outline"
              size="sm"
              onClick={handleReset}
              className="border-destructive/50 text-destructive hover:bg-destructive/10"
            >
              <RotateCcw className="w-4 h-4 mr-1" />
              重置
            </Button>
          )}

          {/* 测试人气票按钮 */}
          {phase === 'playing' && (
            <Button
              variant="outline"
              size="sm"
              onClick={handleTestPopularity}
              className="border-cyan-500/50 text-cyan-500 hover:bg-cyan-500/10"
            >
              <Zap className="w-4 h-4 mr-1" />
              送人气票
            </Button>
          )}

          <Link to="/settings">
            <Button variant="ghost" size="icon" className="h-8 w-8">
              <Settings className="w-4 h-4" />
            </Button>
          </Link>
        </div>
      </div>
    </GlassCard>
  );
}
