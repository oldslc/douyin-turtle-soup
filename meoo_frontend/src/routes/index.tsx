import { createFileRoute } from '@tanstack/react-router';
import { useCallback, useEffect, useRef } from 'react';
import { Header } from '@/components/layout/Header';
import { SoupDisplay } from '@/components/game/SoupDisplay';
import { ProgressBars } from '@/components/game/ProgressBars';
import { QaBubble } from '@/components/game/QaBubble';
import { GiftPanel } from '@/components/game/GiftPanel';
import { ContributionBoard } from '@/components/game/ContributionBoard';
import { GameControls } from '@/components/game/GameControls';
import { ParticleBg } from '@/components/common/ParticleBg';
import { useGameStore } from '@/stores/gameStore';
import { SOUPS } from '@/data/soups';
import type { BarrageResult, SoupData, CharRevealState } from '@/types';

export const Route = createFileRoute('/')({
  component: GamePage,
});

const WS_URL = 'ws://localhost:3010/ws';
const RECONNECT_INTERVAL = 3000;

function GamePage() {
  const { phase, setPhase, addQaRecord, addToTtsQueue } = useGameStore();
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | undefined>(undefined);

  // WebSocket message handler: backend -> frontend
  const handleWsMessage = useCallback((event: MessageEvent) => {
    try {
      const msg = JSON.parse(event.data);
      const store = useGameStore.getState();

      switch (msg.type) {
        case 'game_start':
          if (msg.surface && msg.charStates) {
            // Map server charStates (isContent) to React format (isContentWord)
            const mappedCS: CharRevealState[] = msg.charStates.map(
              (s: any, i: number) => ({
                char: s.char,
                index: i,
                revealed: s.revealed,
                isContentWord: (s.isContent !== undefined) ? s.isContent : s.isContentWord,
              })
            );
            // Find the matching soup from local DB by surface
            const matchedSoup = SOUPS.find((s) => s.surface === msg.surface);
            if (matchedSoup) {
              store.applyGameStart(matchedSoup, mappedCS);
            } else {
              // Fallback: create a temporary soup object
              const tempSoup: SoupData = {
                id: 'ws-' + Date.now(),
                title: msg.surface?.substring(0, 20) || '???',
                surface: msg.surface || '',
                bottom: '',
                keywords: msg.keywords || [],
                difficulty: 'medium',
              };
              store.applyGameStart(tempSoup, mappedCS);
            }
          }
          break;

        case 'reveal_update':
          if (msg.charStates) {
            // Map server charStates (isContent) to React format (isContentWord)
            const mappedCS = msg.charStates.map((s: any, i: number) => ({
              char: s.char,
              index: i,
              revealed: s.revealed,
              isContentWord: (s.isContent !== undefined) ? s.isContent : s.isContentWord,
            }));
            useGameStore.setState({ charStates: mappedCS });
            const contentWords = mappedCS.filter((s: CharRevealState) => s.isContentWord);
            const revealedCount = contentWords.filter((s: any) => s.revealed).length;
            const totalContentWords = contentWords.length;
            if (totalContentWords > 0 && revealedCount >= totalContentWords) {
              store.setPhase('completed');
            }
          }
          break;

        case 'classification':
          if (msg.text && msg.answerType) {
            const resultMap: Record<string, BarrageResult> = {
              '是': 'yes', '不是': 'no', '是也不是': 'maybe', '不相关': 'irrelevant',
            };
            store.addQaRecord(msg.user || '观众', msg.text, resultMap[msg.answerType] || 'irrelevant');
          }
          break;

        case 'gift_effect':
          if (msg.script) {
            store.addToTtsQueue(msg.script, 'urgent');
          }
          break;

        case 'hint':
          if (msg.hint) {
            store.addQaRecord('系统提示', '💡 ' + msg.hint, 'yes');
            store.addToTtsQueue(msg.script || msg.hint, 'urgent');
          }
          break;

        case 'game_end':
          if (msg.charStates) {
            const mappedCS = msg.charStates.map((s: any, i: number) => ({
              char: s.char,
              index: i,
              revealed: s.revealed,
              isContentWord: (s.isContent !== undefined) ? s.isContent : s.isContentWord,
            }));
            useGameStore.setState({ charStates: mappedCS });
          }
          store.setPhase('completed');
          store.addToTtsQueue('恭喜' + (msg.winner || '观众') + '！谜题已揭开！', 'interrupt');
          break;

        case 'pong':
        case 'state_sync':
          break;

        default:
          console.log('[WS] Unknown:', msg.type);
      }
    } catch (err) {
      console.error('[WS] Error:', err);
    }
  }, []);

  const connectWs = useCallback(() => {
    if (wsRef.current?.readyState === WebSocket.OPEN) return;
    try {
      const ws = new WebSocket(WS_URL);
      wsRef.current = ws;
      ws.onopen = () => console.log('[WS] Connected');
      ws.onmessage = handleWsMessage;
      ws.onclose = () => {
        reconnectTimerRef.current = setTimeout(connectWs, RECONNECT_INTERVAL);
      };
      ws.onerror = () => ws.close();
    } catch (err) {
      reconnectTimerRef.current = setTimeout(connectWs, RECONNECT_INTERVAL);
    }
  }, [handleWsMessage]);

  // Expose sendJsonMessage to GameControls via a window ref
  const sendJsonMessage = useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(data));
    }
  }, []);

  useEffect(() => {
    connectWs();
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      wsRef.current?.close();
    };
  }, [connectWs]);

  const handleSendGift = useCallback((giftName: string) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify({
        type: 'gift',
        giftName: giftName,
        nickname: '我',
      }));
    }
  }, []);

  return (
    <div className="h-screen relative overflow-hidden bg-background flex flex-col">
      <ParticleBg particleCount={30} colors={['#00d4ff', '#7c3aed', '#f59e0b']} speed={0.2} />
      <div className="relative z-10 flex-1 flex flex-col px-4 py-4 max-w-7xl mx-auto w-full">
        <Header />
        <div className="mt-4 shrink-0">
          <GameControls sendJsonMessage={sendJsonMessage} />
        </div>
        <div className="mt-4 flex-1 grid grid-cols-1 lg:grid-cols-3 gap-4 min-h-0">
          <div className="lg:col-span-1 flex flex-col gap-3 min-h-0">
            <div className="shrink-0">
              <GiftPanel onSendGift={handleSendGift} />
            </div>
            <div className="shrink-0">
              <ProgressBars />
            </div>
            <div className="flex-1 min-h-0 overflow-hidden">
              <QaBubble />
            </div>
            <div className="shrink-0">
              <ContributionBoard />
            </div>
          </div>
          <div className="lg:col-span-2 min-h-0 overflow-hidden">
            <SoupDisplay />
          </div>
        </div>
      </div>
    </div>
  );
}
