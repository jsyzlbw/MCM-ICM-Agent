from mcm_agent.agents.problem_understanding import ProblemUnderstandingAgent


def test_strip_preamble_removes_chatter_before_first_heading() -> None:
    report = (
        "好的，作为一名资深数学建模竞赛顾问，我将为您撰写报告。\n\n"
        "# 题意理解报告\n## 题目背景\n本题研究 DWTS 投票公平性。\n"
    )
    cleaned = ProblemUnderstandingAgent._strip_preamble(report)
    assert cleaned.startswith("# 题意理解报告")
    assert "资深数学建模竞赛顾问" not in cleaned


def test_strip_preamble_handles_code_fence() -> None:
    report = "```markdown\n# 题意理解报告\n## 题目背景\n内容。\n```"
    cleaned = ProblemUnderstandingAgent._strip_preamble(report)
    assert cleaned.startswith("# 题意理解报告")
    assert "```" not in cleaned


def test_strip_preamble_passthrough_when_already_clean() -> None:
    report = "# 题意理解报告\n## 题目背景\n内容。"
    assert ProblemUnderstandingAgent._strip_preamble(report) == report
