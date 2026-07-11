"""
spam_filter.py — 三层次弹幕过滤 + LLM 输出保护

层次:
  1. 格式过滤: ≤30 字, 不能纯数字/纯标点/纯表情
  2. 频率限制: 每用户 5条/5s, 全局 10条/s, 重复≥3 丢弃
  3. 内容过滤: 玩家弹幕仅拦截屏蔽词; LLM 输出拦截剧透句式

所有拦截静默丢弃。
"""
import re
import time
from collections import defaultdict

# ── 默认屏蔽词列表 ──
DEFAULT_BANNED_WORDS = [
    "加微信", "QQ群", "加群", "私聊", "扫码", "二维码",
    "进群", "拉群", "微信号", "手机号", "电话",
    "代刷", "代练", "外挂", "辅助", "脚本", "刷屏器",
    "赌博", "赌场", "博彩",
    "色情", "黄片", "A片",
    "政治", "领导人", "共产党", "习近平",
    "卖号", "买号", "租号", "交易",
    "广告", "推广", "招代理",
    "骗子", "骗钱", "诈骗",
]

# ── LLM 输出剧透句式 ──
SPOILER_PATTERNS = [
    re.compile(r"答案是"),
    re.compile(r"汤底是"),
    re.compile(r"真相是"),
    re.compile(r"我告诉[你我他她你们我们]"),
    re.compile(r"正确答案[是为]"),
    re.compile(r"其实[这那]?[个件事]?(的|就|是)"),
    re.compile(r"故事[的]?(真相|答案|结局)"),
    re.compile(r"最终答案"),
]

# ── 纯表情/纯数字/纯标点检测 ──
NON_TEXT_PATTERN = re.compile(r"^[\U0001F600-\U0001F64F\U0001F300-\U0001F5FF\U0001F680-\U0001F6FF\U0001F1E0-\U0001F1FF\U0001F200-\U0001F2FF\U0001F900-\U0001F9FF☀-➿︀-️]+$")  # noqa: E501
DIGITS_ONLY = re.compile(r"^\d{1,10}$")
PUNCT_ONLY = re.compile(r"^[，。！？、；：\.\,\!\?\;\:\s\-\_\@\#\$\%\^\&\*\(\)\[\]\{\}]{1,20}$")


class BannedWordsManager:
    """管理屏蔽词列表，支持 CRUD"""

    def __init__(self):
        self._words: list[str] = list(DEFAULT_BANNED_WORDS)
        self._patterns: list[re.Pattern] = self._compile()

    def _compile(self) -> list[re.Pattern]:
        return [re.compile(re.escape(w)) for w in self._words]

    def get_all(self) -> list[str]:
        return list(self._words)

    def add(self, word: str) -> bool:
        w = word.strip()
        if not w or w in self._words:
            return False
        self._words.append(w)
        self._patterns = self._compile()
        return True

    def remove(self, word: str) -> bool:
        if word not in self._words:
            return False
        self._words.remove(word)
        self._patterns = self._compile()
        return True

    def check(self, text: str) -> bool:
        """True = 命中屏蔽词"""
        for p in self._patterns:
            if p.search(text):
                return True
        return False

    def set_all(self, words: list[str]):
        self._words = [w.strip() for w in words if w.strip()]
        self._patterns = self._compile()


class RateLimiter:
    """双桶频率限制 + 重复检测"""

    def __init__(self, per_user_max: int = 5, per_user_window: float = 5.0,
                 global_max: int = 10, global_window: float = 1.0,
                 repeat_threshold: int = 3):
        self.per_user_max = per_user_max
        self.per_user_window = per_user_window
        self.global_max = global_max
        self.global_window = global_window
        self.repeat_threshold = repeat_threshold

        self._user_times: dict[str, list[float]] = defaultdict(list)
        self._global_times: list[float] = []
        self._user_texts: dict[str, list[str]] = defaultdict(list)

    def check_user(self, user: str, text: str) -> tuple[bool, str]:
        """
        Returns (passed: bool, reason: str).
        passed=False means 丢弃此消息.
        """
        now = time.time()

        # 1. 用户窗口清理 + 检查
        times = self._user_times[user]
        cutoff = now - self.per_user_window
        while times and times[0] < cutoff:
            times.pop(0)
        if len(times) >= self.per_user_max:
            return False, f"rate:user:{user}"

        # 2. 全局窗口清理 + 检查
        gt = self._global_times
        gcutoff = now - self.global_window
        while gt and gt[0] < gcutoff:
            gt.pop(0)
        if len(gt) >= self.global_max:
            return False, f"rate:global"

        # 3. 重复检测 (不计入窗口)
        texts = self._user_texts[user]
        cutoff_rep = now - self.per_user_window * 2
        while texts and len(texts) > self.repeat_threshold * 2:
            texts.pop(0)
        if len(texts) >= self.repeat_threshold - 1:
            recent = texts[-(self.repeat_threshold - 1):]
            if all(t == text for t in recent):
                return False, f"repeat:{user}"

        # 4. 记录
        times.append(now)
        gt.append(now)
        texts.append(text)
        return True, ""


class LLMOutputFilter:
    """拦截 LLM 输出中的剧透句式"""

    def check(self, text: str) -> bool:
        """True = 命中剧透模式"""
        for p in SPOILER_PATTERNS:
            if p.search(text):
                return True
        return False


class SpamFilter:
    """三层次弹幕过滤总入口"""

    def __init__(self):
        self.banned = BannedWordsManager()
        self.rate = RateLimiter()
        self.llm = LLMOutputFilter()

    def check_danmaku(self, text: str, user: str) -> tuple[bool, str]:
        """
        过滤玩家弹幕。
        Returns (passed: bool, reason: str).
        passed=False 表示丢弃（已调用方静默处理）。
        """
        text = text.strip()
        if not text:
            return False, "empty"

        # Layer 1: 格式过滤
        if len(text) > 30:
            return False, "format:too_long"
        if NON_TEXT_PATTERN.match(text):
            return False, "format:emoji_only"
        if DIGITS_ONLY.match(text):
            return False, "format:digits_only"
        if PUNCT_ONLY.match(text):
            return False, "format:punct_only"

        # Layer 2: 频率限制
        passed, reason = self.rate.check_user(user, text)
        if not passed:
            return False, reason

        # Layer 3: 内容过滤（屏蔽词）
        if self.banned.check(text):
            return False, "banned_word"

        return True, ""

    def check_llm_output(self, text: str) -> bool:
        """True = 命中剧透，需要丢弃并重试"""
        return self.llm.check(text)


# ── 全局实例 ──
spam_filter = SpamFilter()
