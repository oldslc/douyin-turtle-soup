import { create } from 'zustand';
import type {
  GameState,
  GamePhase,
  SoupData,
  QaRecord,
  GiftRecord,
  ContributionRecord,
  BarrageResult,
  GiftType,
  CharRevealState,
  TtsPriority,
} from '@/types';
import { getRandomSoup } from '@/data/soups';
import { generateId } from '@/utils/helpers';
import { initCharStates, calculateRevealProgress } from '@/utils/pinyinReveal';
import { ttsService } from '@/services/ttsService';
import { SOUPS } from '@/data/soups';

interface GameStore extends GameState {
  // Actions
  setPhase: (phase: GamePhase) => void;
  startNewGame: () => void;
  applyGameStart: (soup: SoupData, charStates: CharRevealState[]) => void;
  revealChar: (index: number) => void;
  revealAllChars: () => void;
  addQaRecord: (user: string, question: string, result: BarrageResult) => void;
  addGiftRecord: (user: string, giftType: GiftType, count: number) => void;
  addContribution: (user: string, count: number) => void;
  updateLikeProgress: (count: number) => void;
  incrementGuessCount: () => void;
  addToTtsQueue: (text: string, priority?: TtsPriority) => void;
  pushTtsMessage: (text: string, priority: TtsPriority) => void;
  removeFromTtsQueue: () => void;
  setTtsQueue: (queue: string[]) => void;
  clearTtsQueue: () => void;
  setTtsPlaying: (playing: boolean) => void;
  clearQaHistory: () => void;
  incrementAntiStallCount: () => void;
  resetGame: () => void;
  getRevealProgress: () => { current: number; total: number; percentage: number };
  getGameDuration: () => number;
}

const initialState: Omit<GameState, 'getRevealProgress' | 'getGameDuration'> = {
  phase: 'idle',
  currentSoup: null,
  charStates: [],
  qaHistory: [],
  giftHistory: [],
  contributions: [],
  likeProgress: 0,
  likeThreshold: 500,
  guessCount: 0,
  startTime: 0,
  ttsQueue: [],
  isTtsPlaying: false,
  antiStallLastRevealTime: 0,
  antiStallSinceRevealCount: 0,
  antiStallConsecutiveTriggers: 0,
};

export const useGameStore = create<GameStore>((set, get) => ({
  ...initialState,

  setPhase: (phase) => set({ phase }),

  startNewGame: () => {
    const soup = getRandomSoup();
    const charStates = initCharStates(soup.bottom);

    ttsService.clearQueue();

    set({
      phase: 'reading',
      currentSoup: soup,
      charStates,
      qaHistory: [],
      giftHistory: [],
      contributions: [],
      likeProgress: 0,
      guessCount: 0,
      startTime: Date.now(),
      ttsQueue: [],
      isTtsPlaying: false,
      antiStallLastRevealTime: 0,
      antiStallSinceRevealCount: 0,
      antiStallConsecutiveTriggers: 0,
    });
  },

  applyGameStart: (soup, charStates) => {
    ttsService.clearQueue();
    set({
      phase: 'playing',
      currentSoup: soup,
      charStates,
      qaHistory: [],
      giftHistory: [],
      contributions: [],
      likeProgress: 0,
      guessCount: 0,
      startTime: Date.now(),
      ttsQueue: [],
      isTtsPlaying: false,
      antiStallLastRevealTime: 0,
      antiStallSinceRevealCount: 0,
      antiStallConsecutiveTriggers: 0,
    });
  },

  revealChar: (index) =>
    set((state) => {
      const newCharStates = [...state.charStates];
      if (newCharStates[index] && !newCharStates[index].revealed) {
        newCharStates[index] = { ...newCharStates[index], revealed: true };
      }

      // 检查是否全部揭示
      const allRevealed = newCharStates
        .filter((s) => s.isContentWord)
        .every((s) => s.revealed);
      
      return {
        charStates: newCharStates,
        antiStallLastRevealTime: Date.now(),
        antiStallSinceRevealCount: 0,
        phase: allRevealed ? 'completed' : state.phase,
      };
    }),

  revealAllChars: () =>
    set((state) => ({
      charStates: state.charStates.map((s) => ({ ...s, revealed: true })),
      phase: 'completed',
    })),

  addQaRecord: (user, question, result) =>
    set((state) => {
      const record: QaRecord = {
        id: generateId(),
        user,
        question,
        result,
        timestamp: Date.now(),
      };
      const newHistory = [record, ...state.qaHistory].slice(0, 100);
      return { qaHistory: newHistory };
    }),

  addGiftRecord: (user, giftType, count) =>
    set((state) => {
      const record: GiftRecord = {
        id: generateId(),
        user,
        giftType,
        count,
        timestamp: Date.now(),
      };
      const newHistory = [record, ...state.giftHistory].slice(0, 50);
      return { giftHistory: newHistory };
    }),

  addContribution: (user, count) =>
    set((state) => {
      const existing = state.contributions.find((c) => c.user === user);
      let newContributions: ContributionRecord[];
      
      if (existing) {
        newContributions = state.contributions.map((c) =>
          c.user === user ? { ...c, revealedCount: c.revealedCount + count } : c
        );
      } else {
        newContributions = [...state.contributions, { user, revealedCount: count }];
      }
      
      // 按揭示数量排序
      newContributions.sort((a, b) => b.revealedCount - a.revealedCount);
      
      return { contributions: newContributions.slice(0, 10) };
    }),

  updateLikeProgress: (count) =>
    set((state) => {
      const newProgress = state.likeProgress + count;
      if (newProgress >= state.likeThreshold) {
        return { likeProgress: newProgress - state.likeThreshold };
      }
      return { likeProgress: newProgress };
    }),

  incrementGuessCount: () =>
    set((state) => ({ guessCount: state.guessCount + 1 })),

  /**
   * 将消息加入 TTS 队列，默认 normal 优先级
   */
  addToTtsQueue: (text, priority = 'normal') => {
    ttsService.speak(text, priority);
    set({ isTtsPlaying: true });
  },

  /**
   * 按指定优先级推送 TTS 消息
   */
  pushTtsMessage: (text, priority) => {
    ttsService.speak(text, priority);
    set({ isTtsPlaying: true });
  },

  /**
   * 从队列移除第一条消息（保留旧接口兼容）
   */
  removeFromTtsQueue: () => {
    const queue = ttsService.getQueue();
    if (queue.length > 0) {
      ttsService.getQueue().shift();
    }
  },

  /**
   * 替换整个队列（供显示用）
   */
  setTtsQueue: (queue) => set({ ttsQueue: queue }),

  /**
   * 清空 TTS 队列
   */
  clearTtsQueue: () => {
    ttsService.clearQueue();
    set({ ttsQueue: [], isTtsPlaying: false });
  },

  setTtsPlaying: (playing) => set({ isTtsPlaying: playing }),

  clearQaHistory: () => set({ qaHistory: [] }),

  incrementAntiStallCount: () =>
    set((state) => ({
      antiStallSinceRevealCount: state.antiStallSinceRevealCount + 1,
    })),

  resetGame: () => {
    ttsService.clearQueue();
    set(initialState);
  },

  getRevealProgress: () => {
    const { charStates } = get();
    return calculateRevealProgress(charStates);
  },

  getGameDuration: () => {
    const { startTime } = get();
    if (startTime === 0) return 0;
    return Math.floor((Date.now() - startTime) / 1000);
  },
}));
