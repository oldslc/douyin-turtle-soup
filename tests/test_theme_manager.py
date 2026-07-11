"""主题管理器单元测试"""
import os
import tempfile
import pytest


@pytest.fixture
def tm():
    """每个测试用独立临时 DB"""
    with tempfile.TemporaryDirectory() as d:
        db = os.path.join(d, "test.db")
        from theme_manager import ThemeManager
        return ThemeManager(db_path=db)


def test_default_active_is_dark(tm):
    """空 DB 时活动主题回退到 dark"""
    assert tm.get_active() == "dark"


def test_set_and_get_active(tm):
    """set_active 后 get_active 返回新值"""
    tm.set_active("starry")
    assert tm.get_active() == "starry"


def test_persistence_across_instances(tmp_path):
    """新实例从同 DB 读到上次写入的值"""
    from theme_manager import ThemeManager
    db = str(tmp_path / "test.db")
    a = ThemeManager(db_path=db)
    a.set_active("festival")
    b = ThemeManager(db_path=db)
    assert b.get_active() == "festival"


def test_unknown_id_falls_back_to_dark(tm):
    """越权值回退到 dark（白名单校验）"""
    tm.set_active("hack")
    assert tm.get_active() == "dark"


def test_list_themes_returns_at_least_three(tm):
    """list_themes 返回至少 3 个内置主题（后续可扩展）"""
    themes = tm.list_themes()
    assert len(themes) >= 3, f"Expected >= 3 themes, got {len(themes)}"
    ids = {t["id"] for t in themes}
    assert ids >= {"dark", "starry", "festival"}, f"Missing core themes in {ids}"


def test_apply_to_html_injects_vars(tm):
    """apply_to_html 返回的 HTML 含主题 CSS 变量"""
    html = "<html><head><style>:root{}</style></head></html>"
    out = tm.apply_to_html(html, "starry")
    assert "--primary: #a855f7" in out
    assert "url('/static/themes/starry/bg.jpg')" in out


def test_apply_to_html_invalid_id_returns_unchanged(tm):
    """无效主题 id 不修改 HTML"""
    html = "<html><head><style>:root{}</style></head></html>"
    out = tm.apply_to_html(html, "hack")
    assert out == html


def test_apply_persists_across_simulated_restart(tmp_path):
    """模拟重启: set → 新实例 → get 验证持久化"""
    from theme_manager import ThemeManager
    db = str(tmp_path / "test.db")
    a = ThemeManager(db_path=db)
    for tid in ["dark", "starry", "festival", "dark"]:
        a.set_active(tid)
        b = ThemeManager(db_path=db)
        assert b.get_active() == tid


def test_apply_to_html_preserves_rest_of_document(tm):
    """注入只改 :root，不破坏其他 HTML"""
    html = "<html><head><style>:root{--old: red;}</style></head><body>其他</body></html>"
    out = tm.apply_to_html(html, "festival")
    assert "其他" in out
    assert "--primary: #ef4444" in out
    assert "--old" not in out  # 旧变量被覆盖


def test_all_themes_have_consistent_var_keys():
    """3 个主题必须有相同的 15 个 CSS 变量键（防缺漏）"""
    from theme_manager import BUILTIN_THEMES
    keys_per_theme = {tid: set(t["vars"].keys()) for tid, t in BUILTIN_THEMES.items()}
    reference = keys_per_theme["dark"]
    for tid, keys in keys_per_theme.items():
        assert keys == reference, f"Theme {tid} missing vars: {reference - keys}"
