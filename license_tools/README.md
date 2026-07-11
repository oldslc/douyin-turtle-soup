# 海龟汤授权码生成工具

开发者专用工具，用于生成 Ed25519 非对称签名授权码。

支持两种运行方式：
- **EXE 版**（推荐）：无需 Python，`dist\keygen.exe` 直接运行
- **Python 版**：需要 Python + 安装依赖

## 快速开始（EXE 版）

```bash
cd license_tools
dist\keygen.exe gen-keys           # 首次：生成密钥对
dist\keygen.exe make <机器码> <类型> # 生成授权码
dist\keygen.exe verify <授权码>     # 验证授权码
dist\keygen.exe machine-id         # 获取本机机器码
```

也可使用 `keygen.bat` 快捷启动（优先 EXE，不存在则回退 Python）。

## 快速开始（Python 版）

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 生成密钥对（仅首次）

```bash
python keygen.py gen-keys
```

输出示例：

```
=======================================================
  密钥对已生成！
=======================================================
  私钥: ...\secret.key  (切勿外泄)
  公钥: ...\public.key

  请将以下公钥复制到 license.py 的 PUBLIC_KEY_HEX：

  PUBLIC_KEY_HEX = "dc3046c6697eb725a37c9469de17bd2fb410572910fd2719cc6e732748fae40b"
```

### 3. 嵌入公钥

```bash
python keygen.py embed
```

这会自动将公钥写入同目录下的 `license.py`（如果存在）。你也可以手动粘贴。

### 4. 获取机器码

在**需要授权的电脑**上运行：

```bash
python keygen.py machine-id
```

或使用 EXE 版（无需 Python）：

```bash
keygen.exe machine-id
```

输出 12 位十六进制机器码，例如：`a1b2c3d4e5f6`

### 5. 生成授权码

```bash
python keygen.py make <机器码> <类型>
```

类型说明：
| 类型 | 有效期 | 说明 |
|------|--------|------|
| `7d` | 7 天 | 体验版 |
| `1m` | 30 天 | 标准版 |
| `1y` | 365 天 | 年度版 |
| `perm` | 永久 | 终身版 |

示例：

```bash
python keygen.py make a1b2c3d4e5f6 1m
```

输出授权码：`LIC-1m-1700000000-a1b2c3d4e5f6-AbCdEfGhIjKlMnOpQrStUvWxYz==`

### 6. 验证授权码（可选）

```bash
python keygen.py verify LIC-1m-1700000000-a1b2c3d4e5f6-AbCdEfGhIjKlMnOpQrStUvWxYz==
```

## 授权码格式

授权码包含以下信息（以 `-` 分隔）：

```
LIC-{类型}-{时间戳}-{机器码前12位}-{Ed25519签名(base64)}
```

- **类型**: 7d / 1m / 1y / perm
- **时间戳**: Unix 时间戳（激活时间）
- **机器码**: 硬件指纹的前 12 位（绑定指定电脑）
- **签名**: Ed25519 私钥签名，防篡改

## 安全说明

- **`secret.key` 是私钥，必须严格保密** — 泄露后任何人都能生成有效授权码
- `public.key` 和 `PUBLIC_KEY_HEX` 是公钥，可以公开（嵌入到分发软件中）
- 每台电脑拥有唯一机器码，授权码与机器码绑定
- 如果更换硬件，需要重新生成授权码
- 建议在本机生成密钥对后，将 `secret.key` 备份到安全位置（如密码管理器）

## 文件说明

| 文件 | 说明 |
|------|------|
| `keygen.py` | 授权码生成工具 Python 脚本 |
| `keygen.bat` | Windows 快捷启动脚本（优先 EXE） |
| `build_keygen_exe.py` | 构建 EXE 的脚本 |
| `dist/keygen.exe` | 编译好的 EXE（可直接分发） |
| `requirements.txt` | Python 依赖 |
| `secret.key` | Ed25519 私钥（`gen-keys` 后生成） |
| `public.key` | Ed25519 公钥（`gen-keys` 后生成） |
| `license.py` | （可选）放入此目录后可用 `embed` 命令自动嵌入公钥 |
