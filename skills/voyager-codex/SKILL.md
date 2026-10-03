---
name: voyager-codex
description: 在 Codex 工作任务中读取工作任务或普通 ChatGPT 聊天，生成独立时间线查看器、搜索旧消息、加星标或按个人文件夹整理时使用。
---

# Voyager Codex Personal

面向 Codex 工作任务和普通 ChatGPT 聊天的对话导航。使用已安装的 `codex-app-tools` 从 Codex 工作任务读取两类会话；交互时间线是独立的本机页面，消息星标和共同的个人文件夹保存在本地 JSON。此技能不修改原始对话，也不会在普通聊天原生页面添加时间线。

## 时间线与查找

1. 用 `mcp__codex_app__list_threads` 找到目标会话的真实 ID、`kind`（`codex` 或 `chatgpt`）和标题。`codex` 任务有 `hostId` 时传给后续工具；普通聊天通常没有 `hostId`，直接省略。若同名会话无法区分，给出候选项让用户选择。
2. 用 `mcp__codex_app__read_thread` 读取会话，必要时沿 `nextCursor` 分页；每页 `turnLimit` 不超过 10。默认节点纳入所有 `userMessage`；对于 `codex`，只纳入 `phase=final_answer` 的 `agentMessage`；对于 `chatgpt`，纳入 `phase` 为空或 `final_answer` 的 `agentMessage`。若用户消息含附件清单和 `## My request:`，摘录从实际请求开始。保留真实消息 ID、回合顺序、角色。用户要求完整时间线时读取全部页；若页数或单条内容被截断，明确说明。
3. 查找旧内容时，在已读取节点中匹配关键词。需要更早结果时继续翻页，不把“未在当前页找到”说成“整个任务没有”。
4. 用户要求生成独立时间线时，可打开下面的查看器。节点点击会跳到**查看器内**对应消息卡片。若用户明确要求在 Codex/ChatGPT 桌面应用的普通聊天原生页面出现时间线，**不要把此查看器当作完成结果**；说明公开插件接口没有提供当前聊天完整历史及原消息滚动控制。若用户要求打开原任务或聊天，可调用 `mcp__codex_app__navigate_to_codex_page`；它只能打开整个会话，**不能定位到会话内的某条消息**。

## 打开交互时间线

1. 将 `read_thread` 返回的页按读取顺序（最新页在前）保存为 JSON 数组，或保存为 `{"pages": [...]}`。保存前只保留 `thread`、`page`、每个回合的 `id`，以及符合上面筛选规则的消息 `id`、`type`、`phase`、`text`/`content`；不要把工具输出或推理内容写进快照。快照默认放在 `~/.local/share/voyager-codex-personal/timelines/`，目录权限设为 `0700`，文件权限设为 `0600`。使用安全文件写入方式；**不要把消息正文拼入 shell 命令**。快照只留在本机。若用户仅需最近消息，可只保存已读取页，面板会标记还有更早页。
2. 运行 `python3 <plugin-root>/scripts/timeline_viewer.py --snapshot <snapshot-path>`。命令会打印本机 `127.0.0.1` URL 并持续服务；保留其执行会话，关闭后面板将无法访问。服务随机生成不可预测的访问路径，不上传消息。
3. 如工具权限允许，可用 `mcp__codex_app__open_in_codex` 将返回 URL 作为 `browser` 目标打开在**当前 Codex 工作任务**的面板中；这仍是独立查看器，不会出现在目标普通聊天的原生页面。如果面板不能打开，给出本机 URL 并在回复中列出文字时间线，明确说明视觉验证状态。若浏览器安全检查拒绝访问，不得换工具绕过。
4. 面板星标和文件夹操作调用已有 `scripts/bookmarks.py`，与文字工作流共用 `stars.json`。重新读取或切换会话时生成新快照并启动相应面板。不要把快照当作实时同步。

## 消息星标

先通过 `read_thread` 确认目标消息的真实 ID，再运行插件中的 `scripts/bookmarks.py`。传入 ID 时仅使用从工具返回且符合 `[A-Za-z0-9_-]+` 的值；不要把消息正文拼进 shell 命令。

```text
python3 <plugin-root>/scripts/bookmarks.py star --thread-id <thread-id> --message-id <message-id>
python3 <plugin-root>/scripts/bookmarks.py unstar --thread-id <thread-id> --message-id <message-id>
python3 <plugin-root>/scripts/bookmarks.py list --thread-id <thread-id>
```

工作任务与普通聊天都使用同一脚本。脚本默认把星标存于 `~/.local/share/voyager-codex-personal/stars.json`；也可通过 `XDG_DATA_HOME` 更改位置。列星标时，用 `read_thread` 补出对应消息的摘要；若原消息不可读取，保留 ID 并说明。不要把星标描述成应用原生消息星标。

## 个人文件夹与侧边栏

对两类会话统一使用本地文件夹记录。先核对真实会话 ID 和 `kind`，再运行：

```text
python3 <plugin-root>/scripts/bookmarks.py folder-set --thread-id <thread-id> --kind <codex|chatgpt> --folder <name>
python3 <plugin-root>/scripts/bookmarks.py folder-list --folder <name>
python3 <plugin-root>/scripts/bookmarks.py folder-remove --thread-id <thread-id>
```

用户提供的文件夹名必须安全地作为单个 shell 参数传入，不能直接拼接未经转义的文本。本地文件夹只记录分类，不改变应用侧边栏、ChatGPT 项目归属或会话正文。

若用户另外要求在 Codex 侧边栏显示任务分区，再用 `mcp__codex_app__list_threads`、`mcp__codex_app__create_sidebar_section` 和 `mcp__codex_app__move_thread_to_sidebar_section` 操作 `kind=codex` 的任务。此工具没有普通 ChatGPT 聊天移动能力，不能把本地文件夹说成原生侧边栏同步。

## 边界

- 这是一套由 Codex 调用的工作流。可从 Codex 工作任务读取并整理普通 ChatGPT 聊天，生成独立本机查看器，但不能让普通聊天原生页面自动出现时间线或悬浮侧栏。用户请求原生页面功能时必须明确报告这一限制。
- 会话读取和打开依赖桌面端的 `codex-app-tools`。独立 Codex CLI 会话可能没有这些工具；若不可用，说明缺失能力，不要读取 Codex 内部数据库或模拟成功。
- 本地 JSON 保存消息 ID、个人文件夹和可选元数据，不同步、不上传。
