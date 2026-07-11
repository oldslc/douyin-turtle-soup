# V7.2 Dashboard 图表增强 设计

> 父项目：抖音海龟汤 V7（三端分离重构）
> 子项目 V7.2：Dashboard 图表增强
> 日期：2026-07-01

## 目标

增强 dashboard 数据可视化：Canvas 图表增加坐标轴/网格/悬停提示、新增回合数/时长指标、时间范围选择器、修复 gift_series 记录逻辑。

## 架构

不改后端 API，只增强 dashboard.py 的前端 JS + CSS。API 已经返回所有需要的数据。

### 改动清单

**1. Canvas 图表增强 （核心）**

当前 drawChart() 只有折线+渐变填充。增强后：
- Y 轴刻度标签（左对齐）
- 水平网格线（虚线）
- 数据点圆点标记（hover 时高亮）
- Hover tooltip：鼠标悬停时显示精确数值和时间

**2. 时间范围选择器**

在趋势图标题旁加 30分钟 / 1小时 / 4小时 三个 tab。点击后：
- 30分钟：显示最新 30 个数据点（当前行为）
- 1小时：显示最新 60 个数据点
- 4小时：显示最新 240 个数据点

需要 server 端 `danmaku_series` / `gift_series` 保留更多点。当前滑动窗口只保留 30 个点，需改为可配最大 240 点。

**3. 新增指标卡**

- 本局局数：从 stats 或 round_history 表获取
- 本场时长：从 session 开始时间计算
- 答对率：从 qa_history 统计（是/不是/是也不是）

**4. 修复 gift_series 记录**

当前 `_record_series("gift", value=coins)` 记录的是抖币收入（正确）。但说明文档 §16 提到"超出窗口的数据被丢弃"——需确保 window 够大。

## API 变更

- `/api/admin/metrics` 新增字段：`round_count`（本会话局数）、`session_duration`（秒）、`accuracy`（答对率）
- 滑动窗口从 30 扩展到 240 点（可覆盖 4 小时）

## 非目标

- 不引入第三方图表库（保持 Canvas 自绘）
- 不做 WebSocket 实时推送图表（5s 轮询足够）
- 不做主题切换联动（V7.1 已完成）
