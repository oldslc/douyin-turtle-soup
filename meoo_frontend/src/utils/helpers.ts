/**
 * 辅助工具函数
 */

/** 生成唯一ID */
export function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`;
}

/** 延迟执行 */
export function delay(ms: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, ms));
}

/** 节流函数 */
export function throttle<T extends (...args: unknown[]) => void>(
  fn: T,
  limit: number
): (...args: Parameters<T>) => void {
  let inThrottle = false;
  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      fn(...args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
}

/** 防抖函数 */
export function debounce<T extends (...args: unknown[]) => void>(
  fn: T,
  wait: number
): (...args: Parameters<T>) => void {
  let timeout: ReturnType<typeof setTimeout>;
  return (...args: Parameters<T>) => {
    clearTimeout(timeout);
    timeout = setTimeout(() => fn(...args), wait);
  };
}

/** 格式化时间 */
export function formatTime(timestamp: number): string {
  const date = new Date(timestamp);
  const hours = date.getHours().toString().padStart(2, '0');
  const minutes = date.getMinutes().toString().padStart(2, '0');
  const seconds = date.getSeconds().toString().padStart(2, '0');
  return `${hours}:${minutes}:${seconds}`;
}

/** 截断文本 */
export function truncateText(text: string, maxLength: number): string {
  if (text.length <= maxLength) return text;
  return text.slice(0, maxLength) + '...';
}

/** 计算揭示进度百分比 */
export function calculateRevealProgress(
  totalChars: number,
  revealedCount: number
): number {
  if (totalChars === 0) return 0;
  return Math.round((revealedCount / totalChars) * 100);
}

/** 过滤无效弹幕 */
export function filterInvalidBarrage(content: string): boolean {
  if (!content || content.trim().length === 0) return false;
  
  const trimmed = content.trim();
  
  // 纯标点
  if (/^[\W\s]+$/.test(trimmed)) return false;
  
  // 纯数字
  if (/^\d+$/.test(trimmed)) return false;
  
  // 长度过短或过长
  if (trimmed.length < 3 || trimmed.length > 30) return false;
  
  // 常见无意义弹幕
  const meaningless = ['哈哈哈', '666', '主播好', '你好', '测试', '啊啊啊'];
  if (meaningless.some((m) => trimmed.includes(m))) return false;
  
  return true;
}

/** 安全解析JSON */
export function safeJsonParse<T>(json: string, fallback: T): T {
  try {
    return JSON.parse(json) as T;
  } catch {
    return fallback;
  }
}
