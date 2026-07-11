/**
 * TTS 语音服务
 * 支持优先级队列、打断逻辑、LIFO 播报机制
 */

import type { TtsPriority } from '@/types';

export interface TtsQueueItem {
  id: string;
  text: string;
  priority: TtsPriority;
}

interface TtsCallbacks {
  onPlayStart?: (text: string) => void;
  onPlayEnd?: (text: string) => void;
  onQueueChange?: (queue: TtsQueueItem[]) => void;
}

class TtsService {
  private synth: SpeechSynthesis | null = null;
  private queue: TtsQueueItem[] = [];
  private isPlaying = false;
  private currentUtterance: SpeechSynthesisUtterance | null = null;
  private callbacks: TtsCallbacks = {};

  constructor() {
    if (typeof window !== 'undefined' && 'speechSynthesis' in window) {
      this.synth = window.speechSynthesis;
    }
  }

  /**
   * ע��ص�
   */
  setCallbacks(callbacks: TtsCallbacks): void {
    this.callbacks = { ...this.callbacks, ...callbacks };
  }

  /**
   * ���Ĳ�������
   * - normal: �����β������ȳ��������µ�Ļ��β����
   * - urgent: �������ͷ�����������л����������ͨ��Ļ��
   * - interrupt: ������ϵ�ǰ���ţ���ն��У����������ݣ���ͨ�ز�����
   */
  speak(text: string, priority: TtsPriority = 'normal'): void {
    if (!this.synth || !text.trim()) return;

    const item: TtsQueueItem = {
      id: `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`,
      text: text.trim(),
      priority,
    };

    switch (priority) {
      case 'interrupt':
        // ��ϵ�ǰ���ţ���ն��У���������
        this.stop();
        this.queue = [item];
        this.playNext();
        break;

      case 'urgent':
        // �������ͷ������������ͨ��Ļ
        this.queue.unshift(item);
        // ���ƶ��г���
        this.trimQueue();
        // ���û���ڲ��ţ���ʼ����
        if (!this.isPlaying) {
          this.playNext();
        }
        break;

      case 'normal':
      default:
        // �����β������ȳ����µ�Ļ��β�����Ȳ��ɵ�Ļ��
        this.queue.push(item);
        this.trimQueue();
        if (!this.isPlaying) {
          this.playNext();
        }
        break;
    }

    this.notifyQueueChange();
  }

  /**
   * ֹͣ��ǰ����
   */
  stop(): void {
    if (this.synth) {
      this.synth.cancel();
    }
    this.currentUtterance = null;
    this.isPlaying = false;
  }

  /**
   * ��ն��в�ֹͣ����
   */
  clearQueue(): void {
    this.stop();
    this.queue = [];
    this.notifyQueueChange();
  }

  /**
   * ��ȡ��ǰ����
   */
  getQueue(): TtsQueueItem[] {
    return [...this.queue];
  }

  /**
   * ��ȡ���г���
   */
  getQueueLength(): number {
    return this.queue.length;
  }

  /**
   * �Ƿ����ڲ���
   */
  getIsPlaying(): boolean {
    return this.isPlaying;
  }

  /**
   * ������һ��
   */
  private playNext(): void {
    if (!this.synth || this.queue.length === 0) {
      this.isPlaying = false;
      this.currentUtterance = null;
      this.notifyQueueChange();
      return;
    }

    const item = this.queue.shift()!;
    this.notifyQueueChange();

    const utterance = new SpeechSynthesisUtterance(item.text);
    utterance.lang = 'zh-CN';
    utterance.rate = 1.0;
    utterance.pitch = 1.0;
    utterance.volume = 1.0;

    utterance.onend = () => {
      this.currentUtterance = null;
      this.isPlaying = false;
      this.callbacks.onPlayEnd?.(item.text);
      // ���Ŷ����е���һ��
      this.playNext();
    };

    utterance.onerror = (event) => {
      console.error('[TTS] Playback error:', event.error);
      this.currentUtterance = null;
      this.isPlaying = false;
      this.playNext();
    };

    this.currentUtterance = utterance;
    this.isPlaying = true;
    this.callbacks.onPlayStart?.(item.text);
    this.synth.speak(utterance);
  }

  /**
   * ���ƶ��г��ȣ�����ʱ�Ƴ���ɵ���ͨ��Ļ
   */
  private trimQueue(): void {
    const MAX_QUEUE_SIZE = 20;
    while (this.queue.length > MAX_QUEUE_SIZE) {
      // �ҵ����Ƴ���ɵ� normal ���ȼ���Ϣ
      const normalIdx = this.queue.findIndex(
        (item) => item.priority === 'normal'
      );
      if (normalIdx !== -1) {
        this.queue.splice(normalIdx, 1);
      } else {
        // û����ͨ��Ϣ���Ƴ����Ƴ���β
        this.queue.pop();
      }
    }
  }

  /**
   * ֪ͨ���б仯
   */
  private notifyQueueChange(): void {
    this.callbacks.onQueueChange?.(this.queue);
  }
}

// ��������
export const ttsService = new TtsService();
