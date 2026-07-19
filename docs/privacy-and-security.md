# 隐私与安全

## 发布仓库不包含什么

本仓库不得包含：

- 真实创作者账号资料和用户自己的创作数据。
- 抓取的视频、音频、图片、文章归档和评论数据。
- Cookie、登录令牌、浏览器用户目录和存储状态。
- API Key、`.env`、私钥和服务账号文件。
- SQLite 数据库、处理队列、审核记录和个人 Obsidian Vault。
- 短期签名媒体 URL 或带鉴权参数的分享链接。
- `%USERPROFILE%`、macOS/Linux 用户主目录等个人绝对路径。

仓库中的测试来源、URL、指标和知识原子均为虚构值。

## 本地数据边界

Skill 本体与用户项目分离：

```text
~/.codex/skills/creator-clone-lab/   # 可公开、可更新的 Skill
用户指定目录/projects/<slug>/        # 用户私有研究数据
```

初始化命令不会在 Skill 目录预置作者知识库。每个用户从 `source_count = 0`、`raw_atom_count = 0` 的空项目开始。

## 浏览器登录

- 所有网页抓取由 Playwright 浏览器自动化 Skill 控制。
- Playwright 优先打开公开页面并生成快照、检查登录状态和网络活动。
- 仅在公开访问失败时复用已认证的 Playwright 命名会话。
- 未检测到登录状态时，才请求用户在 Playwright 可视窗口中配合。
- 不要求用户把 Cookie 文本粘贴到对话。
- 不把 Cookie、令牌、Playwright 会话或浏览器存储写入采集清单。

## API Key

Groq 仅作为可选 ASR 兜底，通过环境变量读取：

```text
GROQ_API_KEY
```

Skill 不提供共享 Key，也不把环境变量值写入项目、日志或 Git 仓库。

## 去敏采集清单

`capture_manifest.json` 可以保存：

- 稳定公开 URL。
- 来源 ID、平台、标题、创作者、发布时间。
- 本地媒体与标准化文档路径。
- 可公开指标和理解等级。

不得保存：

- Cookie 与请求头。
- 登录令牌和浏览器会话 ID。
- 短期签名 CDN URL。
- 与采集无关的本机目录。

## 自动发布检查

`tools/validate_release.py` 会检查：

- 必需的 Skill 文件和版本一致性。
- 仓库是否误跟踪项目、捕获、输出、数据库或媒体目录。
- 是否出现个人 Windows/macOS/Linux 用户路径。
- 是否出现常见长格式密钥。

GitHub Actions 在每次推送和 Pull Request 上执行发布检查与端到端测试。

## 用户发布自己的分支前

```bash
python tools/validate_release.py
git status --short
git diff --cached --check
```

还应人工检查暂存文件，因为任何自动规则都不能覆盖全部密钥格式和隐私语义。
