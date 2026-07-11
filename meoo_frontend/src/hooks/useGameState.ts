import { useCallback, useEffect } from 'react';
import { useGameStore } from '@/stores/gameStore';
import type { WsMessage, GiftType } from '@/types';
import { processBarrage, getResultText } from '@/services/barrageService';
import { getUnrevealedContentWord, getUnrevealedSentence, getAllPositionsOfChar } from '@/utils/pinyinReveal';
import { ttsService } from '@/services/ttsService';

/**
 * 游戏核心逻辑 Hook
 * 处理弹幕、礼物、点赞等交互
 */
export function useGameState() {
  const {
    phase,
    currentSoup,
    charStates,
    likeProgress,
    likeThreshold,
    setPhase,
    startNewGame,
    revealChar,
    revealAllChars,
    addQaRecord,
    addGiftRecord,
    updateLikeProgress,
    addToTtsQueue,
    incrementAntiStallCount,
  } = useGameStore();

  // 处理弹幕消息
  const handleBarrage = useCallback(
    async (user: string, content: string) => {
      if (!currentSoup || phase !== 'playing') return;

      // 构建已揭示字符集合
      const revealedChars = new Set(
        charStates.filter((s) => s.revealed).map((s) => s.char)
      );

      const processResult = await processBarrage(
        content,
        currentSoup.bottom,
        revealedChars,
        currentSoup.keywords
      );

      if (!processResult.valid) return;

      // 轨道A：逐字解密揭示
      if (processResult.revealedChar) {
        const char = processResult.revealedChar;
        for (let j = 0; j < currentSoup.bottom.length; j++) {
          if (currentSoup.bottom[j] === char) {
            revealChar(j);
          }
        }
        console.log(`[Game] 弹幕 "${content}" 揭示了字符 "${char}"`);
      }

      // 未揭示新字时增加弹幕计数
      if (!processResult.revealedChar) {
        incrementAntiStallCount();
      }

      // 轨道B：AI三分类结果处理
      if (processResult.result) {
        addQaRecord(user, content, processResult.result);
        const resultText = getResultText(processResult.result);
        addToTtsQueue(content + '，' + resultText);
        console.log(`[Game] ${user}: "${content}" -> ${resultText}`);
      }
    },
    [currentSoup, phase, charStates, revealChar, addQaRecord, addToTtsQueue, incrementAntiStallCount]
  );

  // 处理礼物消息
  const handleGift = useCallback(
    (user: string, giftName: string, count: number) => {
      if (!currentSoup) return;

      const giftTypeMap: Record<string, GiftType> = {
        '点赞': 'like',
        '粉丝灯牌': 'fan_light',
        '人气票': 'popularity',
        '啤酒': 'beer',
        '棒棒糖': 'lollipop',
        '墨镜': 'sunglasses',
      };

      const giftType = giftTypeMap[giftName];
      if (!giftType) return;

      addGiftRecord(user, giftType, count);
      console.log(`[Game] 收到礼物: ${user} 送出 ${giftName} x${count}`);

      // 根据礼物类型触发不同效果
      switch (giftType) {
        case 'like':
          // 点赞累积
          updateLikeProgress(count);
          if (likeProgress + count >= likeThreshold) {
            // 达到阈值，揭示一个字（相同字一起揭示）
            const keyword = getUnrevealedContentWord(charStates);
            if (keyword) {
              const positions = getAllPositionsOfChar(charStates, keyword.char);
              for (const pos of positions) {
                revealChar(pos);
              }
              addToTtsQueue('感谢' + user + '的点赞，揭示了"' + keyword.char + '"字！', 'urgent');
            }
          }
          break;

        case 'fan_light':
          // 粉丝灯牌：随机解锁一句
          {
            const sentence = getUnrevealedSentence(currentSoup.bottom, charStates);
            if (sentence) {
              for (let i = sentence.startIndex; i < sentence.endIndex; i++) {
                revealChar(i);
              }
              addToTtsQueue('感谢' + user + '的粉丝灯牌，解锁了一句话！', 'urgent');
            }
          }
          break;

        case 'beer':
          // 啤酒：随机揭示一字（相同字一起揭示）
          {
            const keyword = getUnrevealedContentWord(charStates);
            if (keyword) {
              const positions = getAllPositionsOfChar(charStates, keyword.char);
              for (const pos of positions) {
                revealChar(pos);
              }
              addToTtsQueue('感谢' + user + '的啤酒，揭示了"' + keyword.char + '"字！', 'urgent');
            }
          }
          break;

        case 'lollipop':
          // 棒棒糖：随机揭示一句
          {
            const sentence = getUnrevealedSentence(currentSoup.bottom, charStates);
            if (sentence) {
              for (let i = sentence.startIndex; i < sentence.endIndex; i++) {
                revealChar(i);
              }
              addToTtsQueue('感谢' + user + '的棒棒糖，揭示了一句话！', 'urgent');
            }
          }
          break;

        case 'sunglasses':
          // 墨镜：揭示全文
          revealAllChars();
          addToTtsQueue('恭喜' + user + '送出墨镜，谜题已揭开！', 'interrupt');
          break;

        case 'popularity':
          // 人气票：方向引导（简化处理）
          addToTtsQueue('感谢' + user + '的人气票，提示：想想故事的关键人物是谁？', 'urgent');
          break;
      }
    },
    [
      currentSoup,
      likeProgress,
      likeThreshold,
      charStates,
      addGiftRecord,
      updateLikeProgress,
      revealChar,
      revealAllChars,
      addToTtsQueue,
    ]
  );

  // 处理WebSocket消息
  const handleMessage = useCallback(
    (message: WsMessage) => {
      switch (message.type) {
        case 'danmu':
          if (message.data.user && message.data.content) {
            handleBarrage(message.data.user, message.data.content);
          }
          break;
        case 'gift':
          if (message.data.user && message.data.giftName) {
            handleGift(
              message.data.user,
              message.data.giftName,
              message.data.giftCount || 1
            );
          }
          break;
        case 'like':
          if (message.data.likeCount) {
            updateLikeProgress(message.data.likeCount);
          }
          break;
      }
    },
    [handleBarrage, handleGift, updateLikeProgress]
  );

  // 开始新游戏时 TTS 播报汤面
  useEffect(() => {
    if (phase === 'reading' && currentSoup) {
      console.log(`[Game] 开始新游戏: "${currentSoup.title}"`);
      // TTS 播报汤面
      addToTtsQueue('新题目：' + currentSoup.title + '。' + currentSoup.surface, 'interrupt');
      // 2秒后进入 playing 状态
      const timer = setTimeout(() => {
        setPhase('playing');
        console.log('[Game] 游戏进入进行阶段');
      }, 2000);
      return () => clearTimeout(timer);
    }
  }, [phase, currentSoup, addToTtsQueue, setPhase]);

  // 游戏完成后自动开始下一局（5秒延迟）
  useEffect(() => {
    if (phase === 'completed' && currentSoup) {
      console.log('[Game] 游戏完成，5秒后自动开始下一局');
      addToTtsQueue('谜题已揭晓，答案就是：' + currentSoup.bottom + '。5秒后开始下一题！', 'interrupt');

      const timer = setTimeout(() => {
        console.log('[Game] 自动开始下一局');
        startNewGame();
      }, 5000);

      return () => clearTimeout(timer);
    }
  }, [phase, currentSoup, startNewGame, addToTtsQueue]);

  return {
    phase,
    currentSoup,
    startNewGame,
    handleMessage,
    setPhase,
  };
}
