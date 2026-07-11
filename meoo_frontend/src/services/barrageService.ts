/**
 * 弹幕服务
 * 处理弹幕消息的过滤、分类和处理
 */

import type { BarrageResult } from '@/types';
import { filterInvalidBarrage } from '@/utils/helpers';
import { classifyBarrage } from '@/services/qwenService';

export interface BarrageProcessResult {
  valid: boolean;
  result?: BarrageResult;
  revealedChar?: string;
}

/**
 * 处理弹幕消息
 * @param content 弹幕内容
 * @param soupBottom 汤底原文
 * @param revealedChars 已揭示的字符集合
 * @param keywords 关键词列表
 */
export async function processBarrage(
  content: string,
  soupBottom: string,
  revealedChars: Set<string>,
  keywords: string[]
): Promise<BarrageProcessResult> {
  // 第一层过滤
  if (!filterInvalidBarrage(content)) {
    return { valid: false };
  }

  // 轨道A：逐字解密检查（不拦截，继续传到轨道B）
  let revealedChar: string | undefined;
  for (const char of content) {
    if (soupBottom.includes(char) && !revealedChars.has(char)) {
      revealedChar = char;
      break;
    }
  }

  // 轨道B：AI三分类（每条弹幕必走，不跳过）
  const result = await classifyBarrage(content, soupBottom, keywords);
  
  return {
    valid: true,
    revealedChar,
    result,
  };
}

/**
 * 将 BarrageResult 映射为中文播报文本
 */
export function getResultText(result: BarrageResult): string {
  switch (result) {
    case 'yes':
      return '是的';
    case 'maybe':
      return '是也不是';
    case 'no':
      return '不是';
    case 'irrelevant':
      return '不相关';
  }
}

/**
 * 批量处理弹幕
 */
export async function processBarrageBatch(
  messages: Array<{ user: string; content: string }>,
  soupBottom: string,
  revealedChars: Set<string>,
  keywords: string[]
): Promise<Array<{ user: string; result: BarrageProcessResult }>> {
  const results: Array<{ user: string; result: BarrageProcessResult }> = [];
  
  for (const msg of messages) {
    const result = await processBarrage(msg.content, soupBottom, revealedChars, keywords);
    results.push({ user: msg.user, result });
  }
  
  return results;
}