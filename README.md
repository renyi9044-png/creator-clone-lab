# Creator Clone Lab

面向内容创作者的证据驱动研究 Skill。核心用于抖音对标采集与博主蒸馏，并兼容小红书、B 站、快手、微信公众号、网页和本地素材。

它可以把视频、图文、字幕、OCR、语音转写、评论与表现数据整理为可追溯的 JSONL 知识原子，再生成人工审核单元、主题图谱、创作者 AI 分身和 Obsidian 知识库。

## 安装

将仓库中的 `creator-clone-lab` 文件夹复制到：

```text
~/.codex/skills/creator-clone-lab
```

重新打开 Codex 后，可以直接提出：

```text
用 creator-clone-lab 初始化一个抖音对标研究项目
```

首次运行会检查 `yt-dlp`、FFmpeg、语音转文字、OCR 等依赖；缺少工具时会按 Skill 流程安装或提示配置可选接口。

## 数据状态

仓库只包含 Skill、脚本、空模板和虚构测试样本，不包含作者账号数据、抓取结果、知识库、Cookie、登录状态、API Key 或浏览器资料。

每位使用者的数据由初始化命令生成在其自行指定的项目目录中。发布前请继续保留仓库根目录的 `.gitignore`，不要提交个人项目目录或采集文件。

完整流程和命令见 [`creator-clone-lab/SKILL.md`](creator-clone-lab/SKILL.md)。
