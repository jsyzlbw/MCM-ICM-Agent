# 07. 审查与修订设计

## 1. 目标

用户拿到初稿后，通常会继续提出修改意见。Mag 必须支持循环修订，而不是一次性生成后结束。

修订流程：

```text
用户反馈
  -> Agent 理解反馈
  -> 生成修订脚本
  -> 用户确认
  -> 局部重跑受影响阶段
  -> 重新验证
  -> 重新生成论文或局部章节
  -> 输出新草稿
```

## 2. 用户反馈形式

用户可以自然语言反馈：

```text
第二问的模型太简单，换成网络流模型。
图 3 看不清，颜色和标注要重做。
摘要写得更像竞赛论文。
```

Mag 需要识别：

- 反馈影响哪个子问题。
- 影响模型、数据、图表、写作还是排版。
- 是否需要重新求解。
- 是否需要重新检查数据来源。
- 是否需要用户确认新的研究脚本。

## 3. 修订脚本

每次重大修改都先生成 revision script：

```text
Revision plan:

1. Replace Q2 baseline with network-flow formulation.
2. Re-run solver for Q2.
3. Update evidence registry.
4. Regenerate Figure 3.
5. Rewrite model and result sections.
6. Re-run validation and final review.

Proceed? [y/N]:
```

保存：

```text
work/revisions/revision_001.md
work/revisions/revision_001.json
```

## 4. 修订类型

| 类型 | 是否需要用户确认 | 是否需要重跑模型 |
|---|---|---|
| 文案润色 | 可自动 | 否 |
| 图表样式调整 | 可自动 | 否 |
| 补充解释 | 可自动 | 否 |
| 模型路线改变 | 必须确认 | 是 |
| 数据来源改变 | 必须确认 | 可能 |
| 结论数字改变 | 必须确认 | 是 |
| 论文结构大改 | 必须确认 | 可能 |

## 5. 局部重跑

Mag 应尽量局部重跑：

- 只改图表：从 visualization 后重跑。
- 改模型：从 modeling 或 solver 后重跑。
- 改数据：从 search/data 或 EDA 后重跑。
- 改文案：从 paper writer 后重跑。

但任何会影响 claim 的修改，都必须重新跑 evidence binding 和 final review。

## 6. 版本记录

每轮修订输出：

```text
output/draft/revision_001/main.pdf
output/draft/revision_001/change_summary.md
output/draft/revision_001/reviewer_report.md
```

`change_summary.md` 说明：

- 用户提出了什么。
- Agent 改了什么。
- 哪些阶段重跑。
- 哪些结论变化。
- 是否有新风险。

## 7. 停止条件

修订循环在以下情况结束：

- 用户接受最终稿。
- final gate 通过并生成提交包。
- 出现无法自动解决的 blocker。
- 用户决定停止。

## 8. Blocker 处理

如果遇到 blocker：

```text
当前无法继续自动修订：

原因：缺少可靠数据来源
影响：第二问结论无法支撑

可选操作：
  1. 上传数据
  2. 配置推荐 API
  3. 修改研究脚本
  4. 保留为人工待处理项
```

Mag 必须清楚告诉用户为什么阻塞，不能只输出失败堆栈。

