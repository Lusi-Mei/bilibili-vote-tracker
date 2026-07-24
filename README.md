# 奥特曼60周年光之创想季 — 投票数据追踪

[![Vote Tracker](https://github.com/Lusi-Mei/bilibili-vote-tracker/actions/workflows/tracker.yml/badge.svg)](https://github.com/Lusi-Mei/bilibili-vote-tracker/actions/workflows/tracker.yml)

**实时仪表盘**: https://lusi-mei.github.io/bilibili-vote-tracker/

Bilibili "奥特曼60周年光之创想季" 投票活动的实时数据采集与分析。

## 数据文件

| 文件 | 说明 |
|------|------|
| `latest.json` | 最新一次抓取的完整数据 |
| `history.json` | 时间序列票数（每 30 秒一个点，保留 48h） |
| `vote_data.csv` | 最新排名 CSV 快照 |
| `index.html` | 实时仪表盘（GitHub Pages 托管，自动拉取原始数据渲染） |

## 运行方式

### CI（推荐）

GitHub Actions 每 6 小时启动一个会话，内部每 5 秒轮询 API，自动 git push 持久化。

### 本地

```bash
python3 vote_tracker.py              # 启动追踪（每 5 秒）
python3 vote_tracker.py --once       # 单次抓取
python3 vote_tracker.py --server     # 服务器模式（带 git 自动推送）
python3 vote_tracker.py --report     # 生成 HTML 报表
python3 vote_tracker.py --export-csv # 导出 CSV
```

防止合盖休眠：

```bash
caffeinate -i python3 vote_tracker.py
```

## 分析结论概要

- **种子票**：排名 5-12 的角色初始票数高度一致（≈771k，极差 35 票，方差系数 0.0015%），表明存在平台统一种子初始化。
- **匀速增长**：同梯队角色增速高度同步，赛罗奥特曼的增量标准差（σ=5.6）仅为同伴平均值的一半，呈现机械式匀速特征。
- **包围策略无效**：所谓"迪迦+赛罗前后"的投票策略在统计数据中无相关性支撑，邻居间增量相关系数接近零。
