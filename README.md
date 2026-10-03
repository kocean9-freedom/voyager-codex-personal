# Voyager Codex Personal

供个人使用的 Codex 插件：从 Codex 工作任务读取工作任务与普通 ChatGPT 聊天，在独立的本机查看器中回看消息，保存两类会话的星标和个人文件夹。本项目由 `kocean9-freedom` 委托 AI 辅助实现，交互目标受 [voyager-crew/voyager](https://github.com/voyager-crew/voyager) 启发；这是独立的 Codex 插件源码仓库，不是 Voyager 浏览器扩展的移植或官方版本。来源关系详见 [NOTICE.md](./NOTICE.md)。

**重要限制：这个插件不能让 Codex/ChatGPT 桌面应用的普通聊天页面自动出现原生时间线。** 当前交付的查看器是独立页面，不是截图中聊天正文旁的时间线。公开[对话面板接口](https://developers.openai.com/plugins/build/extensions)允许插件在对话旁打开自己的面板，但没有向面板提供当前聊天的完整历史或原消息滚动控制；[插件规范](https://github.com/openai/mcp-extensions/blob/main/docs/spec.md)中的对话入口只传入空参数。

## 功能与边界

| 需求 | 实现 |
| --- | --- |
| 查看消息节点 | 从 Codex 工作任务读取会话，在独立本机查看器显示可点击时间线 |
| 跳转历史消息 | 点击节点可定位到查看器里的消息卡片；无法精确滚动原会话 |
| 给消息加星标 | 在查看器内点击星标，按会话 ID 与消息 ID 保存到本机 JSON；非应用原生星标 |
| 文件夹整理 | 在查看器内保存本地文件夹；两类会话共用数据，工作任务还可另外放入 Codex 原生侧边栏分区 |

这个插件通过 Codex 任务工具读取普通聊天并生成本地快照。独立查看器不能作为“普通聊天已有内置时间线”的验证结果。若需要截图中那种自动跟随当前聊天、点击后滚动原消息的时间线，需要桌面应用提供相应公开接口。

## 安装

当前这台机器的插件源码位于 `~/plugins/voyager-codex-personal`，个人插件目录已登记在 `~/.agents/plugins/marketplace.json`。在本机运行：

```sh
codex plugin add voyager-codex-personal@personal
```

然后在 Codex 桌面版中开启新任务，使新插件技能生效。此插件调用桌面版的 `codex-app-tools`；独立 Codex CLI 会话可以加载技能，但当前测试环境中没有这些桌面任务工具，因而无法在 CLI 读取任务时间线。独立查看器由只绑定本机 `127.0.0.1` 的临时服务提供，关闭服务后页面不可用；不需要账号或外部网络服务。脚本依赖 macOS/Linux 的 Python 3 标准库。

若从 GitHub 在另一台机器安装，先将本仓库克隆到 `~/plugins/voyager-codex-personal`，再在该机器的个人插件市场登记此本地目录并执行上面的安装命令。仓库不包含本机的市场配置、聊天快照或星标数据。

## 使用

安装后可说：

- “用 Voyager 显示这个 Codex 任务的时间线，找出提到测试失败的消息。”
- “用 Voyager 生成普通聊天‘论文阅读顺序建议’的独立时间线查看器。”
- “把刚才那条回答加星标，列出本会话星标。”
- “把这个工作任务和‘论文阅读顺序建议’聊天都归入本地‘研究’文件夹。”
- “把‘分析 Voyager 项目功能与场景’任务放进 Codex 侧边栏的‘研究’分区。”
- “打开这条旧消息所在的会话，并给我可查找的摘录。”

本地星标和个人文件夹保存在 `~/.local/share/voyager-codex-personal/stars.json`。可备份这个文件；删除它会移除本插件保存的星标和分类，不影响原始会话。若设置了 `XDG_DATA_HOME`，文件保存在该目录下的 `voyager-codex-personal/stars.json`。读取的时间线快照保存在本机 `timelines/` 目录；它不是实时同步，重新打开时可刷新。普通聊天的本地文件夹不会出现在应用原生侧边栏，ChatGPT 项目归属也不会改变。

## 验证

```sh
python3 -m unittest discover -s tests -v
codex plugin list
```

验证命令检查本地星标、文件夹、时间线顺序及本机面板服务。普通聊天和工作任务的读取需在桌面端通过 `codex-app-tools` 实测。
