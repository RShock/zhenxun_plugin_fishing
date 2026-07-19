$ErrorActionPreference = 'Stop'
$env:PYTHONUTF8 = '1'
python .\six_digit_lottery.py --full
Write-Host 'Wrote six_fan_stats.tsv, six_rounded_score_distribution.tsv, six_top_scores.tsv, six_digit_game_design_report.md'
