// 海龟汤游戏 - 类型定义

/** 游戏阶段 */
export type GamePhase = 'idle' | 'reading' | 'playing' | 'completed';

/** 弹幕分类结果 */
export type BarrageResult = 'yes' | 'maybe' | 'no' | 'irrelevant';

/** 礼物类型 */
export type GiftType = 'like' | 'fan_light' | 'popularity' | 'beer' | 'lollipop' | 'sunglasses';

/** TTS优先级 */
export type TtsPriority = 'normal' | 'urgent' | 'interrupt';

/** 汤的数据结构 */
export interface SoupData {
  id: string;
  title: string;
  surface: string;
  bottom: string;
  keywords: string[];
  difficulty: 'easy' | 'medium' | 'hard';
  specificQuestions?: Array<{
    text: string;
    answer: '是' | '不是' | '是也不是';
  }>;
}

/** 字符显示状态 */
export interface CharRevealState {
  char: string;
  index: number;
  revealed: boolean;
  isContentWord: boolean;
}

/** 问答记录 */
export interface QaRecord {
  id: string;
  user: string;
  question: string;
  result: BarrageResult;
  timestamp: number;
}

/** 礼物记录 */
export interface GiftRecord {
  id: string;
  user: string;
  giftType: GiftType;
  count: number;
  timestamp: number;
}

/** 贡献记录 */
export interface ContributionRecord {
  user: string;
  revealedCount: number;
}

/** WebSocket消息结构 */
export interface WsMessage {
  type: 'danmu' | 'gift' | 'like' | 'system';
  data: {
    user?: string;
    content?: string;
    giftName?: string;
    giftCount?: number;
    likeCount?: number;
    message?: string;
  };
}

/** 游戏状态 */
export interface GameState {
  phase: GamePhase;
  currentSoup: SoupData | null;
  charStates: CharRevealState[];
  qaHistory: QaRecord[];
  giftHistory: GiftRecord[];
  contributions: ContributionRecord[];
  likeProgress: number;
  likeThreshold: number;
  guessCount: number;
  startTime: number;
  ttsQueue: string[];
  isTtsPlaying: boolean;

  // 防卡死状态
  antiStallLastRevealTime: number;
  antiStallSinceRevealCount: number;
  antiStallConsecutiveTriggers: number;
}

/** 游戏配置 */
export interface GameConfig {
  wsUrl: string;
  qwenApiUrl: string;
  ttsApiUrl: string;
  likeThreshold: number;
  antiStuckInterval: number;
  maxBarrageHistory: number;
  ttsEnabled: boolean;
}

/** 默认配置 */
export const DEFAULT_CONFIG: GameConfig = {
  wsUrl: 'ws://localhost:9876',
  qwenApiUrl: 'http://localhost:3009',
  ttsApiUrl: 'http://localhost:3006',
  likeThreshold: 500,
  antiStuckInterval: 180000,
  maxBarrageHistory: 100,
  ttsEnabled: true,
};

/** 虚词列表 */
export const FUNCTION_WORDS = '的了吗是在和呢吧着过得地个一没有就都而但又如果因为所以然后于是向对从到把被给让每只想会能可以很太非常已经正在曾经将要这那你我他她它们上下里外前中时还也再才刚做是说看来去';

/** 标点符号 */
export const PUNCTUATION = '，。、？！；：“”‘’（）【】《》——……·';
