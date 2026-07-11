# V7.2 Dashboard 图表增强 实施计划

> **For agentic workers:** 参照 superpowers:subagent-driven-development 流程执行。每任务含独立测试周期。

**目标:** 增强 dashboard 数据可视化：Canvas 图表增加坐标轴/网格/悬停提示、新增指标卡、时间范围选择器、修复硬编码段位名、扩展滑动窗口。

**架构:** 只改 2 个文件：`server_v6.py` 新增 3 个 metrics 字段 + 扩展滑动窗口；`dashboard.py` 前端 JS+CSS 增强。

**Tech Stack:** FastAPI + SQLite + 原生 Canvas 2D（无第三方图表库）

## Global Constraints

- 不引入第三方图表库（保持原生 Canvas 2D）
- 不修改后端 API 签名（只新增字段）
- 新字符串使用中文显示
- 所有 CSS 类名用 kebab-case
- 不改动 overlay.py / admin.py / theme_manager.py

---

### Task 1: server_v6.py — 扩展滑动窗口 + 新增 metrics 字段

**Files:**
- Modify: `backend/server_v6.py:251-269` (_record_series)

**Interfaces:**
- Produces: `/api/admin/metrics` 新增 `round_count`, `session_duration`, `accuracy` 字段

- [ ] **Step 1.1: 扩大 _record_series 滑动窗口至 240 点**

将 `target_len = 30` 改为 `target_len = 240`：

```python
def _record_series(self, kind: str, value: int = 1):
    now = time.time()
    elapsed = int((now - self._series_start) / 60)
    target_len = 240  # 4小时（240分钟）
    ...
```

- [ ] **Step 1.2: 在 metrics API 新增 round_count / session_duration / accuracy**

在 `admin_metrics()` 中，`return {` 之前添加计算：

```python
# V7.2 新增指标
round_count = db_query("SELECT COUNT(*) as cnt FROM round_history")
session_duration = int(time.time() - room.start_time) if room.start_time else 0
total_qa = len(room.qa_history)
correct_qa = sum(1 for q in room.qa_history if q.get("result") in ("是", "是也不是"))
accuracy = round(correct_qa / total_qa * 100, 1) if total_qa > 0 else 0
```

然后在 return dict 中增加：
```python
"round_count": round_count[0]["cnt"] if round_count else 0,
"session_duration": session_duration,
"accuracy": accuracy,
```

- [ ] **Step 1.3: 语法检查 + 提交**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python -m py_compile backend/server_v6.py && echo OK
git add backend/server_v6.py
git commit -m "feat(v7.2): expand series window to 240pts, add round_count/duration/accuracy to metrics"
```

---

### Task 2: dashboard.py — Canvas 图表增强（网格/标签/数据点/悬停提示 + 时间范围选择器）

**Files:**
- Modify: `backend/dashboard.py` — JS `drawChart()` 完全重写 + CSS 新增 tooltip

**Interfaces:**
- Consumes: `m.danmaku_series`（Array[int]）, `m.gift_series`（Array[int]）
- 时间范围：30min（默认，取最后30点）、1h（取最后60点）、4h（取全部240点）

- [ ] **Step 2.1: 新增 tooltip CSS**

在 `</style>` 前添加：

```css
.chart-wrap{position:relative}
.chart-tooltip{position:absolute;display:none;background:rgba(0,0,0,0.85);color:#e2e8f0;padding:6px 10px;border-radius:6px;font-size:11px;pointer-events:none;white-space:nowrap;z-index:10;border:1px solid rgba(255,255,255,0.1);backdrop-filter:blur(4px)}
.time-range{display:flex;gap:4px;margin-bottom:6px}
.time-btn{padding:2px 10px;border:1px solid rgba(255,255,255,0.1);border-radius:4px;background:transparent;color:#64748b;font-size:11px;cursor:pointer;transition:all 0.2s}
.time-btn:hover{border-color:#00d4ff;color:#00d4ff}
.time-btn.active{background:#00d4ff22;border-color:#00d4ff;color:#00d4ff}
```

- [ ] **Step 2.2: 重构 HTML 图表容器**

将每个 chart 的 HTML 替换为带 wrap 的结构：

```html
<div class="card col-2">
  <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
    <h3 style="margin-bottom:0">📈 弹幕趋势</h3>
    <div class="time-range" id="danmakuRange">
      <button class="time-btn active" data-range="30">30分钟</button>
      <button class="time-btn" data-range="60">1小时</button>
      <button class="time-btn" data-range="240">4小时</button>
    </div>
  </div>
  <div class="chart-wrap">
    <canvas id="danmakuChart"></canvas>
    <div class="chart-tooltip" id="danmakuTooltip"></div>
  </div>
</div>
```

同样更新 gift chart 容器。

- [ ] **Step 2.3: 重写 drawChart() 函数**

替换整个 `drawChart()` 函数为增强版本（网格线、Y轴标签、数据点、鼠标悬停 tooltip）：

```javascript
let chartState = { danmaku: { maxRange: 30 }, gift: { maxRange: 30 } };

// 时间范围切换事件
document.querySelectorAll('.time-btn').forEach(btn => {
  btn.addEventListener('click', function() {
    const parent = this.closest('.time-range');
    parent.querySelectorAll('.time-btn').forEach(b => b.classList.remove('active'));
    this.classList.add('active');
    const range = parseInt(this.dataset.range);
    const chartId = parent.id === 'danmakuRange' ? 'danmaku' : 'gift';
    chartState[chartId].maxRange = range;
    // 触发重绘 — 下次 refreshMetrics 完成
  });
});

function drawChart(id, data, color, label) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  const ctx = canvas.getContext('2d');
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.round(rect.width * dpr);
  canvas.height = Math.round(rect.height * dpr);
  ctx.scale(dpr, dpr);
  const w = rect.width, h = rect.height;
  ctx.clearRect(0, 0, w, h);

  // 时间范围切片
  const rangeKey = id === 'danmakuChart' ? 'danmaku' : 'gift';
  const maxRange = (chartState[rangeKey] || {}).maxRange || 30;
  const sliced = data ? data.slice(-maxRange) : [];
  if (!sliced || sliced.length < 2) {
    ctx.fillStyle = '#64748b'; ctx.font = '12px sans-serif';
    ctx.textAlign = 'center'; ctx.fillText('等待数据...', w/2, h/2);
    return;
  }

  const max = Math.max(...sliced, 1);
  const padding = { top: 8, right: 8, bottom: 16, left: 36 };
  const plotW = w - padding.left - padding.right;
  const plotH = h - padding.top - padding.bottom;
  const step = plotW / (sliced.length - 1);

  // Y轴网格线 + 标签
  ctx.textAlign = 'right';
  ctx.font = '10px sans-serif';
  ctx.strokeStyle = 'rgba(255,255,255,0.06)';
  ctx.lineWidth = 1;
  ctx.fillStyle = '#64748b';
  const ySteps = 4;
  for (let i = 0; i <= ySteps; i++) {
    const y = padding.top + (plotH / ySteps) * i;
    const val = Math.round(max - (max / ySteps) * i);
    ctx.beginPath();
    ctx.setLineDash([3, 3]);
    ctx.moveTo(padding.left, y);
    ctx.lineTo(w - padding.right, y);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.fillText(val, padding.left - 4, y + 3);
  }

  // 渐变填充
  const grad = ctx.createLinearGradient(0, padding.top, 0, h);
  grad.addColorStop(0, color + '66');
  grad.addColorStop(1, color + '00');
  ctx.beginPath();
  ctx.moveTo(padding.left, h - padding.bottom);
  sliced.forEach((v, i) => {
    ctx.lineTo(padding.left + i * step, padding.top + plotH - (v / max * plotH));
  });
  ctx.lineTo(padding.left + (sliced.length-1) * step, h - padding.bottom);
  ctx.closePath();
  ctx.fillStyle = grad;
  ctx.fill();

  // 折线
  ctx.beginPath();
  sliced.forEach((v, i) => {
    const x = padding.left + i * step;
    const y = padding.top + plotH - (v / max * plotH);
    if (i === 0) ctx.moveTo(x, y);
    else ctx.lineTo(x, y);
  });
  ctx.strokeStyle = color;
  ctx.lineWidth = 2;
  ctx.stroke();

  // 数据点圆点
  sliced.forEach((v, i) => {
    const x = padding.left + i * step;
    const y = padding.top + plotH - (v / max * plotH);
    ctx.beginPath();
    ctx.arc(x, y, 2.5, 0, Math.PI * 2);
    ctx.fillStyle = color;
    ctx.fill();
    ctx.strokeStyle = '#0c0f1e';
    ctx.lineWidth = 1;
    ctx.stroke();
  });

  // tooltip hover — 存储数据供 mousemove 使用
  canvas._chartData = { sliced, max, step, padding, plotW, plotH, color, label: label || id, rangeKey };
}
```

- [ ] **Step 2.4: 添加 mousemove tooltip 事件监听**

在 `refreshMetrics()` 中或全局事件监听：

```javascript
document.addEventListener('mousemove', function(e) {
  const tooltipEls = { danmaku: document.getElementById('danmakuTooltip'), gift: document.getElementById('giftTooltip') };
  Object.entries({ danmakuChart: 'danmaku', giftChart: 'gift' }).forEach(([canvasId, key]) => {
    const canvas = document.getElementById(canvasId);
    const tooltip = tooltipEls[key === 'danmaku' ? 'danmaku' : 'gift'];
    if (!canvas || !tooltip || !canvas._chartData) { if(tooltip) tooltip.style.display = 'none'; return; }
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left;
    const my = e.clientY - rect.top;
    const d = canvas._chartData;
    if (mx < 0 || mx > rect.width || my < 0 || my > rect.height) {
      tooltip.style.display = 'none'; return;
    }
    const idx = Math.round((mx - d.padding.left) / d.step);
    if (idx < 0 || idx >= d.sliced.length) { tooltip.style.display = 'none'; return; }
    const val = d.sliced[idx];
    tooltip.style.display = 'block';
    tooltip.style.left = (d.padding.left + idx * d.step + 8) + 'px';
    tooltip.style.top = (d.padding.top + d.plotH - (val / d.max * d.plotH) - 30) + 'px';
    tooltip.textContent = val + (d.label ? ' ' + d.label : '');
  });
});
```

- [ ] **Step 2.5: 更新 updateMetrics 传递 label 到 drawChart**

```javascript
if (m.danmaku_series) drawChart('danmakuChart', m.danmaku_series, '#00d4ff', '条/分');
if (m.gift_series) drawChart('giftChart', m.gift_series, '#fbbf24', '抖币/分');
```

- [ ] **Step 2.6: 验证**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python -m py_compile backend/dashboard.py && echo OK
```

---

### Task 3: dashboard.py — 新增 3 个指标卡 + 修复硬编码段位名

**Files:**
- Modify: `backend/dashboard.py` — HTML（3 个新 card）+ CSS + JS updateMetrics()

**Interfaces:**
- Consumes: `m.round_count`, `m.session_duration`, `m.accuracy`

- [ ] **Step 3.1: 新增 3 个指标卡 HTML**

在 `付费率` 卡片后面、`弹幕趋势` 图表前面添加：

```html
<div class="card col-1">
  <h3>本场局数</h3>
  <div class="metric green" id="roundCount">0<span class="unit">局</span></div>
</div>

<div class="card col-1">
  <h3>本场时长</h3>
  <div class="metric" id="sessionDuration">00:00<span class="unit"></span></div>
</div>

<div class="card col-1">
  <h3>答对率</h3>
  <div class="metric gold" id="accuracy">0<span class="unit">%</span></div>
</div>
```

- [ ] **Step 3.2: 将 grid 改为适应 3 行（4+3=7 个 col-1 卡片，grid 自动换行）**

当前 `.app` 是 `grid-template-columns: repeat(4,1fr)`。7 个 col-1 卡 → 前 4 一行，后 3 下一行。自然换行，无需改 grid。

- [ ] **Step 3.3: 在 `updateMetrics()` 中添加 3 个新字段更新**

```javascript
document.getElementById('roundCount').innerHTML = (m.round_count||0) + '<span class="unit">局</span>';
// 时长格式化
const dur = m.session_duration || 0;
const mins = Math.floor(dur / 60);
const secs = dur % 60;
document.getElementById('sessionDuration').innerHTML = String(mins).padStart(2,'0') + ':' + String(secs).padStart(2,'0');
document.getElementById('accuracy').innerHTML = (m.accuracy||0) + '<span class="unit">%</span>';
```

- [ ] **Step 3.4: 修复 `updateTierDist()` 硬编码段位名**

从 API 响应中动态获取段位列表，或从服务器获取 tier_dist 的 key 列表：

```javascript
function updateTierDist(dist) {
  const container = document.getElementById('tierDist');
  if (!dist || Object.keys(dist).length === 0) {
    container.innerHTML = '<div style="text-align:center;color:#64748b;padding:16px;font-size:12px">暂无数据</div>';
    return;
  }
  container.innerHTML = Object.entries(dist).map(([tier, count]) =>
    '<div class="td-item"><span class="num">' + count + '</span><span class="label">' + tier + '</span></div>'
  ).join('');
}
```

- [ ] **Step 3.5: 语法检查 + 提交**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python -m py_compile backend/dashboard.py && echo OK
git add backend/dashboard.py backend/server_v6.py
git commit -m "feat(v7.2): dashboard charts with grid/labels/tooltip/time-range, new metric cards, dynamic tier dist"
```

---

### Task 4: 集成测试验证

- [ ] **Step 4.1: 启动服务并验证 metrics API 新增字段**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python backend/server_v6.py &
SERVER_PID=$!
sleep 2
echo "--- Metrics API ---"
curl -s http://localhost:3010/api/admin/metrics | python -c "import sys,json; d=json.load(sys.stdin); print('round_count:', d.get('round_count')); print('session_duration:', d.get('session_duration')); print('accuracy:', d.get('accuracy')); print('danmaku_series len:', len(d.get('danmaku_series',[])))"
kill $SERVER_PID
```

- [ ] **Step 4.2: 检查 dashboard HTML 是否返回**

```bash
cd "C:\Users\27871\OneDrive\Documents\抖音海龟汤"
python backend/server_v6.py &
SERVER_PID=$!
sleep 2
curl -s http://localhost:3010/dashboard | head -c 500
kill $SERVER_PID
```
