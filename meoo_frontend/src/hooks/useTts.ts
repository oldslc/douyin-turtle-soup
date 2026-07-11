import { useState, useCallback, useEffect } from 'react';
import { useGameStore } from '@/stores/gameStore';
import { ttsService } from '@/services/ttsService';

interface UseTtsOptions {
  enabled?: boolean;
  onEnd?: () => void;
}

/**
 * TTS 语音播报 Hook
 * 桥接 ttsService 引擎与 Zustand store 的 UI 状态
 */
export function useTts(options: UseTtsOptions = {}) {
  const { enabled = true, onEnd } = options;
  
  const { isTtsPlaying, setTtsPlaying } = useGameStore();
  const [queueLength, setQueueLength] = useState(0);

  // 注册 ttsService 回调，同步状态到 store
  useEffect(() => {
    if (!enabled) return;

    ttsService.setCallbacks({
      onPlayStart: () => {
        setTtsPlaying(true);
      },
      onPlayEnd: () => {
        setTtsPlaying(false);
        onEnd?.();
      },
      onQueueChange: (queue) => {
        setQueueLength(queue.length);
      },
    });
  }, [enabled, onEnd, setTtsPlaying]);

  // 停止播放
  const stop = useCallback(() => {
    ttsService.stop();
    setTtsPlaying(false);
  }, [setTtsPlaying]);

  // 暂停播放
  const pause = useCallback(() => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.pause();
    }
  }, []);

  // 恢复播放
  const resume = useCallback(() => {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      window.speechSynthesis.resume();
    }
  }, []);

  // 跳到下一条
  const playNext = useCallback(() => {
    ttsService.stop();
    // stop 后队列中的下一条会在 onend 触发时自动播放，
    // 但由于 stop 调用了 cancel，需要手动触发
    const queue = ttsService.getQueue();
    if (queue.length > 0) {
      const next = queue.shift();
      if (next) {
        ttsService.speak(next.text, next.priority);
      }
    }
  }, []);

  // 清空队列
  const clearQueue = useCallback(() => {
    ttsService.clearQueue();
    setTtsPlaying(false);
  }, [setTtsPlaying]);

  // 立即播报（打断当前）
  const speakImmediate = useCallback(
    (text: string) => {
      if (!enabled) return;
      ttsService.speak(text, 'interrupt');
      setTtsPlaying(true);
    },
    [enabled, setTtsPlaying]
  );

  return {
    isPlaying: isTtsPlaying,
    queueLength,
    stop,
    pause,
    resume,
    playNext,
    clearQueue,
    speakImmediate,
  };
}
