import { createFileRoute, Link } from '@tanstack/react-router';
import { GlassCard } from '@/components/common/GlassCard';
import { Button } from '@/components/ui/button';
import { ArrowLeft, Save } from 'lucide-react';
import { useState, useEffect } from 'react';

export const Route = createFileRoute('/settings')({
  component: SettingsPage,
});

interface Config {
  wsUrl: string;
  qwenApiUrl: string;
  ttsApiUrl: string;
  likeThreshold: number;
  ttsEnabled: boolean;
}

const STORAGE_KEY = 'gameConfig';

function loadConfig(): Config {
  try {
    const saved = localStorage.getItem(STORAGE_KEY);
    if (saved) {
      return JSON.parse(saved);
    }
  } catch (_) {}
  return {
    wsUrl: 'ws://localhost:9876',
    qwenApiUrl: 'http://localhost:3009',
    ttsApiUrl: 'http://localhost:3006',
    likeThreshold: 500,
    ttsEnabled: true,
  };
}

function SettingsPage() {
  const [wsUrl, setWsUrl] = useState('');
  const [qwenApiUrl, setQwenApiUrl] = useState('');
  const [ttsApiUrl, setTtsApiUrl] = useState('');
  const [likeThreshold, setLikeThreshold] = useState(500);
  const [ttsEnabled, setTtsEnabled] = useState(true);
  const [saved, setSaved] = useState(false);

  // load config on mount
  useEffect(() => {
    const config = loadConfig();
    setWsUrl(config.wsUrl);
    setQwenApiUrl(config.qwenApiUrl);
    setTtsApiUrl(config.ttsApiUrl);
    setLikeThreshold(config.likeThreshold);
    setTtsEnabled(config.ttsEnabled);
  }, []);

  const handleSave = () => {
    const config: Config = {
      wsUrl,
      qwenApiUrl,
      ttsApiUrl,
      likeThreshold,
      ttsEnabled,
    };
    localStorage.setItem(STORAGE_KEY, JSON.stringify(config));
    setSaved(true);
    setTimeout(() => setSaved(false), 2000);
  };

  return (
    <div className="min-h-screen p-6">
      <div className="container mx-auto max-w-2xl">
        {/* back button */}
        <Link to="/">
          <Button variant="ghost" className="mb-6">
            <ArrowLeft className="w-4 h-4 mr-2" />
            返回游戏
          </Button>
        </Link>

        <h1 className="text-2xl font-bold text-foreground mb-6">游戏设置</h1>

        <div className="space-y-6">
          {/* connection settings */}
          <GlassCard className="p-6" variant="default">
            <h2 className="text-lg font-semibold text-foreground mb-4">连接设置</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-muted-foreground mb-2">WebSocket 地址</label>
                <input
                  type="text"
                  value={wsUrl}
                  onChange={(e) => setWsUrl(e.target.value)}
                  placeholder="ws://localhost:9876"
                  className="w-full px-4 py-2 rounded-lg bg-input border border-border text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <p className="text-xs text-muted-foreground mt-1">直播弹幕服务器 WebSocket 地址</p>
              </div>

              <div>
                <label className="block text-sm text-muted-foreground mb-2">LLM API 地址</label>
                <input
                  type="text"
                  value={qwenApiUrl}
                  onChange={(e) => setQwenApiUrl(e.target.value)}
                  placeholder="http://localhost:3009"
                  className="w-full px-4 py-2 rounded-lg bg-input border border-border text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <p className="text-xs text-muted-foreground mt-1">通义大模型 API 服务地址，用于弹幕分类与解答</p>
              </div>

              <div>
                <label className="block text-sm text-muted-foreground mb-2">TTS API 地址</label>
                <input
                  type="text"
                  value={ttsApiUrl}
                  onChange={(e) => setTtsApiUrl(e.target.value)}
                  placeholder="http://localhost:3006"
                  className="w-full px-4 py-2 rounded-lg bg-input border border-border text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <p className="text-xs text-muted-foreground mt-1">语音合成服务地址</p>
              </div>
            </div>
          </GlassCard>

          {/* game settings */}
          <GlassCard className="p-6" variant="default">
            <h2 className="text-lg font-semibold text-foreground mb-4">游戏设置</h2>

            <div className="space-y-4">
              <div>
                <label className="block text-sm text-muted-foreground mb-2">点赞揭示阈值</label>
                <input
                  type="number"
                  value={likeThreshold}
                  onChange={(e) => setLikeThreshold(Number(e.target.value))}
                  min="1"
                  className="w-full px-4 py-2 rounded-lg bg-input border border-border text-foreground focus:outline-none focus:ring-2 focus:ring-primary"
                />
                <p className="text-xs text-muted-foreground mt-1">每累积多少个点赞揭示一个字</p>
              </div>

              <div className="flex items-center justify-between">
                <div>
                  <label className="text-sm text-foreground">启用语音播报</label>
                  <p className="text-xs text-muted-foreground mt-0.5">开启后将自动语音播报游戏内容</p>
                </div>
                <button
                  onClick={() => setTtsEnabled(!ttsEnabled)}
                  className={`
                    relative inline-flex h-6 w-11 items-center rounded-full transition-colors
                    ${ttsEnabled ? 'bg-primary' : 'bg-muted'}
                  `}
                >
                  <span
                    className={`
                      inline-block h-4 w-4 transform rounded-full bg-white transition-transform
                      ${ttsEnabled ? 'translate-x-6' : 'translate-x-1'}
                    `}
                  />
                </button>
              </div>
            </div>
          </GlassCard>

          {/* save button */}
          <Button
            onClick={handleSave}
            className="w-full bg-primary hover:bg-primary/90 text-primary-foreground"
          >
            <Save className="w-4 h-4 mr-2" />
            {saved ? '已保存！' : '保存设置'}
          </Button>
        </div>
      </div>
    </div>
  );
}
