import { useState, useCallback, useRef } from 'react';
import type { QaRecord, BarrageResult } from '@/types';
import { generateId } from '@/utils/helpers';

interface UseBarrageOptions {
  maxHistory?: number;
}

/**
 * 弹幕处理 Hook
 * 管理弹幕队列和历史记录
 */
export function useBarrage(options: UseBarrageOptions = {}) {
  const { maxHistory = 100 } = options;
  
  const [qaHistory, setQaHistory] = useState<QaRecord[]>([]);
  const queueRef = useRef<string[]>([]);

  // 添加问答记录
  const addQaRecord = useCallback(
    (user: string, question: string, result: BarrageResult) => {
      const record: QaRecord = {
        id: generateId(),
        user,
        question,
        result,
        timestamp: Date.now(),
      };

      setQaHistory((prev) => {
        const newHistory = [record, ...prev];
        return newHistory.slice(0, maxHistory);
      });
    },
    [maxHistory]
  );

  // 清空历史
  const clearHistory = useCallback(() => {
    setQaHistory([]);
  }, []);

  // 添加到待处理队列
  const enqueue = useCallback((text: string) => {
    queueRef.current.push(text);
  }, []);

  // 从队列取出（后进先出）
  const dequeue = useCallback((): string | undefined => {
    return queueRef.current.pop();
  }, []);

  // 获取队列长度
  const getQueueLength = useCallback(() => {
    return queueRef.current.length;
  }, []);

  // 清空队列
  const clearQueue = useCallback(() => {
    queueRef.current = [];
  }, []);

  return {
    qaHistory,
    addQaRecord,
    clearHistory,
    enqueue,
    dequeue,
    getQueueLength,
    clearQueue,
  };
}
