# Mag CLI — Claude-Code 风格交互式 TUI 设计

- 日期：2026-06-20
- 状态：设计待复核（实现前）
- 范围：把 `mag` 的交互式 shell 从「plain `rich.Console.input` REPL」升级为模仿 Claude Code 优雅交互的终端 UI
- 关键决策（已与用户确认）：
  - 底层库：**prompt_toolkit**（非 Textual——Claude Code 本身是「滚动历史 + 停靠底部输入框」，不是全屏应用；prompt_toolkit 最贴合，且已是 `questionary` 的传递依赖，现有 497 个 pexpect/`run_once` 测试不必重写）
  - `!` 前缀 = **执行 shell 命令**（Claude Code bash 模式同款）
  - 特性：欢迎面板、`/` 补全菜单、`@` 文件引用、底部状态行、命令历史、多行输入、运行时 spinner/可中断。**不含** OAuth 登录（本期搁置）
  - 实现：**分阶段**，每阶段同步 main
  - 设计哲学：**模仿而非复刻**；遇到不确定的细节，直接运行本机 `claude` 观察其设计与行为

---

## 1. 目标与非目标

### 目标
1. 启动即呈现一个有品牌感的**欢迎面板**（边框、版本、工作区、LLM/状态、Tips、下一步提示、更新提醒）。
2. 单一底部输入框，按首字符**多路复用输入模式**：纯文本对话 / `/` mag 命令 / `!` shell / `@` 文件引用。
3. `/` 与 `@` 有**实时过滤的补全弹出菜单**（方向键选择、带描述、Enter 接受、Esc 取消）。
4. **命令历史**（↑/↓）、**多行输入**（Alt/Option+Enter 换行，Enter 提交）、**可中断**（Esc 取消进行中的阶段，Ctrl+C 两次退出）。
5. 长任务（LLM 调用、求解、写论文）显示 **spinner + 状态动词 + 计时 + “esc 中断”**。
6. 一致的**珊瑚橙主题**与盒绘装饰（圆角面板、`·` 分隔、树形符号），但仅作用于「界面外壳」，命令正文仍保持 `markup=False` 字面输出。
7. **不破坏现有契约**：`InteractiveSession.run_once(text)` 维持不变，仍是所有逻辑入口；非 TTY（管道/CI/pexpect 旧用例）自动回退到原 `console.input` 行为。

### 非目标（本期不做）
- OAuth 登录（用 Claude 作为 LLM）——单独立项。
- LLM 真流式 token-by-token 渲染——架构留口，先做「线程阻塞 + spinner」，流式作为 Phase 4。
- Shift+Tab 权限模式循环（Claude Code 的 plan/auto-accept）——以「工作流阶段徽章」作为 mag 的弱化版替代，循环切换列为 nice-to-have。
- `#` memory 前缀——mag 无对应语义，不做。
- 全屏 alt-screen 应用形态（明确放弃，因为它**反而不像** Claude Code）。

---

## 2. 现状与差距（审计结论）

当前交互实现（`src/mcm_agent/cli_session.py`）：
- 入口：`cli.py` 的 `main()`（`typer`, `invoke_without_command=True`）→ `InteractiveSession.prepare(cwd).run()`。
- 循环：`run()` 先打印 `startup_text()`（纯文本几行），然后 `while True: text = console.input("> ", markup=False)` → `run_once(text)` → `_print(result.message)`。
- 分发：`run_once()` 中 `text.startswith("/")` → 查 `self.commands` 注册表；`/help` 特判；否则 `_handle_natural_language()`（`DialogueGuard` → `generate_chat_reply()`）。
- 渲染：`console.print(message, markup=False, highlight=False)`，无面板/表格/高亮/补全/历史/状态行。
- 命令注册：`build_command_registry()` 返回 `{name: command}`，每个命令有 `.summary`，`run(args, CommandContext)`，`CommandContext(workspace_root, printer, ask)`。

差距（→ 本设计逐项消除）：无欢迎面板、无补全/历史、无状态行/进度、无多行、无 `!`/`@`、无主题化外壳、自然语言回复未做 markdown 渲染、长任务无可中断反馈。

复用资产（已存在，UI 层缺失而已）：
- 命令名 + `summary`（喂 `/` 补全）。
- `load_workspace_state()` 的 phase/init 状态、`load_settings()` 的 LLM provider+model（喂面板与状态行）。
- `SessionStore.read_recent_messages()`（喂历史/上下文）。
- `_make_ask()` 的 TTY 检测（决定是否启用富交互）。
- `run()` 已 `try/except KeyboardInterrupt`（中断语义的落点）。

---

## 3. 设计原则

1. **`run_once` 是唯一真相入口。** 富 UI 只替换「怎么读取一行输入」与「怎么渲染输出外壳」，不改「一行输入如何被处理」。这样命令逻辑、`DialogueGuard`、chat 路径、全部单测零改动。
2. **TTY 才富交互，否则降级。** `stdin.isatty() and stdout.isatty()` 为真时走 prompt_toolkit；否则走旧 `console.input` 直读 + `run_once`（保护 CI、管道、旧 pexpect 用例）。
3. **外壳上色，正文留白。** 主题/盒绘只用于面板、提示符、状态行、补全菜单等「chrome」；命令正文沿用 `markup=False`（保住 `[ok]`/`[missing]` 等字面标记，见历史教训）。
4. **模仿而非复刻。** 复制 Claude Code 的**交互范式**（面板结构、模式前缀、补全行为、中断语义、珊瑚橙基调），用 mag 自己的领域信息填充（工作区/阶段/LLM/题目/数据）。
5. **小而清晰的单元。** 新增独立模块（completer、key-bindings、面板渲染、shell 执行、spinner），各有单一职责与可单测的接口。

---

## 4. 整体架构

### 4.1 新增 / 改动模块

```
src/mcm_agent/
  cli_session.py            (改) run() 分流：TTY → 新 PromptUI；非 TTY → 旧直读循环。run_once 不动。
  tui/                      (新) 交互 UI 层（纯展示与输入，无业务逻辑）
    __init__.py
    app.py                  PromptUI：组合 PromptSession + 渲染，驱动 run_once
    welcome.py              render_welcome_panel(state, settings, version) -> rich.Panel
    theme.py                MAG_THEME（rich.Theme）+ 颜色常量（珊瑚橙等）
    completers.py           SlashCommandCompleter, AtFileCompleter, MagCompleter(合并)
    keybindings.py          build_key_bindings()（Esc/Ctrl+C/历史/多行/?）
    statusbar.py            bottom_toolbar(state, settings) -> 文本（阶段徽章 + LLM + 提示）
    runner.py               run_with_spinner(callable, status_verb)（线程阻塞 + rich.Live spinner + 可中断）
  core/
    shell_exec.py           (新) run_shell(workspace_root, command) -> ShellResult（! 透传，沙箱到工作区）
  cli_commands/
    base.py                 (微调) CommandContext 增加可选 confirm/spinner 钩子（向后兼容，默认 None）
```

### 4.2 控制流（TTY）

```
mag (no args)
  └─ InteractiveSession.prepare(cwd).run()
       ├─ if not (stdin&stdout isatty):  旧循环（console.input → run_once）   [降级路径]
       └─ else: PromptUI(session).loop()
            ├─ 打印 render_welcome_panel(...)              一次
            ├─ while True:
            │    line = PromptSession.prompt(
            │              message=HTML('> '),
            │              completer=MagCompleter(...),
            │              key_bindings=...,
            │              bottom_toolbar=...,
            │              history=FileHistory('.mag/history'),
            │              multiline=False, prompt_continuation=...)
            │    dispatch(line):
            │       ├─ line.startswith('!')  → shell_exec.run_shell(...) → 渲染输出
            │       ├─ 其它（含 '/' 与 '@' 与纯文本） → result = run_once(line)
            │       │     （耗时 stage 由命令内部经 ctx.spinner 包裹，或 chat 走 run_with_spinner）
            │       └─ 渲染 result.message（chat 回复走 markdown 渲染；命令正文 markup=False）
            │    if result.exit_session: break
            └─ patch_stdout() 包裹，避免后台输出撕裂正在编辑的输入行
```

要点：
- `!` 在 UI 层直接处理（shell 不属于 mag 命令域，也不该进 `run_once` 的命令注册表）。其余一切（`/`、`@`、纯文本）仍下沉到 `run_once`，保持单一入口。
- `@` 的处理：补全器把 `@path` 补全成工作区相对路径插入输入行；提交后由 `run_once` → `_handle_natural_language` 识别 `@token` 并把对应文件内容/摘要注入 chat 上下文（见 §9）。
- prompt_toolkit 仅「拥有输入」；**rich 仍是唯一渲染器**（面板、菜单描述用 rich 风格，但补全弹窗本身由 prompt_toolkit 绘制——两者在屏幕上分工：上方滚动区 rich，底部输入区 pt）。

---

## 5. 交互模型 / 输入模式

| 首字符/操作 | 模式 | 行为 | 落点 |
|---|---|---|---|
| 普通文本 | 对话 | 与 mag 讨论题目（LLM） | `run_once` → `_handle_natural_language` |
| `/` | mag 命令 | 弹补全菜单；执行 `/start /api /question …` | `run_once`（slash 分支，不变） |
| `!` | shell | 在工作区执行系统命令并回显 | UI 层 `shell_exec.run_shell` |
| `@` | 文件引用 | 弹文件补全；把文件作为上下文附给下一轮 | 补全器插入 → `run_once` 解析 |
| ↑ / ↓ | 历史 | 调出/回到历史输入 | `PromptSession` history |
| Alt/Option+Enter | 多行 | 输入内插入换行 | key binding |
| Enter | 提交 | 提交当前（可能多行）输入 | — |
| Esc | 中断 | 取消进行中的阶段（spinner 显示「esc 中断」） | `runner.run_with_spinner` |
| Ctrl+C ×2 | 退出 | 第一次清空当前行并提示，再次退出 | key binding |
| `?` | 快捷键帮助 | 弹快捷键浮层（或打印一段帮助） | UI 层 |

模式是**逐行**判定（不像 Claude Code 的 Shift+Tab 粘性权限模式）。阶段徽章（§7.3）只读地反映工作流 phase，不改变输入解释。

---

## 6. 欢迎面板（Welcome Panel）

### 6.1 结构（对位 Claude Code，填 mag 领域信息）

| Claude Code | mag 对应 |
|---|---|
| ✻ Claude Code + 版本 | ✻ Mag · MCM/ICM Modeling Agent + `v0.1.0` |
| Welcome back \<name\> | 依据状态的问候（首次：欢迎；老工作区：欢迎回来） |
| model / billing / org / cwd | **LLM**: deepseek-v4-flash · **Workspace**: test · **Phase**: discussing · **cwd** |
| Tips for getting started | 依据状态的下一步（未 init → 配 /api；未导题 → /question；就绪 → /start） |
| What's new | （可选，低优先）简短变更，指向 `/help` |
| Update available | （打包后才有意义，先留空） |
| 底部 `? for shortcuts · ← for agents` | `/help 命令 · / 菜单 · ! shell · @ 文件 · ? 快捷键` |

### 6.2 Mockup（圆角珊瑚橙边框）

```
╭─ Mag ✻  v0.1.0 ──────────────────────────────────────────────╮
│                                                              │
│   Welcome back!  MCM/ICM Modeling Agent                      │
│                                                              │
│   LLM        deepseek-v4-flash  (DeepSeek)                   │
│   Workspace  test                                           │
│   Phase      discussing                                      │
│   cwd        ~/test                                          │
│                                                              │
│   下一步                                                      │
│   • /start   分析题目并开始讨论                                │
│   • 直接打字  与我讨论建模方向                                  │
│   • /api     查看/配置 API                                    │
│                                                              │
╰──────────────────────────────────────────────────────────────╯
  /help 命令 · / 菜单 · ! shell · @ 文件 · ? 快捷键
> ▍
```

- “下一步”分支：复用现有 `startup_text()` 的状态判断逻辑（`state.init.completed` / `problem_imported`），只是搬进面板。
- LLM 行：`load_settings()` 的 provider+model；未配置时显示「未配置 · 运行 /api」并标黄。
- 渲染：`rich.Panel(..., box=box.ROUNDED, border_style="accent")`，整段打印在滚动区顶部（每会话一次）。

---

## 7. 底部输入区

### 7.1 提示符与输入框
- 提示 `> `（珊瑚橙），prompt_toolkit `PromptSession`。
- `patch_stdout()` 包裹：后台/异步打印不会撕裂正在编辑的输入行。
- 多行：默认单行 Enter 提交；`Alt+Enter` 插入换行进入多行；`prompt_continuation` 显示续行符（如 `… `）。

### 7.2 底部提示行 / 状态栏（bottom_toolbar）
始终可见的一行 dim 文本，左右两段：
```
 deepseek-v4-flash · discussing                    ? 快捷键 · ! shell · @ 文件
```
- 左：LLM 简称 + 当前 phase 徽章。
- 右：核心可发现性提示。
- 由 `statusbar.bottom_toolbar(state, settings)` 生成，每次重绘刷新。

### 7.3 阶段徽章
- mag 的工作流 phase（`init → discussing → script_locked → 运行中 → done`）映射为彩色徽章，作为 Claude Code「Plan/auto-accept 模式徽章」的领域替代。
- 只读反映状态；nice-to-have：Shift+Tab 在「每步确认 ↔ 自动批准（auto_approve）」间切换（mag 已有 `--auto-approve`/`approve-checkpoint` 概念）。

---

## 8. `/` 斜杠补全菜单

- 触发：行首 `/`。
- 数据源：`build_command_registry()` 的 `{name: command.summary}`（已存在）。
- 组件：`SlashCommandCompleter(Completer)`，`get_completions` 产出 `Completion(text="/name", display="/name", display_meta=summary)`。
- 行为：实时模糊过滤；↑/↓ 移动高亮；Enter/Tab 接受并插入；Esc 关闭菜单（不提交）；右侧 dim 显示 `summary`。
- 样式：`Completion` 用 pt 的 `style`/`selected_style`，珊瑚橙高亮行。
- 选中后若命令带子选项（如 `/api`、`/rag <category>`），后续仍走各命令既有的 `ask` 交互（暂不为子参数做二级补全，列 nice-to-have）。

Mockup：
```
> /st▍
  ┌──────────────────────────────────────────────┐
  │ /start    分析题目并开始研究讨论                │
  │ /status   查看当前 workspace 状态              │
  └──────────────────────────────────────────────┘
```

---

## 9. `@` 文件引用

- 触发：输入中出现 `@`。
- 组件：`AtFileCompleter`，遍历 `workspace_root` 下相关文件，**忽略** `work/`、`output/`、`.git/`、`.mag/`、`node_modules` 等噪声目录；对大工作区做缓存+去抖（见风险）。
- 重点候选：`input/problem/*`（题目）、`input/data/*` 与 `data/**`（数据）、`knowledge_base/**`（RAG）、`output/draft/*`、`paper/main.tex`、生成的图。
- 补全：插入 `@<相对路径>` 到输入行（Tab 进入目录、选择文件，对位 Claude Code 的 `@` 行为）。
- 语义：提交后，`run_once` → `_handle_natural_language` 解析行内 `@token`，把对应文件**内容或摘要**注入下一轮 chat 上下文（文本/CSV 截断注入；PDF 走已有解析或仅给路径+元信息）。`generate_chat_reply` 的 prompt 拼装处增加「附加文件」段。
- 退化：找不到文件就当普通文本，不报错。

---

## 10. `!` Shell 透传

- 触发：行首 `!`。
- 组件：`core/shell_exec.py::run_shell(workspace_root, command) -> ShellResult(exit_code, stdout, stderr, duration)`。
- 执行：`subprocess.run(command, shell=True, cwd=workspace_root, capture_output=True, text=True, timeout=…)`。**cwd 固定工作区**。
- 回显：stdout/stderr 以代码块样式打印到滚动区；非零退出码标红并显示 `exit N`。
- 入历史/上下文：命令与（截断的）输出追加进 `SessionStore`，便于后续对话引用（对位 Claude Code「bash 输出回灌上下文」）。
- 安全：
  - 不做命令白名单（这是用户本机的 shell，用户自负）；但**默认超时**（如 120s）防卡死。
  - 文档明确：`!` 在工作区目录下、以当前用户权限运行任意命令；这是便利特性，等同用户自己开个终端。
  - 不把 `!` 命令视作「需确认的破坏性操作」（用户主动输入即授权）；但 `rm -rf` 之类不拦（与系统 shell 行为一致）。

Mockup：
```
> !ls input/data
$ ls input/data
fans.csv  scores.csv
  (exit 0 · 0.02s)
> ▍
```

---

## 11. 运行时状态与进度

- 组件：`runner.run_with_spinner(fn, status_verb, *, interruptible=True)`。
- 机制：把阻塞调用（`generate_chat_reply`、`run_mvp_workflow` 的 stage、solver 代码生成）丢到**工作线程**；主线程用 `rich.Live` 或 pt 的 `ProgressBar` 显示单行：`✻ Solving… (12s · esc 中断)`。
- 状态动词按阶段映射（复用 `workflow_adapter.STAGE_LABELS` 的中文标签：「正在写代码求解」「正在撰写论文」…）。
- 中断：Esc 触发取消标志；对可取消的阶段尽力停止，对不可取消的（in-flight HTTP）标记「放弃结果」并尽快返回（见风险）。`run()` 既有的 KeyboardInterrupt 捕获保留。
- 长工作流：`run_default_workflow(progress=…)` 已支持 progress 回调，将其桥接到本 spinner，逐 stage 刷新文案。

---

## 12. 键位绑定（build_key_bindings）

| 键 | 行为 |
|---|---|
| Enter | 提交输入（多行模式下在续行时由 pt 决定） |
| Alt/Option+Enter | 插入换行（进入/继续多行） |
| ↑ / ↓ | 历史上一条 / 下一条（空行时）；补全菜单内移动高亮 |
| Tab | 接受补全 / `@` 进入目录 |
| Esc | 中断进行中的阶段（无进行中时关闭补全菜单） |
| Ctrl+C | 第一次：清空当前行并提示「再按一次退出」；第二次：退出 |
| Ctrl+D | 退出（空行时） |
| `?` | 行首单独 `?`：显示快捷键帮助浮层/段落 |

（Claude Code 的 Esc-Esc 编辑上一条、Ctrl+G 外部编辑器等列为 nice-to-have，本期不做。）

---

## 13. 主题与渲染

- `tui/theme.py` 定义 `MAG_THEME = rich.Theme({...})`：`accent`（珊瑚橙 `#D97757` 量级）、`success`、`warning`、`error`、`dim`、`phase.*` 徽章色。
- 盒绘：圆角面板 `box.ROUNDED`；资源/输出列表用树形符号 `├── └──`；行内分隔 `·`。
- **关键约束**：`cli_session._print` 对**命令正文**继续 `markup=False, highlight=False`（保字面标记）。主题只作用于「外壳」：欢迎面板、提示符、状态栏、补全菜单、spinner、错误前缀。
- 自然语言/LLM 回复：用 `rich.Markdown` 渲染（标题/列表/代码高亮），区别于命令正文的纯文本。
- 优雅降级：颜色走主题注册表，结构靠盒绘+dim/bold，无背景填充，任意终端可读；`NO_COLOR`/窄终端自适应。

---

## 14. 错误处理与降级

1. **非 TTY**：`prepare/run` 检测到非交互即走旧 `console.input → run_once` 循环，**完全不加载 prompt_toolkit UI**。保护：pytest `CliRunner`、管道、CI、既有 pexpect 行式用例。
2. **prompt_toolkit 不可用/导入失败**：捕获 ImportError → 回退旧循环 + 一行提示。
3. **诚实报错**：延续上一轮修复（chat 真因可见）；shell 非零码、补全异常、文件读不出，都以 dim/red 提示而非静默或误导。
4. **CJK/IME**：验证中文宽字符的光标对齐与补全菜单宽度（风险项，纳入测试）。
5. **后台输出撕裂**：所有非输入打印经 `patch_stdout()`。

---

## 15. 组件边界与文件清单

| 单元 | 职责 | 接口 | 依赖 |
|---|---|---|---|
| `tui/app.py` `PromptUI` | 组合输入循环+渲染，驱动 `run_once` | `PromptUI(session).loop()` | pt, rich, session |
| `tui/welcome.py` | 渲染欢迎面板 | `render_welcome_panel(state, settings, version)->Panel` | rich |
| `tui/theme.py` | 主题与颜色常量 | `MAG_THEME`, `ACCENT` | rich |
| `tui/completers.py` | `/` 与 `@` 补全 | `MagCompleter(commands, workspace_root)` | pt |
| `tui/keybindings.py` | 键位 | `build_key_bindings(state_cbs)->KeyBindings` | pt |
| `tui/statusbar.py` | 底部状态行文本 | `bottom_toolbar(state, settings)->str/FormattedText` | — |
| `tui/runner.py` | spinner+线程+中断 | `run_with_spinner(fn, verb)->result` | rich, threading |
| `core/shell_exec.py` | `!` 执行 | `run_shell(root, cmd)->ShellResult` | subprocess |
| `cli_session.py` | TTY 分流；`run_once` 不变 | `run()` | 上述 tui |

每个单元可独立单测（completer 喂注册表断言候选；welcome 断言关键字段；shell_exec 断言退出码/超时；statusbar 断言阶段文案）。

---

## 16. 测试策略

- **不动**：现有 `run_once` + `CliRunner` + 行式断言全部保留（非 TTY 路径）→ 497 测试零改。
- **新增单元测试**：
  - `SlashCommandCompleter`：给定输入前缀，断言候选与描述。
  - `AtFileCompleter`：临时工作区造文件，断言候选、忽略 `work/output/.git`。
  - `render_welcome_panel`：断言含 LLM/Workspace/Phase/下一步关键字。
  - `shell_exec.run_shell`：`echo`/非零码/超时三用例。
  - `bottom_toolbar`：各 phase 文案。
- **prompt_toolkit 无头测试**：`create_pipe_input()` + `DummyOutput()` 驱动 `PromptSession`，断言补全/历史/键位（pt 官方测试套路）。
- **pexpect pty 冒烟**（薄）：真 pty 起 `mag`，断言欢迎面板出现、`/` 触发菜单、`!echo hi` 回显、Ctrl+C 两次退出。保持精简（pty 易脆）。
- **CJK**：一个含中文输入的 pipe 测试，验证不崩、宽度合理。

---

## 17. 分阶段实施计划

> 每阶段：TDD、绿灯、单独提交、同步 main。

- **Phase 1 — 外壳与基础（低风险，先出观感）**
  - `tui/theme.py` + `tui/welcome.py`：欢迎面板（替换 `startup_text` 的呈现）。
  - 底部提示行（先用现有 `console.input` 也能显示的静态 hint）。
  - `core/shell_exec.py` + `run_once` 之外的 `!` 处理（此阶段可先在旧循环里加 `!` 分支）。
  - 产出：一眼就有 Claude Code 感的面板 + `!` 可用，且不引入 pt 风险。

- **Phase 2 — prompt_toolkit 输入循环（核心）**
  - `tui/app.py` `PromptUI` + TTY 分流；`FileHistory`；多行；Ctrl+C×2 / Esc 键位。
  - `tui/completers.py` 的 `/` 补全 + `tui/statusbar.py` 动态底部栏（LLM+phase）。
  - pt 无头测试 + pexpect 冒烟。

- **Phase 3 — 文件引用与进度**
  - `@` 补全 + `_handle_natural_language` 注入文件上下文。
  - `tui/runner.py` spinner + 可中断；桥接 `run_default_workflow` 进度文案；阶段徽章。
  - chat 回复改 `rich.Markdown` 渲染。

- **Phase 4 — 流式（可选增强）**
  - provider 增 `generate_stream`（httpx `client.stream`），`prompt_async` + `to_thread` + `patch_stdout` 做 token 级渲染。

---

## 18. 风险与缓解（采自研究）

| 风险 | 缓解 |
|---|---|
| 流式需先有 `generate_stream` | 先 spinner+线程阻塞，流式留 Phase 4 |
| live prompt 期间后台打印撕裂 | 一律 `patch_stdout()` |
| Ctrl-C/Esc 无法真正取消 in-flight HTTP | 视作「放弃结果」+ 设超时；UI 立即返回 |
| 大工作区 `@` 补全卡顿 | 缓存+去抖；忽略 `work/output/.git/.mag` |
| 中文/IME 宽字符 | 专测；必要时调列宽 |
| 直接依赖 pt 与 questionary 版本耦合 | 在 `pyproject` 显式 `prompt_toolkit>=3.0.50` 并 pin |
| pexpect pty 测试脆弱 | 冒烟保持极薄，主覆盖仍靠 `run_once` 单测 |

---

## 19. 依赖与版本
- 新增显式依赖：`prompt_toolkit>=3.0.50`（当前已随 `questionary` 间接安装；显式声明以解耦版本）。
- 其余无新增（rich 已在用）。

---

## 20. 未来扩展（明确搁置）
- OAuth 登录（Claude 作 LLM）——单独 spec。
- LLM 真流式渲染（Phase 4 已留口）。
- Shift+Tab 模式循环（auto-approve ↔ 每步确认）。
- `/` 子参数二级补全（如 `/rag <category>`、`@` 跨目录深补全增强）。
- Esc-Esc 编辑上一条、Ctrl+G 外部编辑器。

---

## 附：与 Claude Code 的「模仿映射」速查
| Claude Code | mag 实现 |
|---|---|
| ✻ + 品牌 + 版本面板 | `render_welcome_panel` |
| model/billing/org/cwd | LLM/Workspace/Phase/cwd |
| `/` 命令菜单 | `SlashCommandCompleter`（数据来自现有 registry） |
| `!` bash | `core/shell_exec`（cwd=工作区） |
| `@` 文件 | `AtFileCompleter` + 上下文注入 |
| spinner + status verb + esc | `runner.run_with_spinner`（复用 STAGE_LABELS） |
| 模式徽章（Plan/auto） | 工作流 phase 徽章（+ 可选 auto-approve 切换） |
| `? for shortcuts · …` | `/help · / 菜单 · ! shell · @ 文件 · ? 快捷键` |
| 珊瑚橙主题 + 圆角盒绘 | `MAG_THEME` + `box.ROUNDED`（仅外壳） |
