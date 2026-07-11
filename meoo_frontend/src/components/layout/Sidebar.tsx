import { GiftPanel } from '@/components/game/GiftPanel';
import { LikeProgress } from '@/components/game/LikeProgress';
import { TtsPlayer } from '@/components/game/TtsPlayer';

/**
 * 侧边栏组件
 * 包含礼物面板、点赞进度、TTS控制
 */
export function Sidebar() {
  return (
    <div className="space-y-4">
      <LikeProgress />
      <GiftPanel />
      <TtsPlayer />
    </div>
  );
}
