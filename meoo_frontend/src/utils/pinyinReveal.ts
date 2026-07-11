import { FUNCTION_WORDS, PUNCTUATION } from '@/types';

/**
 * 拼音揭示工具
 * 用于逐字解密功能
 */

/** 检查字符是否是中文 */
export function isChinese(char: string): boolean {
  return /[\u4e00-\u9fa5]/.test(char);
}

/** 检查字符是否是标点符号 */
export function isPunctuation(char: string): boolean {
  return new RegExp(`[${PUNCTUATION}]`).test(char);
}

/** 检查字符是否是虚词 */
export function isFunctionWord(char: string): boolean {
  return FUNCTION_WORDS.includes(char);
}

/** 检查字符是否是实词（需要揭示的内容） */
export function isContentWord(char: string): boolean {
  // 必须是中文字符
  if (!isChinese(char)) return false;
  // 不能是虚词
  if (isFunctionWord(char)) return false;
  return true;
}

/** 初始化字符揭示状态 */
export function initCharStates(text: string): Array<{
  char: string;
  index: number;
  revealed: boolean;
  isContentWord: boolean;
}> {
  return Array.from(text).map((char, index) => ({
    char,
    index,
    revealed: !isContentWord(char), // 虚词和标点默认揭示
    isContentWord: isContentWord(char),
  }));
}

/** 获取未揭示的实词 */
export function getUnrevealedContentWord(
  charStates: Array<{ char: string; index: number; revealed: boolean; isContentWord: boolean }>
): { char: string; index: number } | null {
  const unrevealed = charStates.filter(
    (s) => s.isContentWord && !s.revealed
  );
  if (unrevealed.length === 0) return null;
  
  // 随机选择一个
  const random = unrevealed[Math.floor(Math.random() * unrevealed.length)];
  return { char: random.char, index: random.index };
}

/** 获取所有未揭示的某个字符的位置 */
export function getAllPositionsOfChar(
  charStates: Array<{ char: string; index: number }>,
  targetChar: string
): number[] {
  return charStates
    .map((s, index) => (s.char === targetChar ? index : -1))
    .filter((i) => i !== -1);
}

/** 获取未完全揭示的短句（到逗号为止） */
export function getUnrevealedClause(
  text: string,
  charStates: Array<{ char: string; index: number; revealed: boolean; isContentWord: boolean }>
): { startIndex: number; endIndex: number } | null {
  const clauses: Array<{ start: number; end: number }> = [];
  let start = 0;

  // 以逗号、句号、感叹号、问号作为分隔符
  for (let i = 0; i < text.length; i++) {
    if ('，。！？、；：'.includes(text[i])) {
      clauses.push({ start, end: i + 1 });
      start = i + 1;
    }
  }

  if (start < text.length) {
    clauses.push({ start, end: text.length });
  }

  // 找第一个有未揭示实词的短句
  for (const clause of clauses) {
    for (let i = clause.start; i < clause.end; i++) {
      if (charStates[i]?.isContentWord && !charStates[i]?.revealed) {
        return { startIndex: clause.start, endIndex: clause.end };
      }
    }
  }

  return null;
}

/** 获取未完全揭示的句子（兼容旧接口） */
export function getUnrevealedSentence(
  text: string,
  charStates: Array<{ char: string; index: number; revealed: boolean; isContentWord: boolean }>
): { startIndex: number; endIndex: number } | null {
  return getUnrevealedClause(text, charStates);
}

/** 计算揭示进度 */
export function calculateRevealProgress(
  charStates: Array<{ char: string; index: number; revealed: boolean; isContentWord: boolean }>
): { current: number; total: number; percentage: number } {
  const contentWords = charStates.filter((s) => s.isContentWord);
  const revealed = contentWords.filter((s) => s.revealed).length;
  const total = contentWords.length;
  
  return {
    current: revealed,
    total,
    percentage: total === 0 ? 0 : Math.round((revealed / total) * 100),
  };
}