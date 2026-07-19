# 新手上手手册

## 1. 安装 Skill

推荐使用 `skills` CLI：

```bash
npx -y skills add renyi9044-png/creator-clone-lab -g --all
```

查看仓库能识别出的 Skill，但不安装：

```bash
npx -y skills add renyi9044-png/creator-clone-lab --list
```

也可以手动把仓库中的 `creator-clone-lab` 文件夹复制到：

```text
~/.codex/skills/creator-clone-lab
```

安装后重新打开 Codex。

## 2. 第一次工具检查

直接对 Codex 说：

```text
用 creator-clone-lab 检查本机采集、语音转文字、OCR 和图谱工具。
```

也可以在 Skill 目录执行：

```bash
python scripts/check_install_media_tools.py
```

需要自动安装 Python 与系统依赖时：

```bash
python scripts/check_install_media_tools.py --install --install-system
```

核心工具包括：

- Playwright 浏览器自动化 Skill：所有网页平台采集的统一控制入口。
- Node.js / `npx`：Playwright CLI 运行时与兜底启动器。
- `yt-dlp`：公开媒体与页面提取。
- FFmpeg / ffprobe：音视频处理。
- `faster-whisper`：本地语音转文字。
- RapidOCR、OpenCV、Pillow：画面文字和关键帧处理。
- NetworkX、NumPy、Pillow：关系图谱布局与预览。
- SQLite FTS5：本地全文检索。
- `GROQ_API_KEY`：可选的云端语音转文字兜底。

Windows 出现中文解码问题时，先设置：

```powershell
$env:PYTHONUTF8='1'
```

## 3. 初始化空项目

建议一个创作者或一个研究范围对应一个项目：

```text
用 creator-clone-lab 初始化一个名为“测试账号研究”的抖音项目，保存到我指定的目录。
```

底层命令：

```bash
python scripts/init_creator_project.py projects/test-creator \
  --name "测试账号研究" \
  --creator "账号名称" \
  --platform douyin
```

刚初始化的项目必须满足：

```text
source_count = 0
raw_atom_count = 0
promoted_unit_count = 0
topic_map_count = 0
clone_maturity = not-built
```

## 4. 抓取账号或作品

把主页或作品链接交给 Codex：

```text
使用 Playwright 浏览器自动化 Skill 抓取这个抖音主页。先用命名会话打开公开页面、生成快照并检查网络；公开访问不完整时复用已认证的 Playwright 会话；仍未登录再打开可视窗口提醒我配合。
```

所有网页抓取必须先经过 Playwright 页面验证。`yt-dlp` 和平台脚本只在 Playwright 确认目标页面与权限后提取媒体或结构化数据。系统不会要求用户粘贴 Cookie，也不会把 Playwright 会话写入项目。采集结果先进入 `capture_manifest.json`，然后注册为可追溯来源。

## 5. 处理无字幕视频

系统按以下顺序理解内容：

```text
平台字幕 → 本地 ASR → 可选 API ASR
画面字幕 → OCR
动作与场景 → 关键帧/视觉理解
```

只有元数据时，理解等级只能标记为 `metadata-only`；缺少关键语音或场景时只能标记为 `partial`。

## 6. 蒸馏创作者

建议同时准备高表现、普通表现和低表现作品。然后提出：

```text
按定位、选题、思考、表达、视觉和转化五层蒸馏。每条规律写支持来源、反例、表现区间、适用格式和置信度。
```

不要只给爆款样本。只看成功作品会把偶然性误写成方法论。

## 7. 构建 Obsidian 知识库

```text
把已审核的来源、知识原子、内容单元、创作规律和主题地图构建为 Obsidian Vault，并验证所有链接。
```

底层命令：

```bash
python scripts/build_obsidian_vault.py projects/test-creator
python scripts/validate_obsidian_vault.py projects/test-creator/内容资产工程
python scripts/render_obsidian_graph.py projects/test-creator/内容资产工程
```

验证必须报告：无缺失目录、无未解析链接、无重复节点名、无标记错误、无缺失生成文件。

## 8. 用 AI 分身创作

```text
先从知识库检索这个选题对应的受众问题、开头规律、视觉证据和失败反例，再给我写分镜脚本。标明每一段调用了哪条规则。
```

生成视频脚本时，推荐固定为：

```text
画面 / 镜头
台词或字幕
角色动作
这一拍的目的
使用的证据或创作者规则
```

## 9. 发布后复盘

提供 T+1h、T+24h 或更长期数据：

```text
记录这条作品的播放、点赞、评论、分享、收藏和关注变化，并判断问题出在选题、承诺、开头、视觉证明、信息密度、节奏、受众还是转化路径。
```

复盘只能新增证据、调整置信度或拒绝旧规则，不能修改历史来源来迎合结果。

## 10. 常见问题

**为什么抓到了标题，却不直接开始蒸馏？**

标题和描述只能支持 `metadata-only` 判断。看不到台词、画面或互动上下文时，不能声称理解了完整视频。

**一定要登录吗？**

不一定。Playwright 先打开公开页面；平台限制公开访问时，才复用已认证的 Playwright 命名会话或请用户在可视 Playwright 窗口登录。

**知识库是一个大 Markdown 文件吗？**

不是。JSONL 保存数千条原子，Markdown 保存审核后的稳定单元，SQLite 提供检索，Obsidian 展示可点击关系图谱。

**能不能直接复制对标博主？**

系统学习选题判断、结构、证据和表达机制，不应复制原文、具体创意或受版权保护的内容。
