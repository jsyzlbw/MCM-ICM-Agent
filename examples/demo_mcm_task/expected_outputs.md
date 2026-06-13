# Expected Outputs

Run this demo with:

```bash
mcm-agent run .demo_workspace \
  --problem-file examples/demo_mcm_task/problem.md \
  --attachment examples/demo_mcm_task/attachments/city_flood_indicators.csv \
  --user-idea-file examples/demo_mcm_task/user_idea.md \
  --supervisor-skills-dir examples/demo_mcm_task/skills \
  --auto-approve
```

Expected key artifacts:

- `reports/problem_understanding.md`
- `reports/model_decision.md`
- `reports/experiment_plan.md`
- `results/model_metrics.json`
- `results/evidence_registry.json`
- `figures/fig_q1_prediction.pdf`
- `figures/fig_q1_prediction.svg`
- `review/figure_quality_report.md`
- `review/reviewer_report.md`
- `paper/main.tex`
- `final_submission/AI_use_report.md`

This demo uses local attachments and fake/default providers by design, so it is safe for
CI and development runs. Real provider connectivity should be checked separately with
`scripts/smoke_providers.py`.
