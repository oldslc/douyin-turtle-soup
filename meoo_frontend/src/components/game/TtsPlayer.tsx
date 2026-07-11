import { useTts } from '@/hooks/useTts';
import { GlassCard } from '@/components/common/GlassCard';
import { Volume2, VolumeX, Pause, Play, SkipForward } from 'lucide-react';
import { Button } from '@/components/ui/button';

/**
 * TTS播放器组件
 * 控制语音播报
 */
export function TtsPlayer() {
  const { isPlaying, queueLength, stop, pause, resume, playNext } = useTts();

  return (
    <GlassCard className="p-3" variant="default">
      <div className="flex items-center justify-between">
        <div className="flex items-center gap-2">
          {isPlaying ? (
            <Volume2 className="w-4 h-4 text-primary animate-pulse" />
          ) : (
            <VolumeX className="w-4 h-4 text-muted-foreground" />
          )}
          <span className="text-sm text-foreground">
            {isPlaying ? '播报中' : '已暂停'}
          </span>
          {queueLength > 0 && (
            <span className="text-xs text-muted-foreground">
              (队列: {queueLength})
            </span>
          )}
        </div>

        <div className="flex items-center gap-1">
          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={isPlaying ? pause : resume}
          >
            {isPlaying ? (
              <Pause className="w-4 h-4" />
            ) : (
              <Play className="w-4 h-4" />
            )}
          </Button>

          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={stop}
          >
            <VolumeX className="w-4 h-4" />
          </Button>

          <Button
            variant="ghost"
            size="icon"
            className="h-8 w-8"
            onClick={playNext}
            disabled={queueLength === 0}
          >
            <SkipForward className="w-4 h-4" />
          </Button>
        </div>
      </div>
    </GlassCard>
  );
}
