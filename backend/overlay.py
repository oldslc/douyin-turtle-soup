"""投屏端 — 9:16 抖音竖屏（V8 视觉重构版）

设计参考用户提供的抖音游戏截图：
- 1080×1920 竖屏，中心 1080×1080 安全区
- 顶部状态条（5.5vh） + 汤面（11-15vh） + 谜底揭示（38-55vh） + 进度条（5vh） + 底部互动（14vh）
- 固定大方格字格（80×88px），揭示时蓝绿发光
- 浮层：TTS 字幕条、礼物全屏扇光、答题气泡、段位升级、礼物气泡
"""
import json

OVERLAY_HTML = r"""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0, maximum-scale=1.0, user-scalable=no">
<title>CCcat 海龟汤 · 投屏</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
@import url('https://fonts.googleapis.com/css2?family=Noto+Sans+SC:wght@400;700;900&family=ZCOOL+KuaiLe&display=swap');

:root {
  /* 主题变量由 theme_manager 注入；如未注入则使用默认暗色 */
  --bg: #050714;
  --bg-grad: linear-gradient(180deg, #050714 0%, #0a0f2a 50%, #050714 100%);
  --primary: #00d4ff;
  --purple: #a855f7;
  --gold: #fbbf24;
  --green: #22c55e;
  --red: #ef4444;
  --yellow: #eab308;
  --pink: #f472b6;
  --text: #f1f5f9;
  --text-dim: #94a3b8;
  --text-dimmer: #475569;
  --card: rgba(12,16,38,0.6);
  --card-border: rgba(255,255,255,0.05);
}

html,body{height:100%;width:100%;overflow:hidden;background:var(--bg)}
body{color:var(--text);
  font-family:'Noto Sans SC','PingFang SC','Microsoft YaHei',sans-serif;
  background:var(--bg-grad);position:relative;user-select:none;-webkit-user-select:none}

/* ── 粒子背景 ── */
#particles{position:fixed;inset:0;pointer-events:none;z-index:0;opacity:0.4}
.star{position:absolute;width:2px;height:2px;background:#fff;border-radius:50%;box-shadow:0 0 6px #fff;animation:twinkle 3s ease-in-out infinite}
@keyframes twinkle{0%,100%{opacity:0.2;transform:scale(0.5)}50%{opacity:1;transform:scale(1.2)}}

/* ══════════════════════════════════════
   主布局: 1080×1920 竖屏
   顶部状态 5.5vh + 汤面 13vh + 谜底 50vh + 进度 5vh + 底部 14vh = 87.5vh
   留 12.5vh 给底部互动栏
   ══════════════════════════════════════ */
.app{position:relative;z-index:1;width:100vw;height:100vh;
  display:flex;flex-direction:column;padding:3vh 3vw 0;gap:1.2vh}

/* ── 顶部状态条 (5.5vh) ── */
.top-bar{flex-shrink:0;height:5.5vh;min-height:42px;
  display:flex;align-items:center;justify-content:space-between;
  padding:0 3vw;border-radius:12px;overflow:hidden;
  background:linear-gradient(90deg,rgba(12,16,38,0.95),rgba(20,12,40,0.95));
  border:1px solid rgba(0,212,255,0.25);
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
  box-shadow:0 2px 12px rgba(0,0,0,0.3)}
.brand{display:flex;align-items:center;gap:2vw}
.logo{width:3.2vh;height:3.2vh;min-width:26px;min-height:26px;border-radius:8px;
  background:linear-gradient(135deg,var(--primary),var(--purple));
  display:flex;align-items:center;justify-content:center;font-size:1.8vh;flex-shrink:0;
  box-shadow:0 0 14px rgba(0,212,255,0.5);
  animation:logo-pulse 2.5s ease-in-out infinite}
@keyframes logo-pulse{0%,100%{box-shadow:0 0 14px rgba(0,212,255,0.5)}50%{box-shadow:0 0 24px rgba(0,212,255,0.8)}}
.brand-text{display:flex;flex-direction:column;line-height:1.1}
.brand-title{font-size:1.4vh;font-weight:900;background:linear-gradient(90deg,#fff,#94a3b8);-webkit-background-clip:text;-webkit-text-fill-color:transparent}
.brand-sub{font-size:0.9vh;color:var(--text-dim);letter-spacing:1.5px}

.status-pills{display:flex;align-items:center;gap:1.2vw;margin-right:0.8vw}
.pill{padding:0.4vh 1.6vw;border-radius:99px;font-size:1.05vh;font-weight:700;
  background:rgba(255,255,255,0.06);color:var(--text-dim)}
.pill.diff{background:rgba(168,85,247,0.25);color:var(--purple);box-shadow:0 0 10px rgba(168,85,247,0.3);font-weight:900;font-size:1.15vh}
@keyframes pulse{0%,100%{opacity:1}50%{opacity:0.6}}

/* ── 点赞进度条 (品牌和难度之间的独立行) ── */
.like-progress{width:100%;display:flex;flex-direction:column;gap:4px;flex:1;margin:0 4.5vw 0 0;min-width:0}
.like-progress-row{display:flex;align-items:center;gap:8px}
.progress-track{flex:1;height:6px;background:rgba(100,116,139,0.3);border-radius:3px;position:relative;overflow:hidden}
.like-fill{height:100%;border-radius:3px;width:0%;background:linear-gradient(90deg,#22c55e,#fbbf24);transition:width 0.3s ease}
.progress-markers{position:absolute;inset:0;pointer-events:none}
.progress-markers .marker{position:absolute;top:-3px;width:2px;height:12px;background:var(--primary);transform:translateX(-50%);border-radius:1px}
.progress-markers .marker.reached{background:var(--gold);box-shadow:0 0 6px var(--gold)}
.progress-label{font-size:1.15vh;color:var(--gold);white-space:nowrap;min-width:3.5vw;text-align:right;font-weight:900}
.like-icon{font-size:1.8vh;flex-shrink:0;line-height:1}
.threshold-row{display:flex;align-items:center;width:100%}
/* 阈值效果标签（在进度条下方） */
.like-thresholds{flex:1;display:flex;position:relative;height:2vh;margin-left:6px;padding:2px 2vw 0 0}
.like-thresholds .tl{position:absolute;font-size:1.05vh;color:var(--text-dimmer);transform:translateX(-50%);white-space:nowrap;line-height:1.3;transition:color 0.3s,font-weight 0.3s;letter-spacing:0.5px}
.tl-label{font-size:0.95vh;color:var(--text-dimmer);white-space:nowrap;flex-shrink:0;letter-spacing:0.3px}
.like-thresholds .tl.reached{color:var(--gold);font-weight:800;text-shadow:0 0 8px rgba(251,191,36,0.3)}
.like-thresholds .tl.active{color:var(--primary);font-weight:800;text-shadow:0 0 10px rgba(0,212,255,0.5)}

/* ── 汤面区 (11vh，自适应字号) ── */
.surface-area{flex-shrink:0;height:11vh;min-height:11vh;max-height:11vh;
  padding:1.0vh 3.5vw;border-radius:14px;
  background:linear-gradient(135deg,rgba(0,212,255,0.06),rgba(168,85,247,0.06));
  border:1px solid rgba(0,212,255,0.2);
  backdrop-filter:blur(12px);-webkit-backdrop-filter:blur(12px);
  display:flex;flex-direction:column;justify-content:center;
  position:relative;overflow:hidden;box-shadow:0 4px 16px rgba(0,0,0,0.2)}
.surface-area::before{content:'';position:absolute;left:0;top:0;bottom:0;width:4px;
  background:linear-gradient(180deg,var(--primary),var(--purple));
  box-shadow:0 0 10px var(--primary)}
.surface-label{font-size:1.0vh;color:var(--primary);letter-spacing:3px;margin-bottom:0.4vh;
  display:flex;align-items:center;gap:6px;font-weight:700}
.surface-label::before{content:'✦';color:var(--gold);font-size:1.4vh}
.surface-text{line-height:1.35;color:var(--text);font-weight:500;
  display:block;overflow:visible;
  font-family:'ZCOOL KuaiLe','Noto Sans SC',serif;
  text-shadow:0 1px 3px rgba(0,0,0,0.5);
  word-break:break-word;
  overflow-wrap:break-word;
  white-space:normal;
  width:100%;
  /* 字号由 JS 动态调整以铺满 */
  font-size:2vh}

/* ── 谜底揭示区 (核心, 缩小约 1/3) ── */
.reveal-area{flex:1;min-height:0;
  border-radius:16px;
  background:linear-gradient(135deg,rgba(0,212,255,0.04),rgba(168,85,247,0.04));
  border:1px solid rgba(0,212,255,0.15);
  position:relative;overflow:hidden;
  display:flex;flex-direction:column;
  box-shadow:0 0 30px rgba(0,212,255,0.05),inset 0 0 60px rgba(168,85,247,0.05)}
.reveal-area::before{content:'';position:absolute;inset:0;
  background:radial-gradient(circle at 50% 50%,rgba(0,212,255,0.08),transparent 60%);
  pointer-events:none;animation:reveal-glow 4s ease-in-out infinite}
@keyframes reveal-glow{0%,100%{opacity:0.6}50%{opacity:1}}

.reveal-header{flex-shrink:0;padding:1.0vh 2.5vw;
  display:flex;align-items:center;justify-content:space-between;
  border-bottom:1px solid rgba(255,255,255,0.05);
  position:relative;z-index:2}
.reveal-title{font-size:1.3vh;color:var(--primary);letter-spacing:3px;font-weight:700}
.reveal-title::before{content:'🔮 '}
.reveal-stats{display:flex;gap:2.5vw;font-size:1.3vh;color:var(--text-dim)}
.reveal-stats .val{color:var(--primary);font-weight:700;margin-left:0.4vw;font-size:1.5vh}

.reveal-scroll{flex:1;overflow-y:hidden;padding:1.2vh 2vw 0.8vh;
  display:flex;flex-wrap:wrap;align-content:flex-start;gap:0.4vw;
  justify-content:center;align-items:flex-start;
  position:relative;z-index:2;--cb-font-size:min(3.8vh,4.2vw);--cb-w:5.2vw;--cb-h:5.5vh}

/* ── 字格 (核心视觉, 固定大方格) ── */
.char-box{width:var(--cb-w);height:var(--cb-h);
  display:flex;align-items:center;justify-content:center;overflow:hidden;
  font-size:var(--cb-font-size);font-weight:900;border-radius:8px;transition:all 0.4s;
  position:relative;font-family:'ZCOOL KuaiLe',serif}
.char-box.revealed{color:var(--primary);
  text-shadow:0 0 16px rgba(0,212,255,0.6),0 0 4px #fff;
  animation:reveal-pop 0.5s cubic-bezier(0.34,1.56,0.64,1)}
.char-box.hidden{color:transparent;
  background:linear-gradient(135deg,rgba(100,116,139,0.28),rgba(100,116,139,0.18));
  border:1px solid rgba(100,116,139,0.25);
  border-radius:5px;min-width:2.5vw;
  box-shadow:inset 0 1px 2px rgba(0,0,0,0.3)}
.char-box.hidden::after{content:'';position:absolute;width:75%;height:3px;
  background:rgba(148,163,184,0.55);border-radius:2px}
.char-box.function-word{color:var(--text-dimmer);font-size:calc(var(--cb-font-size)*0.55);font-weight:400;opacity:0.7}
.char-box.punct{color:var(--text-dimmer);width:2.5vw;font-size:calc(var(--cb-font-size)*0.65)}
.char-box.highlight{color:var(--gold);
  text-shadow:0 0 24px rgba(251,191,36,0.9),0 0 6px #fff;
  animation:highlight-pulse 1.2s ease-out;
  transform:scale(1.1)}
@keyframes reveal-pop{0%{transform:scale(0) rotate(180deg);opacity:0}
  60%{transform:scale(1.35) rotate(-10deg)}
  100%{transform:scale(1) rotate(0);opacity:1}}
@keyframes highlight-pulse{0%{transform:scale(1)}
  30%{transform:scale(1.5);color:#fff;text-shadow:0 0 36px #fff}
  100%{transform:scale(1.1)}}

/* ── 底部行 (进度条 + 礼物栏) ── */
.bottom-row{flex-shrink:0;display:flex;gap:1.2vw;margin-bottom:0.8vh}

/* ── 进度条 (底部行·左) ── */
.progress-area{flex:0 0 32%;padding:1.0vh 2vw;
  border-radius:12px;
  background:linear-gradient(90deg,rgba(12,16,38,0.95),rgba(20,12,40,0.95));
  border:1px solid rgba(0,212,255,0.2);
  backdrop-filter:blur(12px);
  box-shadow:0 2px 12px rgba(0,0,0,0.3);
  display:flex;flex-direction:column;justify-content:center}
.progress-row{display:flex;justify-content:space-between;align-items:center;
  font-size:1.1vh;color:var(--text-dim);margin-bottom:0.4vh}
.progress-row .pct{color:var(--primary);font-weight:900;font-size:1.3vh;text-shadow:0 0 10px rgba(0,212,255,0.5)}
.progress-bar{height:0.9vh;background:rgba(100,116,139,0.2);
  border-radius:99px;overflow:hidden;position:relative;
  box-shadow:inset 0 1px 2px rgba(0,0,0,0.3)}
.progress-fill{height:100%;border-radius:99px;
  background:linear-gradient(90deg,var(--primary),var(--purple));
  transition:width 0.6s cubic-bezier(0.4,0,0.2,1);
  position:relative;overflow:hidden;
  box-shadow:0 0 10px rgba(0,212,255,0.5)}
.progress-fill::after{content:'';position:absolute;inset:0;
  background:linear-gradient(90deg,transparent,rgba(255,255,255,0.4),transparent);
  animation:shimmer 2s linear infinite}
@keyframes shimmer{0%{transform:translateX(-100%)}100%{transform:translateX(100%)}}
.progress-fill.warning{background:linear-gradient(90deg,var(--yellow),var(--primary))}
.progress-fill.danger{background:linear-gradient(90deg,var(--red),var(--yellow));animation:danger-pulse 0.8s ease-in-out infinite}
@keyframes danger-pulse{0%,100%{opacity:1}50%{opacity:0.7}}

/* ── 礼物栏 (底部行·右) ── */
.gift-list-area{flex:1;border-radius:12px;
  background:linear-gradient(90deg,rgba(12,16,38,0.95),rgba(20,12,40,0.95));
  border:1px solid rgba(0,212,255,0.2);
  backdrop-filter:blur(12px);
  padding:0.6vh 1.2vw;display:flex;align-items:center;gap:0.6vw;
  overflow:hidden;box-shadow:0 2px 12px rgba(0,0,0,0.3)}
.gift-list-title{display:none}
.gift-list{display:flex;gap:0.3vw;flex:1;align-items:stretch}
.gift-list::-webkit-scrollbar{display:none}
.gift-item{display:flex;flex-direction:column;align-items:center;justify-content:center;gap:0.2vw;
  flex:1;min-width:0;padding:0.5vh 0.4vw;
  border-radius:8px;background:rgba(0,212,255,0.06);
  border:1px solid rgba(0,212,255,0.12);
  transition:all 0.2s}
.gift-item:hover{background:rgba(0,212,255,0.15);transform:translateY(-1px)}
.gift-item .gi-icon{font-size:2.2vh;line-height:1;flex-shrink:0;filter:drop-shadow(0 0 4px rgba(0,212,255,0.4));display:flex;align-items:center;justify-content:center}
.gift-item .gi-icon img{width:2.8vh;height:2.8vh;object-fit:contain;max-width:100%;max-height:100%;filter:drop-shadow(0 0 3px rgba(0,212,255,0.5))}
.gift-item .gi-name{font-size:1.1vh;color:var(--text);font-weight:900;white-space:nowrap;line-height:1}
.gift-item .gi-func{font-size:0.95vh;color:var(--gold);white-space:nowrap;overflow:hidden;text-overflow:ellipsis;max-width:11vw;line-height:1;font-weight:600}

/* ── 底部互动区 (flex 撑满剩余空间) ── */
.bottom-area{flex:1;min-height:8vh;
  display:flex;gap:2vw;margin-bottom:1vh}

.danmaku-panel{flex:3;border-radius:14px;
  background:var(--card);border:1px solid var(--card-border);
  backdrop-filter:blur(12px);
  display:flex;flex-direction:column;overflow:hidden}
.danmaku-header{flex-shrink:0;padding:1vh 2vw;
  display:flex;align-items:center;justify-content:space-between;
  border-bottom:1px solid rgba(255,255,255,0.05)}
.danmaku-label{font-size:1.2vh;color:var(--text-dim);letter-spacing:2px}
.danmaku-count{font-size:1.1vh;color:var(--primary);font-weight:700}
.danmaku-scroll{flex:1;overflow-y:auto;padding:0.8vh 1.5vw;
  display:flex;flex-direction:column;gap:0.5vh;
  scrollbar-width:thin}
.danmaku-scroll::-webkit-scrollbar{width:2px}
.danmaku-scroll::-webkit-scrollbar-thumb{background:rgba(0,212,255,0.2);border-radius:2px}
.danmaku-item{display:flex;align-items:flex-start;gap:1.2vw;
  font-size:1.5vh;line-height:1.3;
  padding:0.3vh 0.5vw;
  animation:dm-in 0.3s ease-out;
  flex-shrink:0}
@keyframes dm-in{from{opacity:0;transform:translateX(-8px)}to{opacity:1;transform:translateX(0)}}
.dm-user{font-weight:700;color:var(--gold);
  white-space:nowrap;flex-shrink:0;
  max-width:18vw;overflow:hidden;text-overflow:ellipsis}
.dm-text{flex:1;color:var(--text);word-break:break-word;line-height:1.4}
.dm-tag{font-size:1.1vh;padding:0.2vh 1.2vw;border-radius:6px;
  white-space:nowrap;font-weight:700;flex-shrink:0}
.dm-tag.yes{background:rgba(34,197,94,0.25);color:var(--green)}
.dm-tag.no{background:rgba(239,68,68,0.25);color:var(--red)}
.dm-tag.maybe{background:rgba(234,179,8,0.25);color:var(--yellow)}
.dm-tag.hint{background:rgba(0,212,255,0.25);color:var(--primary);font-weight:900}

.info-panel{flex:2;border-radius:14px;
  background:var(--card);border:1px solid var(--card-border);
  backdrop-filter:blur(12px);
  display:flex;flex-direction:column;padding:1vh 2vw;
  min-width:0;overflow:hidden}
.info-title{font-size:1.2vh;color:var(--text-dim);letter-spacing:2px;
  margin-bottom:0.6vh;flex-shrink:0}
.tier-list{flex:1;overflow-y:auto;margin-top:0.5vh;
  display:flex;flex-direction:column;gap:0.3vh;min-height:0}
/* 排行榜前3 — 领奖台布局 213 */
.tier-top3{flex-shrink:0;display:flex;flex-direction:row;align-items:flex-end;justify-content:center;
  gap:0.6vw;padding:0.6vh 0.6vw;margin:0 -0.6vw 0.4vh;
  min-height:10vh}
.podium-item{display:flex;flex-direction:column;align-items:center;gap:0.2vh;
  border-radius:10px;padding:0.4vh 0.6vw;flex:1;
  transition:all 0.2s;
  position:relative}
.podium-item .rank-icon{font-size:3vh;line-height:1}
.podium-item .name{font-size:1.5vh;font-weight:700;color:var(--text);overflow:hidden;text-overflow:ellipsis;white-space:nowrap;max-width:100%}
.podium-item .tier-badge{font-size:0.9vh;padding:0.1vh 0.4vw;border-radius:4px;background:rgba(0,212,255,0.15);color:var(--primary)}
.podium-item .score{font-size:1.1vh;color:var(--gold);font-weight:700}
.podium-item .podium-stand{width:80%;height:1.2vh;border-radius:4px 4px 0 0;margin-top:0.2vh;flex-shrink:0}
.podium-item.podium-1{flex:1.4;background:linear-gradient(180deg,rgba(251,191,36,0.2),rgba(251,191,36,0.05));
  border:1px solid rgba(251,191,36,0.3);padding-top:1.2vh}
.podium-item.podium-1 .rank-icon{font-size:3.6vh}
.podium-item.podium-1 .name{font-size:2.0vh}
.podium-item.podium-1 .podium-stand{height:2.2vh;background:linear-gradient(180deg,#fbbf24,#b8860b);box-shadow:0 -2px 10px rgba(251,191,36,0.4)}
.podium-item.podium-2{flex:0.8;align-self:flex-end;background:linear-gradient(180deg,rgba(192,192,192,0.15),rgba(0,212,255,0.04));
  border:1px solid rgba(192,192,192,0.2);padding-bottom:0.8vh}
.podium-item.podium-2 .name{font-size:1.3vh}
.podium-item.podium-2 .podium-stand{height:1.6vh;background:linear-gradient(180deg,#c0c0c0,#808080);box-shadow:0 -2px 10px rgba(192,192,192,0.3)}
.podium-item.podium-3{flex:0.8;align-self:flex-end;background:linear-gradient(180deg,rgba(205,127,50,0.15),rgba(168,85,247,0.04));
  border:1px solid rgba(205,127,50,0.2);padding-bottom:0.4vh}
.podium-item.podium-3 .name{font-size:1.3vh}
.podium-item.podium-3 .podium-stand{height:1.0vh;background:linear-gradient(180deg,#cd7f32,#8b5a2b);box-shadow:0 -2px 10px rgba(205,127,50,0.3)}
/* 排行榜第 4+ 可滚动 */
.tier-rest{flex:1;overflow-y:auto;display:grid;grid-template-columns:1fr 1fr;gap:0.3vh 1.5vw;align-content:start;
  scrollbar-width:thin}
.tier-rest::-webkit-scrollbar{width:2px}
.tier-rest::-webkit-scrollbar-thumb{background:rgba(0,212,255,0.2);border-radius:2px}
.tier-item{display:flex;justify-content:space-between;align-items:center;
  font-size:1.3vh;padding:0.2vh 0}
.tier-item .rank-num{color:var(--text-dim);width:2vw;font-weight:900;font-size:1.2vh}
.tier-item .rank-num.top{color:var(--gold)}
.tier-item .name{flex:1;color:var(--text);font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}
.tier-item .tier-badge{font-size:1vh;padding:0.1vh 0.8vw;border-radius:4px;
  background:rgba(0,212,255,0.15);color:var(--primary)}
.tier-item .score{color:var(--gold);font-weight:700;font-size:1.2vh;margin-left:1vw}

/* ══════════════════════════════════════
   浮层动画
   ══════════════════════════════════════ */

/* ── 礼物飞屏动画 (参考截图中央大礼物) ── */
.gift-fly{position:fixed;left:50%;top:35%;transform:translateX(-50%);
  z-index:90;pointer-events:none;text-align:center;
  animation:gift-fly-in 4s cubic-bezier(0.34,1.56,0.64,1) forwards}
.gift-fly .icon-wrap{width:20vh;height:20vh;min-width:120px;min-height:120px;
  margin:0 auto 1vh;
  background:radial-gradient(circle,rgba(251,191,36,0.4),transparent 70%);
  border-radius:50%;
  display:flex;align-items:center;justify-content:center;
  position:relative}
.gift-fly .icon{font-size:12vh;filter:drop-shadow(0 0 20px rgba(251,191,36,0.8));
  animation:icon-bounce 1s ease-in-out infinite}
.gift-fly .name{font-size:3vh;font-weight:900;color:var(--gold);text-shadow:0 0 16px rgba(251,191,36,0.5);margin-bottom:0.5vh}
.gift-fly .user{font-size:2.2vh;color:var(--text);font-weight:700}
.gift-fly .combo{font-size:2vh;color:var(--pink);font-weight:900;margin-top:0.5vh}
@keyframes gift-fly-in{
  0%{opacity:0;transform:translateX(-50%) scale(0.3) translateY(50px)}
  20%{opacity:1;transform:translateX(-50%) scale(1) translateY(0)}
  80%{opacity:1;transform:translateX(-50%) scale(1) translateY(0)}
  100%{opacity:0;transform:translateX(-50%) scale(0.8) translateY(-30vh)}}
@keyframes icon-bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-10px)}}

/* ── 礼物气泡 (右上方, 小礼物) ── */
.gift-scroll{position:fixed;right:2vw;top:8vh;
  z-index:80;pointer-events:none;
  display:flex;flex-direction:column-reverse;gap:1vh;
  max-height:60vh;overflow:hidden}
.gift-bubble{display:flex;align-items:center;gap:1.5vw;
  background:linear-gradient(90deg,rgba(251,191,36,0.2),rgba(168,85,247,0.2));
  border:1px solid rgba(251,191,36,0.4);
  border-radius:99px;padding:0.8vh 2.5vw;
  animation:bubble-in 3s ease-out forwards;
  backdrop-filter:blur(8px);
  max-width:50vw}
.gift-bubble .icon{font-size:2.5vh;flex-shrink:0}
.gift-bubble .text{font-size:1.5vh;color:var(--text);white-space:nowrap;font-weight:600}
.gift-bubble .text b{color:var(--gold)}
@keyframes bubble-in{
  0%{opacity:0;transform:translateX(100px) scale(0.5)}
  15%{opacity:1;transform:translateX(0) scale(1)}
  85%{opacity:1;transform:translateX(0) scale(1)}
  100%{opacity:0;transform:translateX(50px) scale(0.9)}}

/* ── 答题气泡 (左侧) ── */
.answer-bubbles{position:fixed;left:2vw;top:25vh;bottom:30vh;
  z-index:70;pointer-events:none;
  display:flex;flex-direction:column-reverse;gap:1vh;
  max-width:60vw}
.answer-bubble{display:inline-flex;align-items:center;gap:1.5vw;
  background:rgba(12,16,38,0.85);
  border:1px solid rgba(0,212,255,0.3);
  border-radius:0 18px 18px 18px;
  padding:0.8vh 2.5vw;
  animation:bubble-pop 3s ease-out forwards;
  backdrop-filter:blur(8px);
  max-width:60vw;align-self:flex-start}
.answer-bubble .name{font-size:1.5vh;color:var(--gold);font-weight:700;white-space:nowrap}
.answer-bubble .ans{font-size:1.7vh;font-weight:900}
.answer-bubble.yes .ans{color:var(--green)}
.answer-bubble.no .ans{color:var(--red)}
.answer-bubble.maybe .ans{color:var(--yellow)}
@keyframes bubble-pop{
  0%{opacity:0;transform:translateX(-30px) scale(0.5)}
  10%{opacity:1;transform:translateX(0) scale(1)}
  85%{opacity:1}
  100%{opacity:0;transform:translateX(-20px) scale(0.95)}}

/* ── TTS 字幕条 (底部悬浮, 独立于 toast) ── */
.tts-bar{position:fixed;left:50%;bottom:14vh;transform:translateX(-50%);
  z-index:95;background:linear-gradient(90deg,rgba(0,0,0,0.85),rgba(12,16,38,0.85));
  border:1px solid rgba(0,212,255,0.4);
  border-radius:99px;
  padding:1.2vh 4vw;max-width:80vw;
  text-align:center;display:none;
  animation:tts-in 0.3s ease-out;
  box-shadow:0 4px 20px rgba(0,0,0,0.5)}
.tts-bar.active{display:flex;align-items:center;gap:1.5vw}
.tts-bar .icon{font-size:2vh;color:var(--primary);
  animation:tts-pulse 1s ease-in-out infinite;flex-shrink:0}
.tts-bar .text{font-size:1.8vh;color:var(--text);font-weight:600;line-height:1.3}
@keyframes tts-in{from{opacity:0;transform:translateX(-50%) translateY(20px)}to{opacity:1;transform:translateX(-50%) translateY(0)}}
@keyframes tts-pulse{0%,100%{transform:scale(1)}50%{transform:scale(1.2)}}

/* ── 段位升级动画 (全屏) ── */
.tier-up{position:fixed;inset:0;z-index:200;
  display:flex;flex-direction:column;align-items:center;justify-content:center;
  background:radial-gradient(circle,rgba(0,0,0,0.85),rgba(0,0,0,0.95));
  animation:tier-flash 3.5s ease-out forwards;
  pointer-events:none}
.tier-up .icon{font-size:18vh;animation:icon-rotate 1s ease-in-out;filter:drop-shadow(0 0 40px var(--gold))}
.tier-up .tier-name{font-size:8vh;font-weight:900;
  background:linear-gradient(135deg,var(--gold),var(--primary),var(--purple));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent;
  margin:1vh 0;
  text-shadow:0 0 30px rgba(251,191,36,0.5);
  letter-spacing:4px}
.tier-up .user{font-size:3vh;color:var(--text);font-weight:700}
.tier-up .user b{color:var(--gold)}
.tier-up .from-to{font-size:1.8vh;color:var(--text-dim);margin-top:0.5vh}
@keyframes tier-flash{0%{opacity:0}10%{opacity:1}85%{opacity:1}100%{opacity:0}}
@keyframes icon-rotate{0%{transform:scale(0) rotate(0)}50%{transform:scale(1.3) rotate(180deg)}100%{transform:scale(1) rotate(360deg)}}

/* ── 通关结算 ── */
.settlement{position:fixed;bottom:14vh;left:4vw;right:4vw;z-index:150;
  background:linear-gradient(180deg,rgba(251,191,36,0.15),rgba(168,85,247,0.15));
  border:1px solid rgba(251,191,36,0.4);
  border-radius:16px;padding:2vh 4vw;text-align:center;
  animation:settle-up 0.5s ease-out;backdrop-filter:blur(16px)}
.settlement .big{font-size:3.6vh;font-weight:900;color:var(--gold);margin-bottom:0.8vh;letter-spacing:2px}
.settlement .detail{font-size:1.8vh;color:var(--text);line-height:1.5}
.settlement .detail b{color:var(--gold)}
@keyframes settle-up{from{opacity:0;transform:translateY(100px)}to{opacity:1;transform:translateY(0)}}

/* ── 提示横幅 (中下) ── */
.hint-banner{position:fixed;left:50%;bottom:32vh;transform:translateX(-50%);
  z-index:85;pointer-events:none;
  background:linear-gradient(90deg,rgba(0,212,255,0.2),rgba(168,85,247,0.2));
  border:1px solid rgba(0,212,255,0.4);
  border-radius:14px;padding:1.5vh 4vw;
  max-width:80vw;text-align:center;
  animation:hint-bounce 0.5s ease-out;
  backdrop-filter:blur(12px)}
.hint-banner .label{font-size:1.2vh;color:var(--primary);letter-spacing:3px;margin-bottom:0.3vh}
.hint-banner .text{font-size:2vh;color:var(--text);font-weight:700;line-height:1.4}
.hint-banner.disappear{animation:hint-out 0.5s ease-in forwards}
@keyframes hint-bounce{0%{opacity:0;transform:translateX(-50%) scale(0.5)}60%{transform:translateX(-50%) scale(1.05)}100%{transform:translateX(-50%) scale(1)}}
@keyframes hint-out{to{opacity:0;transform:translateX(-50%) translateY(-20px)}}

/* ── 全屏礼物特效 (扇光+中央大图) ── */
.gift-fullscreen{position:fixed;inset:0;z-index:180;pointer-events:none;
  display:flex;align-items:center;justify-content:center;
  animation:fullscreen-flash 2.5s ease-out forwards}
.gift-fullscreen .rays{position:absolute;inset:0;
  background:conic-gradient(from 0deg,transparent,rgba(251,191,36,0.2),transparent,rgba(168,85,247,0.2),transparent,rgba(0,212,255,0.2),transparent);
  animation:rays-spin 3s linear infinite}
@keyframes rays-spin{from{transform:rotate(0)}to{transform:rotate(360deg)}}
.gift-fullscreen .center{position:relative;text-align:center;animation:center-zoom 2.5s ease-out}
.gift-fullscreen .icon{font-size:30vh;filter:drop-shadow(0 0 40px var(--gold))}
.gift-fullscreen .name{font-size:6vh;font-weight:900;color:var(--gold);text-shadow:0 0 30px var(--gold);margin-top:1vh}
.gift-fullscreen .user{font-size:3vh;color:var(--text);margin-top:0.5vh;font-weight:700}
@keyframes fullscreen-flash{0%{opacity:0}15%{opacity:1}85%{opacity:1}100%{opacity:0}}
@keyframes center-zoom{0%{transform:scale(0)}60%{transform:scale(1.2)}100%{transform:scale(1)}}

/* ── 等待覆盖层 ── */
.waiting-overlay{position:fixed;inset:0;z-index:100;display:flex;align-items:center;justify-content:center;
  background:var(--bg-grad);flex-direction:column;gap:1.5vh}
.waiting-content{text-align:center;display:flex;flex-direction:column;align-items:center;gap:1.2vh}
.waiting-logo{font-size:10vh;animation:waiting-bounce 2s ease-in-out infinite}
@keyframes waiting-bounce{0%,100%{transform:translateY(0)}50%{transform:translateY(-1.5vh)}}
.waiting-title{font-size:4vh;font-weight:900;background:linear-gradient(90deg,var(--primary),var(--purple));
  -webkit-background-clip:text;-webkit-text-fill-color:transparent}
.waiting-sub{font-size:2vh;color:var(--text-dim);letter-spacing:3px}
.waiting-dots{display:flex;gap:1.2vw;margin-top:1vh}
.waiting-dots span{width:1.2vh;height:1.2vh;border-radius:50%;background:var(--primary);
  animation:waiting-dot 1.4s ease-in-out infinite}
.waiting-dots span:nth-child(2){animation-delay:0.2s}
.waiting-dots span:nth-child(3){animation-delay:0.4s}
@keyframes waiting-dot{0%,80%,100%{opacity:0.2;transform:scale(0.6)}40%{opacity:1;transform:scale(1)}}
/* 默认显示等待覆盖层，进入游戏后隐藏 */
body.playing-mode .waiting-overlay{display:none !important}
body:not(.playing-mode) .reveal-area,body:not(.playing-mode) .surface-area,
body:not(.playing-mode) .bottom-row,body:not(.playing-mode) .bottom-area .danmaku-panel,
body:not(.playing-mode) .answer-bubbles{display:none!important}

/* ── 入场动画 ── */
.fade-in{animation:fade-in 0.4s ease-out}
@keyframes fade-in{from{opacity:0;transform:translateY(10px)}to{opacity:1;transform:translateY(0)}}

/* ── 响应式: 适配更窄屏幕 ── */
@media (max-aspect-ratio: 9/16) {
  .reveal-scroll{--cb-font-size:min(4.5vh,5vw);--cb-w:6vw;--cb-h:6.5vh}
  .surface-text{font-size:2.4vh}
  /* 礼物栏: 缩小尺寸适配窄屏 */
  .bottom-row{gap:0.8vw}
  .gift-list-area{padding:0.3vh 0.8vw;gap:0.3vw}
  .gift-item{padding:0.3vh 0.5vw}
  .gift-item .gi-icon{font-size:1.6vh}
  .gift-item .gi-icon img{width:2vh;height:2vh}
  .gift-item .gi-name{font-size:0.85vh}
  .gift-item .gi-func{font-size:0.75vh;max-width:8vw}
  /* 排行榜自适应缩紧 */
  .tier-top3{min-height:7vh;gap:0.4vw;padding:0.4vh 0.4vw}
  .podium-item{padding:0.3vh 0.4vw;gap:0.1vh}
  .podium-item .rank-icon{font-size:2.2vh}
  .podium-item.podium-1 .rank-icon{font-size:2.8vh}
  .podium-item .name{font-size:1.2vh}
  .podium-item.podium-1 .name{font-size:1.6vh}
  .podium-item.podium-2 .name,.podium-item.podium-3 .name{font-size:1.0vh}
  .podium-item .score{font-size:0.9vh}
  .podium-item .podium-stand{height:0.8vh}
  .podium-item.podium-1 .podium-stand{height:1.5vh}
  .podium-item.podium-2 .podium-stand{height:1.0vh}
  .podium-item.podium-3 .podium-stand{height:0.7vh}
  /* 底部互动区缩紧 */
  .bottom-area{min-height:8vh;gap:1.2vw}
  .info-panel{padding:0.6vh 1.2vw}
  .tier-item{font-size:1.0vh;padding:0.15vh 0}
  .tier-item .rank-num{font-size:0.9vh;width:1.5vw}
  .tier-item .score{font-size:0.9vh}
  .tier-item .tier-badge{font-size:0.75vh;padding:0.05vh 0.4vw}
  .danmaku-item{font-size:1.2vh;padding:0.2vh 0.4vw;gap:0.8vw}
  .dm-user{max-width:12vw;font-size:1.1vh}
  .dm-tag{font-size:0.85vh;padding:0.1vh 0.6vw}
}
@media (max-aspect-ratio: 3/5) {
  .gift-item .gi-name{font-size:0.65vh}
  .gift-item .gi-func{font-size:0.65vh;max-width:6vw}
  .gift-item{padding:0.15vh 0.2vw}
  .gift-list{gap:0.15vw}
  .gift-item .gi-icon{font-size:1.2vh}
  .gift-item .gi-icon img{width:1.4vh;height:1.4vh}
  .podium-item .rank-icon{font-size:1.6vh}
  .podium-item.podium-1 .rank-icon{font-size:2.0vh}
  .podium-item .name{font-size:0.9vh}
  .podium-item.podium-1 .name{font-size:1.2vh}
  .podium-item.podium-2 .name,.podium-item.podium-3 .name{font-size:0.8vh}
  .tier-item{font-size:0.85vh}
  .danmaku-item{font-size:1.0vh}
}
</style>
</head>
<body>

<canvas id="particles"></canvas>

<!-- 等待覆盖层 -->
<div class="waiting-overlay" id="waitingOverlay">
  <div class="waiting-content">
    <div class="waiting-logo">🐢</div>
    <div class="waiting-title">海龟汤</div>
    <div class="waiting-sub">等待开播...</div>
    <div class="waiting-dots"><span></span><span></span><span></span></div>
  </div>
</div>

<div class="app" id="app">
  <!-- 顶栏 -->
  <div class="top-bar fade-in">
    <div class="brand">
      <div class="logo">🐢</div>
      <div class="brand-text">
        <div class="brand-title">海龟汤</div>
        <div class="brand-sub">LIVE · GUESS SOUP</div>
      </div>
    </div>
    <div class="like-progress" id="likeProgress">
      <div class="like-progress-row">
        <span class="like-icon">👍</span>
        <div class="progress-track">
          <div class="like-fill" id="likeFill"></div>
          <div class="progress-markers" id="likeMarkers"></div>
        </div>
        <span class="progress-label" id="likeLabel">0/--</span>
      </div>
      <div class="threshold-row">
        <span class="tl-label">点赞切换难度</span>
        <div class="like-thresholds" id="likeThresholds"></div>
      </div>
    </div>
    <div class="status-pills">
      <span class="pill diff" id="diffBadge">难度：简单</span>
    </div>
  </div>

  <!-- 汤面区 -->
  <div class="surface-area fade-in">
    <div class="surface-label">汤面</div>
    <div class="surface-text" id="surfaceText"></div>
  </div>

  <!-- 谜底揭示 -->
  <div class="reveal-area fade-in">
    <div class="reveal-header">
      <div class="reveal-title">谜底揭示</div>
      <div class="reveal-stats">
        <span>已揭示 <span class="val" id="revealedCount">0</span></span>
        <span>剩余 <span class="val" id="hiddenCount">0</span></span>
      </div>
    </div>
    <div class="reveal-scroll" id="revealScroll"></div>
  </div>

  <!-- 底部行 (进度条 + 礼物栏) -->
  <div class="bottom-row fade-in">
    <div class="progress-area">
      <div class="progress-row">
        <span>揭示进度</span>
        <span class="pct" id="progressText">0%</span>
      </div>
      <div class="progress-bar">
        <div class="progress-fill" id="progressFill" style="width:0%"></div>
      </div>
    </div>
    <div class="gift-list-area" id="giftListArea">
      <div class="gift-list" id="giftList"></div>
    </div>
  </div>

  <!-- 底部互动 -->
  <div class="bottom-area fade-in">
    <div class="answer-bubbles" id="answerBubbles"></div>
    <div class="danmaku-panel">
      <div class="danmaku-header">
        <span class="danmaku-label">💬 弹幕</span>
        <span class="danmaku-count" id="danmakuCount">0</span>
      </div>
      <div class="danmaku-scroll" id="danmakuScroll"></div>
    </div>
    <div class="info-panel">
      <div class="info-title">🏆 排行</div>
      <div class="tier-top3" id="tierTop3"></div>
      <div class="tier-rest" id="tierRest"></div>
    </div>
  </div>
</div>

<!-- 浮层容器 -->
<div id="float-layer"></div>
<div class="gift-scroll" id="giftScroll"></div>
<div class="tts-bar" id="ttsBar"><span class="icon">🔊</span><span class="text" id="ttsText"></span></div>

<script>
// ══════════════════════════════════════════
// 配置
// ══════════════════════════════════════════
const CONFIG = {
  wsUrl: (location.protocol==='https:'?'wss:':'ws:')+'//'+location.host+'/ws',
  maxDanmaku: 40,
  giftFullscreenMinCoins: 1000,  // 触发全屏扇光
  hintDisappearMs: 60000,
  settlementHideMs: 5000,
  ttsEnabled: true,
  ttsRate: 1.0,
  ttsVolume: 0.8,
};

// 礼物列表：从控制面板动态获取
let currentSlots = []; // 缓存槽位配置

async function fetchSlotConfig() {
  try {
    const resp = await fetch('/api/admin/slots');
    const data = await resp.json();
    currentSlots = data.slots || [];
    renderSlotGifts();
    renderLikeThresholds();
  } catch(e) { console.warn('[Slots] 获取槽位配置失败', e); }
}

function renderSlotGifts() {
  const el = document.getElementById('giftList');
  if (!el) return;
  // 只显示非点赞模式的槽位
  const displaySlots = (currentSlots || []).filter(s => !s.like_mode);
  if (displaySlots.length === 0) {
    el.innerHTML = '<div style="font-size:1vh;color:var(--text-dimmer)">暂无礼物</div>';
    return;
  }
  el.innerHTML = displaySlots.map(s =>
    '<div class="gift-item" title="' + escapeHtml(s.name) + ' · ' + escapeHtml(s.desc) + '">' +
    '<span class="gi-icon">' + (s.gift_icon && s.gift_icon.startsWith('http') ? '<img src="' + escapeHtml(s.gift_icon) + '" alt="' + escapeHtml(s.gift_name || '') + '">' : '🎁') + '</span>' +
    '<span class="gi-name">' + escapeHtml(s.gift_name || '未绑定') + '</span>' +
    '<span class="gi-func">' + escapeHtml(s.name) + '</span>' +
    '</div>'
  ).join('');
}

function renderLikeThresholds() {
  const markersEl = document.getElementById('likeMarkers');
  const labelsEl = document.getElementById('likeThresholds');
  // 筛选开启了点赞模式的槽位，按阈值排序
  const likeSlots = (currentSlots || []).filter(s => s.like_mode).sort((a,b) => (a.like_threshold||0) - (b.like_threshold||0));
  if (likeSlots.length === 0) {
    markersEl.innerHTML = '';
    labelsEl.innerHTML = '';
    return;
  }
  const maxThreshold = likeSlots[likeSlots.length-1].like_threshold || 800;
  // 生成竖线标记
  markersEl.innerHTML = likeSlots.map(s => {
    const pct = (s.like_threshold / maxThreshold * 100);
    return '<span class="marker" style="left:' + pct + '%" data-slot="' + s.id + '"></span>';
  }).join('');
  // 生成阈值标签
  labelsEl.innerHTML = likeSlots.map(s => {
    const pct = (s.like_threshold / maxThreshold * 100);
    const _dn = escapeHtml(s.name).replace('难度-', '');
    return '<span class="tl" style="left:' + pct + '%" data-slot="' + s.id + '">' + s.like_threshold + '→' + _dn + '</span>';
  }).join('');
}

function fitRevealChars() {
  const container = document.getElementById('revealScroll');
  if (!container) return;
  const boxes = container.querySelectorAll('.char-box');
  if (!boxes.length) return;
  const gapVw = 0.5;
  const gapPx = container.clientWidth * gapVw / 100;
  const cs = getComputedStyle(container);
  const padW = parseFloat(cs.paddingLeft) + parseFloat(cs.paddingRight);
  const padH = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
  const availW = container.clientWidth - padW;
  const availH = container.clientHeight - padH;
  const total = boxes.length;
  let lo = 4, hi = 48, best = 4;
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    const bw = mid * 1.15 + 8;
    const bh = mid * 1.3 + 8;
    const cols = Math.max(1, Math.floor((availW + gapPx) / (bw + gapPx)));
    const rows = Math.ceil(total / cols);
    const needH = rows * (bh + gapPx) - gapPx;
    if (needH <= availH && cols >= 1) { best = mid; lo = mid + 1; }
    else { hi = mid - 1; }
  }
  container.style.setProperty('--cb-font-size', best + 'px');
  container.style.setProperty('--cb-w', Math.round(best * 1.15 + 8) + 'px');
  container.style.setProperty('--cb-h', Math.round(best * 1.3 + 8) + 'px');
}
window.addEventListener('resize', fitRevealChars);
if (window.ResizeObserver) {
  const rs = document.getElementById('revealScroll');
  if (rs) new ResizeObserver(() => fitRevealChars()).observe(rs);
}

function fitSurfaceText() {
  const el = document.getElementById('surfaceText');
  if (!el || !el.textContent) return;
  const area = el.parentElement;
  const label = area.querySelector('.surface-label');
  const labelH = label ? label.offsetHeight : 0;
  const cs = getComputedStyle(area);
  const padH = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom);
  const availH = area.clientHeight - padH - labelH - 4;
  let lo = 8, hi = 60, best = 8;
  while (lo <= hi) {
    const mid = Math.floor((lo + hi) / 2);
    el.style.fontSize = mid + 'px';
    if (el.scrollHeight <= availH) { best = mid; lo = mid + 1; }
    else { hi = mid - 1; }
  }
  el.style.fontSize = best + 'px';
}
if (window.ResizeObserver) {
  const sa = document.querySelector('.surface-area');
  if (sa) new ResizeObserver(() => fitSurfaceText()).observe(sa);
}
window.addEventListener('resize', fitSurfaceText);

let ws = null;
let reconnectTimer = null;
let currentRoom = null;

// ══════════════════════════════════════════
// WebSocket
// ══════════════════════════════════════════
function connect() {
  if (ws && ws.readyState !== WebSocket.CLOSED) ws.close();
  ws = new WebSocket(CONFIG.wsUrl);
  ws.onopen = () => {
    console.log('[WS] 已连接');
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null; }
    fetchSlotConfig();
  };
  ws.onclose = () => { console.log('[WS] 断开'); scheduleReconnect(); };
  ws.onerror = (e) => console.warn('[WS] 错误', e);
  ws.onmessage = (e) => {
    try { handleMessage(JSON.parse(e.data)); } catch(err) { console.warn('[WS] 解析失败', e.data); }
  };
}
function scheduleReconnect() {
  if (reconnectTimer) return;
  reconnectTimer = setTimeout(() => { reconnectTimer = null; connect(); }, 3000);
}

function handleMessage(msg) {
  switch(msg.type) {
    case 'connected':
      if (msg.phase) setPhase(msg.phase);
      break;
    case 'state_sync':
      currentRoom = msg.room;
      if (msg.room) {
        if (msg.room.difficulty_name) document.getElementById('diffBadge').textContent = '难度：' + msg.room.difficulty_name;
        if (msg.room.phase) setPhase(msg.room.phase);
        if (msg.room.char_states) {
          renderCharStates(msg.room.char_states);
          updateProgress(msg.room.char_states);
        }
        if (msg.room.soup_text) {
          document.getElementById('surfaceText').textContent = msg.room.soup_text;
          fitSurfaceText();
        }
      }
      break;
    case 'game_start':
      document.getElementById('diffBadge').textContent = '难度：' + (msg.difficulty_name || '');
      setPhase(msg.phase || 'playing');
      renderCharStates(msg.charStates);
      updateProgress(msg.charStates);
      clearDanmaku();
      document.getElementById('answerBubbles').innerHTML = '';
      // 填充汤面文本
      document.getElementById('surfaceText').textContent = msg.surface || '';
      fitSurfaceText();
      // 朗读汤面 (TTS 字幕条)
      speakTTS('汤面：' + (msg.surface || ''), 8000);
      break;
    case 'reveal_update':
      renderCharStates(msg.charStates);
      updateProgress(msg.charStates);
      if (msg.newChars && msg.newChars.length) {
        msg.newChars.forEach(ch => flashChar(ch, msg.antiStall));
      }
      break;
    case 'classification':
      addDanmakuItem(msg);
      updateQA(msg);
      break;
    case 'hint':
    case 'auto_hint':
      showHint(msg.hint || msg.script || msg.text || '', msg.autoHide);
      break;
    case 'gift_effect':
      handleGiftEffect(msg);
      break;
    case 'game_end':
      document.getElementById('float-layer').innerHTML = '';
      setPhase('complete');
      renderCharStates(msg.charStates);
      updateProgress(msg.charStates);
      if (msg.bottom) {
        showSettlement(msg.winner, msg.bottom);
        speakTTS('谜底揭晓：' + msg.bottom, 12000);
      }
      break;
    case 'tier_up':
      showTierUp(msg);
      break;
    case 'difficulty_scheduled':
      if (msg.nextDifficultyName) {
        const badge = document.getElementById('diffBadge');
        const oldText = badge.textContent;
        badge.textContent = '⏭ ' + msg.nextDifficultyName;
        badge.style.boxShadow = '0 0 20px rgba(0,212,255,0.6)';
        setTimeout(() => { badge.textContent = oldText; badge.style.boxShadow = ''; }, 6000);
      }
      break;
    case 'like_update':
      // 服务器发送 {slotId, progress, threshold}
      updateLikeProgress(msg.slotId, msg.progress, msg.threshold);
      break;
    case 'slots_updated':
      fetchSlotConfig();
      break;
    case 'score_update':
      // 由 metrics_update 统一刷新
      break;
    case 'danmu':
      // 外部推流的弹幕
      addExternalDanmu(msg.data);
      break;
    case 'theme_change':
      location.reload();
      break;
  }
}

// ══════════════════════════════════════════
// 渲染: 字符状态
// ══════════════════════════════════════════
function renderCharStates(states) {
  if (!states) return;
  const container = document.getElementById('revealScroll');
  container.innerHTML = '';
  states.forEach((s, i) => {
    const div = document.createElement('div');
    div.className = 'char-box';
    div.dataset.char = s.char;
    div.dataset.idx = i;
    if (s.revealed) {
      div.classList.add('revealed');
      div.textContent = s.char;
    } else if (!s.isContent) {
      div.classList.add('function-word');
      div.textContent = s.char;
    } else {
      div.classList.add('hidden');
    }
    if (/[，。！？、；：""''（）《》【】\s]/.test(s.char)) div.classList.add('punct');
    container.appendChild(div);
  });
  const content = states.filter(s => s.isContent);
  const revealed = content.filter(s => s.revealed).length;
  document.getElementById('revealedCount').textContent = revealed;
  document.getElementById('hiddenCount').textContent = content.length - revealed;
  requestAnimationFrame(fitRevealChars);
}

function flashChar(ch, isAntiStall) {
  const boxes = document.querySelectorAll('.char-box[data-char="' + cssEscape(ch) + '"]');
  boxes.forEach(b => {
    b.classList.add('highlight');
    if (isAntiStall) b.style.boxShadow = '0 0 30px var(--red)';
    setTimeout(() => {
      b.classList.remove('highlight');
      if (isAntiStall) b.style.boxShadow = '';
    }, 2000);
  });
}

function cssEscape(s) {
  if (window.CSS && CSS.escape) return CSS.escape(s);
  return s.replace(/["\\]/g, '\\$&');
}

function updateProgress(states) {
  if (!states) return;
  const content = states.filter(s => s.isContent);
  const revealed = content.filter(s => s.revealed).length;
  const total = content.length;
  const pct = total > 0 ? (revealed / total * 100) : 0;
  const pctEl = document.getElementById('progressText');
  const fillEl = document.getElementById('progressFill');
  if (pctEl) pctEl.textContent = Math.round(pct) + '%';
  if (fillEl) {
    fillEl.style.width = pct + '%';
    fillEl.className = 'progress-fill';
    if (pct > 66) fillEl.classList.add('danger');
    else if (pct > 33) fillEl.classList.add('warning');
  }
}

// ══════════════════════════════════════════
// 弹幕
// ══════════════════════════════════════════
function addDanmakuItem(msg) {
  const scroll = document.getElementById('danmakuScroll');
  const item = document.createElement('div');
  item.className = 'danmaku-item';
  let tagClass = 'yes', tagText = '✓是';
  switch(msg.answerType) {
    case '是': tagClass='yes'; tagText='✓'; break;
    case '不是': tagClass='no'; tagText='✗'; break;
    case '是也不是': tagClass='maybe'; tagText='△'; break;
    default: tagClass='maybe'; tagText='?'; break;
  }
  item.innerHTML = '<span class="dm-user">' + escapeHtml(msg.user||'观众') + '</span><span class="dm-text">' + escapeHtml(msg.text||'') + '</span><span class="dm-tag ' + tagClass + '">' + tagText + '</span>';
  scroll.appendChild(item);
  scroll.scrollTop = scroll.scrollHeight;
  while (scroll.children.length > CONFIG.maxDanmaku) scroll.removeChild(scroll.firstChild);
  updateQACount();
}

function addExternalDanmu(data) {
  if (!data) return;
  const scroll = document.getElementById('danmakuScroll');
  const item = document.createElement('div');
  item.className = 'danmaku-item';
  item.innerHTML = '<span class="dm-user">' + escapeHtml(data.user||'观众') + '</span><span class="dm-text">' + escapeHtml(data.content||'') + '</span>';
  scroll.appendChild(item);
  scroll.scrollTop = scroll.scrollHeight;
  while (scroll.children.length > CONFIG.maxDanmaku) scroll.removeChild(scroll.firstChild);
}

function updateQACount() {
  const count = document.getElementById('danmakuScroll').querySelectorAll('.danmaku-item').length;
  document.getElementById('danmakuCount').textContent = count;
}

function updateQA(msg) {
  if (!msg || msg.answerType === 'hint') return;
  const container = document.getElementById('answerBubbles');
  if (!container) return;
  const bubble = document.createElement('div');
  const cls = msg.answerType === '是' ? 'yes' : msg.answerType === '不是' ? 'no' : 'maybe';
  const label = msg.answerType === '是' ? '是的' : msg.answerType === '不是' ? '不是' : '是也不是';
  bubble.className = 'answer-bubble ' + cls;
  bubble.innerHTML = '<span class="name">' + escapeHtml(msg.user||'观众') + '</span><span class="ans">' + label + '</span>';
  container.appendChild(bubble);
  setTimeout(() => { if (bubble.parentNode) bubble.remove(); }, 5000);
  while (container.children.length > 20) container.removeChild(container.firstChild);
}

function clearDanmaku() {
  document.getElementById('danmakuScroll').innerHTML = '';
  updateQACount();
}

// ══════════════════════════════════════════
// 点赞进度条
// ══════════════════════════════════════════
// 点赞进度条（多槽位模式）
let likeProgressData = {}; // {slotId: {progress, threshold}}

function updateLikeProgress(slotId, progress, threshold) {
  if (!slotId) return;
  // 更新该槽位的进度
  likeProgressData[slotId] = {progress: progress || 0, threshold: threshold || 500};
  // 计算整体进度：取百分比最高的活跃槽位
  const entries = Object.entries(likeProgressData);
  let displayProgress = 0, displayThreshold = 800;
  let currentSlotId = slotId;
  // 找到当前阈值最高的槽位作为显示基准
  for (const [sid, data] of entries) {
    if (data.threshold > displayThreshold) displayThreshold = data.threshold;
  }
  // 找到当前百分比最高的槽位作为填充依据
  let maxPct = 0;
  for (const [sid, data] of entries) {
    const pct = data.threshold > 0 ? (data.progress / data.threshold * 100) : 0;
    if (pct > maxPct) { maxPct = pct; displayProgress = data.progress; currentSlotId = sid; }
  }
  // 更新进度条
  const bar = document.getElementById('likeProgress');
  const fill = document.getElementById('likeFill');
  const label = document.getElementById('likeLabel');
  const pct = Math.min(100, displayProgress / displayThreshold * 100);
  fill.style.width = pct + '%';
  label.textContent = displayProgress + '/' + displayThreshold;
  // 颜色变化
  if (displayProgress >= displayThreshold) fill.style.background = 'linear-gradient(90deg,#f59e0b,#ef4444)';
  else if (pct > 66) fill.style.background = 'linear-gradient(90deg,#22c55e,#f59e0b)';
  else fill.style.background = 'linear-gradient(90deg,#22c55e,#fbbf24)';
  // 更新阈值标记状态
  document.querySelectorAll('#likeThresholds .tl').forEach(el => {
    const sid = el.dataset.slot;
    const data = likeProgressData[sid];
    el.classList.toggle('reached', data && data.progress >= data.threshold);
  });
  document.querySelectorAll('#likeMarkers .marker').forEach(el => {
    const sid = el.dataset.slot;
    const data = likeProgressData[sid];
    el.classList.toggle('reached', data && data.progress >= data.threshold);
  });
}

// ══════════════════════════════════════════
// 礼物效果
// ══════════════════════════════════════════
function handleGiftEffect(msg) {
  const coins = msg.coins || 0;
  const user = msg.user || '观众';
  const giftName = msg.giftName || '礼物';
  const icon = msg.icon || '🎁';
  const script = msg.script || '';
  const combo = msg.combo || 1;

  // TTS 字幕条
  if (script) speakTTS(script, 5000);

  // 高价礼物: 全屏扇光
  if (coins >= CONFIG.giftFullscreenMinCoins) {
    showFullscreenGift(giftName, user, coins, icon);
  } else {
    // 中央飞屏 + 右上方气泡
    showGiftFly(giftName, user, icon, combo);
    showGiftBubble(giftName, user, coins);
  }
}

function showGiftFly(name, user, icon, combo) {
  const layer = document.getElementById('float-layer');
  const div = document.createElement('div');
  div.className = 'gift-fly';
  div.innerHTML = '<div class="icon-wrap"><span class="icon">' + escapeHtml(icon) + '</span></div>' +
    '<div class="name">' + escapeHtml(name) + '</div>' +
    '<div class="user">感谢 ' + escapeHtml(user) + '</div>' +
    (combo > 1 ? '<div class="combo">🔥x' + combo + ' 连击</div>' : '');
  layer.appendChild(div);
  setTimeout(() => div.remove(), 4000);
}

function showGiftBubble(name, user, coins) {
  const scroll = document.getElementById('giftScroll');
  const div = document.createElement('div');
  div.className = 'gift-bubble';
  div.innerHTML = '<span class="icon">🎁</span><span class="text"><b>' + escapeHtml(user) + '</b> 送 ' + escapeHtml(name) + (coins>0?' ('+coins+'抖币)':'') + '</span>';
  scroll.appendChild(div);
  setTimeout(() => div.remove(), 3500);
  while (scroll.children.length > 5) scroll.removeChild(scroll.firstChild);
}

function showFullscreenGift(name, user, coins, icon) {
  const layer = document.getElementById('float-layer');
  const div = document.createElement('div');
  div.className = 'gift-fullscreen';
  div.innerHTML = '<div class="rays"></div><div class="center"><div class="icon">' + escapeHtml(icon||'🎉') + '</div><div class="name">' + escapeHtml(name) + '</div><div class="user">感谢 ' + escapeHtml(user) + (coins>0?' · '+coins+'抖币':'') + '</div></div>';
  layer.appendChild(div);
  setTimeout(() => div.remove(), 3000);
}

// ══════════════════════════════════════════
// 提示横幅
// ══════════════════════════════════════════
function showHint(text, autoHideMs) {
  const layer = document.getElementById('float-layer');
  layer.querySelectorAll('.hint-banner').forEach(h => h.remove());
  const banner = document.createElement('div');
  banner.className = 'hint-banner';
  banner.innerHTML = '<div class="label">💡 提示</div><div class="text">' + escapeHtml(text) + '</div>';
  layer.appendChild(banner);
  // TTS 同步朗读
  speakTTS('提示：' + text, autoHideMs || 6000);
  setTimeout(() => {
    banner.classList.add('disappear');
    setTimeout(() => banner.remove(), 500);
  }, autoHideMs || CONFIG.hintDisappearMs);
}

// ══════════════════════════════════════════
// 段位升级
// ══════════════════════════════════════════
let tierUpTimer = null;
function showTierUp(msg) {
  if (tierUpTimer) clearTimeout(tierUpTimer);
  const layer = document.getElementById('float-layer');
  const old = layer.querySelector('.tier-up'); if(old) old.remove();
  const tier = msg.to_tier || {};
  const div = document.createElement('div');
  div.className = 'tier-up';
  div.innerHTML = '<div class="icon">' + (tier.icon || '🏆') + '</div><div class="tier-name">' + escapeHtml(tier.name || '') + '</div><div class="user">恭喜 <b>' + escapeHtml(msg.user || '') + '</b></div>' + (msg.from_tier ? '<div class="from-to">' + escapeHtml(msg.from_tier.name || '') + ' → ' + escapeHtml(tier.name || '') + '</div>' : '');
  layer.appendChild(div);
  tierUpTimer = setTimeout(() => { div.remove(); tierUpTimer = null; }, 3500);
}

// ══════════════════════════════════════════
// 通关结算
// ══════════════════════════════════════════
function showSettlement(winner, bottom) {
  const layer = document.getElementById('float-layer');
  const div = document.createElement('div');
  div.className = 'settlement';
  div.innerHTML = '<div class="big">🎉 通关！</div><div class="detail">感谢 <b>' + escapeHtml(winner || '观众') + '</b> 的精彩提问！</div>';
  layer.appendChild(div);
  setTimeout(() => div.remove(), CONFIG.settlementHideMs);
}

// ══════════════════════════════════════════
// TTS 字幕条 (服务器 CosyVoice3 引擎)
// ══════════════════════════════════════════
let ttsTimeout = null;
let ttsAudio = null;
async function speakTTS(text, hideMs) {
  if (!text) return;
  if (ttsTimeout) clearTimeout(ttsTimeout);
  // 独立版若无 TTS 引擎则跳过
  if (window.__STANDALONE__ && !window.__STANDALONE_TTS__) { CONFIG.ttsEnabled = false; }
  // 显示字幕条
  const bar = document.getElementById('ttsBar');
  document.getElementById('ttsText').textContent = text;
  bar.style.display = 'flex';
  bar.classList.add('active');
  // 从服务器获取 CosyVoice3 音频
  if (CONFIG.ttsEnabled) {
    try {
      if (ttsAudio) { ttsAudio.pause(); ttsAudio = null; }
      const resp = await fetch('/api/tts/synthesize', {
        method: 'POST', headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({text: text})
      });
      if (resp.ok) {
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        ttsAudio = new Audio(url);
        // 从响应头读取服务端语速设置并应用到 playbackRate
        const serverRate = parseFloat(resp.headers.get('X-TTS-Rate')) || 1.0;
        ttsAudio.playbackRate = serverRate;
        ttsAudio.onended = () => { URL.revokeObjectURL(url); ttsAudio = null; };
        ttsAudio.play().catch(() => {});
      }
    } catch(e) { /* 服务器 TTS 不可用，静默降级 */ }
  }
  ttsTimeout = setTimeout(() => {
    bar.classList.remove('active');
    setTimeout(() => bar.style.display = 'none', 300);
  }, hideMs || 6000);
}

// ══════════════════════════════════════════
// 阶段
// ══════════════════════════════════════════
function setPhase(phase) {
  const isPlaying = !(phase === 'idle' || phase === 'lobby');
  document.body.classList.toggle('playing-mode', isPlaying);
  // 排行榜始终显示
  const infoPanel = document.querySelector('.info-panel');
  if (infoPanel) infoPanel.style.display = 'flex';
}

// ══════════════════════════════════════════
// 数据统计
// ══════════════════════════════════════════

async function refreshLeaderboard() {
  try {
    const data = await (await fetch('/api/leaderboard?limit=5')).json();
    const list = (data.leaderboard || []).map((u,i) => {
      const tier = typeof u.tier === 'object' && u.tier ? u.tier : {};
      return {
        rank: i+1,
        name: u.name || '',
        tier: tier.name || '',
        tierEmoji: tier.emoji || '',
        score: u.score || 0,
      };
    });
    renderTierList(list);
  } catch(e) {}
}

function renderTierList(list) {
  const top3El = document.getElementById('tierTop3');
  const restEl = document.getElementById('tierRest');
  if (!list || list.length === 0) {
    top3El.innerHTML = '<div style="font-size:1.2vh;color:var(--text-dimmer);text-align:center;padding:1vh;width:100%">暂无排行</div>';
    restEl.innerHTML = '';
    return;
  }
  // 前3按领奖台顺序排列: [2nd, 1st, 3rd]
  const top3 = list.slice(0, 3);
  const rest = list.slice(3);
  // 重新排：索引0→银(左), 1→金(中), 2→铜(右)
  let ordered;
  if (top3.length === 1) {
    ordered = [{item: top3[0], cls: 'podium-1', icon: '🥇'}];
  } else if (top3.length === 2) {
    ordered = [
      {item: top3[1], cls: 'podium-2', icon: '🥈'},
      {item: top3[0], cls: 'podium-1', icon: '🥇'},
    ];
  } else {
    ordered = [
      {item: top3[1], cls: 'podium-2', icon: '🥈'},
      {item: top3[0], cls: 'podium-1', icon: '🥇'},
      {item: top3[2], cls: 'podium-3', icon: '🥉'},
    ];
  }
  top3El.innerHTML = ordered.map(o =>
    '<div class="podium-item ' + o.cls + '">' +
    '<div class="rank-icon">' + o.icon + '</div>' +
    '<div class="name">' + escapeHtml(o.item.name) + '</div>' +
    (o.item.score ? '<span class="score">' + o.item.score + '</span>' : '') +
    '<div class="podium-stand"></div>' +
    '</div>'
  ).join('');
  if (rest.length === 0) {
    restEl.innerHTML = '';
  } else {
    restEl.innerHTML = rest.map(t =>
      '<div class="tier-item">' +
      '<span class="rank-num">' + (top3.length + rest.indexOf(t) + 1) + '</span>' +
      '<span class="name">' + escapeHtml(t.name) + '</span>' +
      (t.tier ? '<span class="tier-badge">' + escapeHtml(t.tierEmoji) + ' ' + escapeHtml(t.tier) + '</span>' : '') +
      (t.score ? '<span class="score">' + t.score + '</span>' : '') +
      '</div>'
    ).join('');
  }
}

// ══════════════════════════════════════════
// 工具
// ══════════════════════════════════════════
function escapeHtml(s) {
  if (s == null) return '';
  const d = document.createElement('div');
  d.textContent = String(s);
  return d.innerHTML;
}

// ══════════════════════════════════════════
// 粒子背景
// ══════════════════════════════════════════
(function initParticles() {
  const canvas = document.getElementById('particles');
  const ctx = canvas.getContext('2d');
  let w = canvas.width = window.innerWidth;
  let h = canvas.height = window.innerHeight;
  window.addEventListener('resize', () => { w=canvas.width=window.innerWidth; h=canvas.height=window.innerHeight; });
  const dots = Array.from({length:30}, () => ({
    x: Math.random()*w, y: Math.random()*h,
    r: Math.random()*1.5+0.5,
    dx: (Math.random()-0.5)*0.3, dy: (Math.random()-0.5)*0.3
  }));
  function draw() {
    ctx.clearRect(0,0,w,h);
    dots.forEach(d => {
      d.x += d.dx; d.y += d.dy;
      if(d.x<0||d.x>w) d.dx*=-1; if(d.y<0||d.y>h) d.dy*=-1;
      ctx.beginPath(); ctx.arc(d.x,d.y,d.r,0,Math.PI*2);
      ctx.fillStyle='rgba(0,212,255,0.4)'; ctx.fill();
    });
    requestAnimationFrame(draw);
  }
  draw();
})();

// ══════════════════════════════════════════
// 启动
// ══════════════════════════════════════════
connect();
fetchSlotConfig();
fitRevealChars();
fitSurfaceText();
refreshLeaderboard();
setInterval(refreshLeaderboard, 10000);
setInterval(() => { if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({type: 'ping'})); }, 5000);
</script>
</body>
</html>"""
