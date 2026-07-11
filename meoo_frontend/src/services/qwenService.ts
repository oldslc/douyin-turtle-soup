/**
 * Qwen AI 服务
 * 用于弹幕三分类和礼物索要话术生成
 */

import type { BarrageResult } from '@/types';

const QWEN_API_URL = import.meta.env.VITE_QWEN_API_URL || 'http://localhost:3009';

interface ClassifyRequest {
  text: string;
  answer: string;
  keywords: string[];
}

interface ClassifyResponse {
  text: string;
  answerType: string;  // "是" | "不是" | "是也不是"
  layer: string;       // "rule" or "qwen"
  latencyMs: number;
}

interface GiftSolicitRequest {
  gameState: {
    duration: number;       // 游戏时长（秒）
    revealProgress: number; // 揭示进度（0-100）
    qaCount: number;        // 问答次数
    lastRevealTime: number; // 上次揭示时间
  };
}

interface GiftSolicitResponse {
  message: string;
}

/**
 * 弹幕三分类
 * @param text 观众提问
 * @param answer 汤底答案
 * @param keywords 关键词列表
 */
export async function classifyBarrage(
  text: string,
  answer: string,
  keywords: string[]
): Promise<BarrageResult> {
  try {
    const response = await fetch(`${QWEN_API_URL}/classify`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({
        text,
        answer,
        keywords,
      } as ClassifyRequest),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data: ClassifyResponse = await response.json();
    // 映射后端 answerType 到 BarrageResult
    switch (data.answerType) {
      case '是': return 'yes';
      case '不是': return 'no';
      case '是也不是': return 'maybe';
      default: return 'irrelevant';
    }
  } catch (error) {
    console.error('[Qwen] Classification failed:', error);
    // 降级为随机结果
    return fallbackClassify(text);
  }
}

/**
 * 生成礼物索要话术
 */
export async function generateGiftSolicit(
  gameState: GiftSolicitRequest['gameState']
): Promise<string> {
  try {
    const response = await fetch(`${QWEN_API_URL}/gift-solicit`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ gameState } as GiftSolicitRequest),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data: GiftSolicitResponse = await response.json();
    return data.message;
  } catch (error) {
    console.error('[Qwen] Gift solicit failed:', error);
    return fallbackGiftSolicit(gameState);
  }
}

/**
 * 生成方向引导提示
 */
export async function generateHint(
  qaHistory: Array<{ question: string; result: BarrageResult }>,
  answer: string
): Promise<string> {
  try {
    const response = await fetch(`${QWEN_API_URL}/hint`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
      },
      body: JSON.stringify({ qaHistory, answer }),
    });

    if (!response.ok) {
      throw new Error(`HTTP error! status: ${response.status}`);
    }

    const data: { hint: string } = await response.json();
    return data.hint;
  } catch (error) {
    console.error('[Qwen] Hint generation failed:', error);
    return '试试从故事的关键人物入手？';
  }
}

// 降级分类函数
function fallbackClassify(question: string): BarrageResult {
  const lowerQ = question.toLowerCase();
  
  if (lowerQ.includes('是') || lowerQ.includes('对')) {
    return Math.random() > 0.5 ? 'yes' : 'maybe';
  }
  
  const rand = Math.random();
  if (rand < 0.3) return 'yes';
  if (rand < 0.6) return 'maybe';
  if (rand < 0.85) return 'no';
  return 'irrelevant';
}

// 降级礼物索要话术
function fallbackGiftSolicit(gameState: GiftSolicitRequest['gameState']): string {
  const messages = [
    '玩这么久了，帮主播卡个灯牌吧~',
    '就差一点就能揭示了，送个啤酒助力一下？',
    '要不要送个棒棒糖给个提示？',
    '觉得有趣的话，点个关注不迷路哦~',
    '送个小礼物，主播给你更多提示！',
  ];
  
  if (gameState.revealProgress < 20) {
    return '刚开始玩，送个礼物支持一下吧~';
  }
  
  if (gameState.revealProgress > 70) {
    return '快揭开了！送个墨镜直接通关？';
  }
  
  return messages[Math.floor(Math.random() * messages.length)];
}