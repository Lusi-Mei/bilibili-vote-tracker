#!/usr/bin/env python3
"""
奥特曼60周年光之创想季 — 投票数据实时追踪
Bilibili Vote Tracker

Usage:
    python3 vote_tracker.py              # 启动追踪
    python3 vote_tracker.py --once       # 单次抓取
    python3 vote_tracker.py --export-csv # 导出 CSV
    python3 vote_tracker.py --report     # 生成 HTML 报表
"""

import json
import time
import os
import csv
import signal
import sys
import subprocess
from datetime import datetime, timezone, timedelta
from urllib.request import Request, urlopen
from urllib.error import URLError

# ── Config ──────────────────────────────────────────────
VOTE_ID = "23ERA1wloghvx0200"
GROUP_ID = "24ERA1wloghvt0g00"
API_URL = "https://api.bilibili.com/x/activity_components/vote_new/rank"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
    "Referer": "https://www.bilibili.com/blackboard/era/yPzdu1cQxeYNK7dd.html",
    "Origin": "https://www.bilibili.com",
}
DATA_DIR = os.path.dirname(os.path.abspath(__file__))
SNAPSHOTS_DIR = os.path.join(DATA_DIR, "snapshots")
LATEST_FILE = os.path.join(DATA_DIR, "latest.json")
HISTORY_FILE = os.path.join(DATA_DIR, "history.json")
CSV_FILE = os.path.join(DATA_DIR, "vote_data.csv")
REPORT_FILE = os.path.join(DATA_DIR, "report.html")
POLL_INTERVAL = 5  # seconds
HISTORY_INTERVAL = 6  # save history every N polls (6*5=30s)
MAX_ITEMS = 40  # top N characters
MAX_HISTORY_POINTS = 5760  # 48h at 30s intervals

TZ = timezone(timedelta(hours=8))  # CST

CHART_COLORS = [
    "#ff6b35", "#4ecdc4", "#ffe66d", "#a29bfe", "#fd79a8",
    "#00cec9", "#fdcb6e", "#6c5ce7", "#e17055", "#81ecec",
    "#fab1a0", "#55efc4", "#74b9ff", "#ff7675", "#dfe6e9",
    "#636e72", "#ff9ff3", "#54a0ff", "#5f27cd", "#01a3a4",
    "#e056a0", "#ffa502", "#7bed9f", "#70a1ff", "#ff6348",
    "#2ed573", "#1e90ff", "#ff4757", "#2bcbba", "#45aaf2",
    "#a55eea", "#26de81", "#fc5c65", "#4b7bec", "#fd9644",
    "#20bf6b", "#8854d0", "#eb3b5a", "#0fb9b1", "#3867d6",
]


def fetch_data():
    url = f"{API_URL}?vote_id={VOTE_ID}&group_id={GROUP_ID}&ps={MAX_ITEMS}"
    req = Request(url, headers=HEADERS)
    with urlopen(req, timeout=10) as resp:
        body = json.loads(resp.read().decode("utf-8"))
    if body["code"] != 0:
        raise RuntimeError(f"API error: {body.get('message', 'unknown')}")
    data = body["data"]
    return {
        "vote_id": data["vote_id"],
        "group_id": data["group_id"],
        "remain_vote": data["remain_vote"],
        "items": [
            {
                "rank": i + 1,
                "item_id": it["item_id"],
                "title": it["item"]["title"],
                "vote": it["vote"],
                "pic": it["item"]["pic"],
            }
            for i, it in enumerate(data["items"])
        ],
    }


def load_previous():
    if os.path.exists(LATEST_FILE):
        with open(LATEST_FILE) as f:
            return json.load(f)
    return None


def load_history():
    if os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE) as f:
            return json.load(f)
    return {"timestamps": [], "items": {}}


def save_history(data, timestamp):
    hist = load_history()
    ts_str = timestamp.strftime("%m/%d %H:%M")

    hist["timestamps"].append(ts_str)

    for it in data["items"]:
        iid = it["item_id"]
        if iid not in hist["items"]:
            hist["items"][iid] = {"title": it["title"], "votes": []}
        hist["items"][iid]["votes"].append(it["vote"])

    if len(hist["timestamps"]) > MAX_HISTORY_POINTS:
        trim = len(hist["timestamps"]) - MAX_HISTORY_POINTS
        hist["timestamps"] = hist["timestamps"][trim:]
        for iid in hist["items"]:
            hist["items"][iid]["votes"] = hist["items"][iid]["votes"][trim:]

    with open(HISTORY_FILE, "w") as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)


def save_snapshot(data, timestamp):
    os.makedirs(SNAPSHOTS_DIR, exist_ok=True)
    filename = timestamp.strftime("snapshot_%Y%m%d_%H%M%S.json")
    with open(os.path.join(SNAPSHOTS_DIR, filename), "w") as f:
        json.dump({"timestamp": timestamp.isoformat(), **data}, f, ensure_ascii=False, indent=2)
    with open(LATEST_FILE, "w") as f:
        json.dump({"timestamp": timestamp.isoformat(), **data}, f, ensure_ascii=False, indent=2)


def build_index(prev):
    if not prev:
        return {}
    return {it["item_id"]: {"rank": it["rank"], "vote": it["vote"]} for it in prev["items"]}


def print_update(data, prev_data):
    now = datetime.now(TZ)
    prev_index = build_index(prev_data)

    print()
    print(f"┌{'─' * 78}┐")
    print(f"│  奥特曼60周年光之创想季 — 投票实时排名  {now.strftime('%Y-%m-%d %H:%M:%S')}     │")
    print(f"├{'─' * 78}┤")
    print(f"│ {'排名':<5} {'角色':<18} {'票数':>14} {'变化':>12} {'排名变化':>10} │")
    print(f"├{'─' * 78}┤")

    total_votes = sum(it["vote"] for it in data["items"])
    max_show = min(20, len(data["items"]))

    for it in data["items"][:max_show]:
        rank, title, votes, item_id = it["rank"], it["title"], it["vote"], it["item_id"]
        delta_str, rank_str = "", ""

        if item_id in prev_index:
            prev_info = prev_index[item_id]
            delta = votes - prev_info["vote"]
            delta_str = f"+{delta:,}" if delta > 0 else (f"{delta:,}" if delta < 0 else "—")
            rank_delta = prev_info["rank"] - rank
            rank_str = f"↑{rank_delta}" if rank_delta > 0 else (f"↓{abs(rank_delta)}" if rank_delta < 0 else "—")
        else:
            delta_str, rank_str = "NEW", "NEW"

        print(f"│ {rank:<5} {title:<18} {votes:>14,} {delta_str:>12} {rank_str:>10} │")

    print(f"├{'─' * 78}┤")
    print(f"│  总票数: {total_votes:,}  前{max_show}/{len(data['items'])}名                                           │")
    print(f"└{'─' * 78}┘")


def export_csv():
    prev = load_previous()
    if not prev:
        print("暂无数据，请先运行追踪。")
        return
    with open(CSV_FILE, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.writer(f)
        writer.writerow(["排名", "角色", "票数", "item_id", "更新时间", "图片URL"])
        for it in prev["items"]:
            writer.writerow([
                it["rank"], it["title"], it["vote"], it["item_id"], prev["timestamp"],
                f"https:{it['pic']}" if not it["pic"].startswith("http") else it["pic"],
            ])
    print(f"CSV 已导出到: {CSV_FILE}")


def generate_report():
    prev = load_previous()
    hist = load_history()
    if not prev:
        print("暂无数据，请先运行追踪。")
        return

    items = prev["items"]
    total_votes = sum(it["vote"] for it in items)
    max_votes = items[0]["vote"] if items else 1
    ts = prev["timestamp"]
    timestamps_json = json.dumps(hist.get("timestamps", []), ensure_ascii=False)

    # 所有角色图表数据
    all_datasets = []
    for i, it in enumerate(items):
        iid = it["item_id"]
        votes = hist.get("items", {}).get(iid, {}).get("votes", [])
        color = CHART_COLORS[i % len(CHART_COLORS)]
        all_datasets.append({
            "id": iid,
            "label": it["title"],
            "rank": it["rank"],
            "votes_now": it["vote"],
            "data": votes,
            "borderColor": color,
            "backgroundColor": color + "44",
            "borderWidth": 2,
            "pointRadius": 0,
            "pointHoverRadius": 4,
            "tension": 0.2,
            "hidden": False,  # 默认全部显示
        })

    all_datasets_json = json.dumps(all_datasets, ensure_ascii=False)

    # 排行榜表格
    rows_html = ""
    for it in items:
        pct = it["vote"] / total_votes * 100 if total_votes > 0 else 0
        bar_pct = it["vote"] / max_votes * 100 if max_votes > 0 else 0
        rows_html += f"""
        <tr>
            <td class="rank">{it['rank']}</td>
            <td class="title">{it['title']}</td>
            <td class="votes">{it['vote']:,}</td>
            <td class="pct">{pct:.1f}%</td>
            <td class="bar-cell">
                <div class="bar" style="width:{bar_pct:.1f}%"></div>
            </td>
        </tr>"""

    # 复选框列表
    checkbox_html = ""
    row_groups = [items[i:i+5] for i in range(0, len(items), 5)]
    for group in row_groups:
        checkbox_html += '<div class="cb-row">'
        for it in group:
            checked = "checked"
            color = CHART_COLORS[(it["rank"] - 1) % len(CHART_COLORS)]
            checkbox_html += f"""
            <label class="cb-label" style="--c:{color}">
                <input type="checkbox" class="char-cb" data-id="{it['item_id']}" {checked}>
                <span class="cb-name">{it['rank']}. {it['title']}</span>
            </label>"""
        checkbox_html += '</div>'

    html = f"""<!DOCTYPE html>
<html lang="zh">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>奥特曼60周年光之创想季 — 投票排名</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.7/dist/chart.umd.min.js"></script>
<style>
* {{ margin:0; padding:0; box-sizing:border-box; }}
body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif; background: #0a0a1a; color: #e0e0e0; min-height: 100vh; }}
.header {{ text-align: center; padding: 25px 0 8px; background: linear-gradient(180deg, #1a1a3e, #0a0a1a); }}
.header h1 {{ font-size: 26px; color: #ff6b35; letter-spacing: 2px; }}
.header .sub {{ color: #888; margin-top: 6px; font-size: 13px; }}
.header .total {{ color: #ff6b35; font-weight: bold; }}
.container {{ max-width: 1200px; margin: 0 auto; padding: 20px; }}

/* Checkbox area */
.filter-section {{ margin-bottom: 15px; }}
.filter-section h3 {{ color: #ccc; font-size: 14px; margin-bottom: 10px; padding-left: 10px; border-left: 3px solid #ff6b35; }}
.filter-bar {{ display: flex; gap: 8px; margin-bottom: 10px; flex-wrap: wrap; align-items: center; }}
.filter-bar button {{ padding: 5px 14px; border-radius: 5px; cursor: pointer; font-size: 12px; border: 1px solid #444; background: transparent; color: #aaa; }}
.filter-bar button:hover {{ border-color: #ff6b35; color: #ff6b35; }}
.filter-bar button.active {{ background: #ff6b35; color: #fff; border-color: #ff6b35; }}
.cb-grid {{ background: #111128; border-radius: 10px; padding: 12px 15px; border: 1px solid #1a1a3e; }}
.cb-row {{ display: flex; flex-wrap: wrap; gap: 6px 12px; margin-bottom: 4px; }}
.cb-row:last-child {{ margin-bottom: 0; }}
.cb-label {{ display: inline-flex; align-items: center; gap: 4px; cursor: pointer; font-size: 12px; color: #999; padding: 3px 8px; border-radius: 4px; border: 1px solid transparent; transition: all 0.15s; user-select: none; white-space: nowrap; }}
.cb-label:hover {{ background: rgba(255,255,255,0.05); border-color: #333; }}
.cb-label input {{ display: none; }}
.cb-label .cb-dot {{ width: 8px; height: 8px; border-radius: 50%; background: var(--c); opacity: 0.3; flex-shrink: 0; transition: opacity 0.15s; }}
.cb-label input:checked + .cb-dot {{ opacity: 1; box-shadow: 0 0 6px var(--c); }}
.cb-label input:checked ~ .cb-name {{ color: #ddd; }}
.cb-name {{ font-size: 12px; }}

/* Chart */
.chart-section {{ margin-bottom: 20px; }}
.chart-section h3 {{ color: #ccc; font-size: 14px; margin-bottom: 8px; padding-left: 10px; border-left: 3px solid #ff6b35; display: flex; align-items: center; gap: 10px; }}
.chart-section h3 .count {{ color: #888; font-size: 12px; font-weight: normal; }}
.chart-wrap {{ background: #111128; border-radius: 12px; padding: 20px; border: 1px solid #1a1a3e; position: relative; min-height: 450px; }}
.chart-wrap canvas {{ width: 100% !important; }}

/* Table */
table {{ width: 100%; border-collapse: collapse; }}
th {{ padding: 10px; text-align: left; color: #aaa; font-weight: 500; font-size: 11px; border-bottom: 1px solid #333; }}
td {{ padding: 8px 10px; border-bottom: 1px solid #1a1a2e; font-size: 13px; }}
tr:hover {{ background: rgba(255,255,255,0.03); }}
.rank {{ width: 36px; text-align: center; font-weight: bold; font-size: 14px; }}
tr:nth-child(1) .rank {{ color: #ffd700; font-size: 18px; }}
tr:nth-child(2) .rank {{ color: #c0c0c0; font-size: 16px; }}
tr:nth-child(3) .rank {{ color: #cd7f32; font-size: 15px; }}
.title {{ font-weight: 500; }}
.votes {{ font-weight: bold; color: #ff6b35; min-width: 80px; }}
.pct {{ color: #888; font-size: 12px; min-width: 50px; }}
.bar-cell {{ min-width: 120px; }}
.bar {{ height: 5px; background: linear-gradient(90deg, #ff6b35, #ff9f43); border-radius: 3px; }}

.footer {{ text-align: center; padding: 20px; color: #555; font-size: 12px; margin-top: 20px; }}
.refresh {{ display: flex; justify-content: center; gap: 12px; margin: 15px 0; }}
.refresh button {{ background: #ff6b35; color: #fff; border: none; padding: 8px 24px; border-radius: 6px; cursor: pointer; font-size: 14px; }}
.refresh button:hover {{ background: #e85d2c; }}
.refresh .auto {{ font-size: 12px; color: #888; align-self: center; }}

/* Tooltip */
.tooltip-row {{ display: flex; align-items: center; gap: 6px; margin: 2px 0; }}
.tooltip-dot {{ width: 10px; height: 10px; border-radius: 50%; flex-shrink: 0; }}
</style>
</head>
<body>
<div class="header">
    <h1>奥特曼60周年光之创想季</h1>
    <p class="sub">投票实时排名 · 总票数: <span class="total">{total_votes:,}</span> · {len(items)} 位角色 · 更新于 {ts}</p>
</div>
<div class="container">

    <!-- 选择区域 -->
    <div class="filter-section">
        <h3>🔍 选择要显示的角色（勾选后图表自动更新）</h3>
        <div class="filter-bar">
            <button onclick="selectTop(3)">前三名</button>
            <button onclick="selectTop(5)">前五名</button>
            <button onclick="selectTop(10)">前十名</button>
            <button onclick="selectTop(20)">前二十名</button>
            <button onclick="selectTop({len(items)})" class="active">全部</button>
            <button onclick="clearAll()">清除</button>
            <span style="margin-left: auto; font-size: 12px; color: #666;" id="selectedCount">已选 {len(items)} 项</span>
        </div>
        <div class="cb-grid">
            {checkbox_html}
        </div>
    </div>

    <!-- 图表 -->
    <div class="chart-section">
        <h3>📈 票数趋势 <span class="count">（横轴: 最近48小时，选中角色的 Y 轴自动适配）</span></h3>
        <div class="chart-wrap">
            <canvas id="chartMain"></canvas>
        </div>
    </div>

    <!-- 排行榜 -->
    <div class="chart-section">
        <h3>📋 最新排名（前{len(items)}位）</h3>
    </div>
    <table>
        <thead><tr><th>#</th><th>角色</th><th>票数</th><th>占比</th><th>对比第1名</th></tr></thead>
        <tbody>{rows_html}</tbody>
    </table>

    <div class="refresh">
        <button onclick="location.reload()">刷新数据</button>
        <span class="auto" id="countdown">5s 后自动刷新</span>
    </div>
</div>
<div class="footer">数据来源: Bilibili · 自动追踪 · {ts}</div>

<script>
const timestamps = {timestamps_json};
const allDatasets = {all_datasets_json};

// 从 localStorage 恢复选择
function getSavedSelection() {{
    try {{ return JSON.parse(localStorage.getItem('voteChartSelection') || '[]'); }} catch(e) {{ return []; }}
}}
function saveSelection(ids) {{
    localStorage.setItem('voteChartSelection', JSON.stringify(ids));
}}

const saved = getSavedSelection();
const cbs = document.querySelectorAll('.char-cb');
if (saved.length > 0) {{
    cbs.forEach(cb => cb.checked = saved.includes(cb.dataset.id));
}} else {{
    cbs.forEach(cb => cb.checked = true);
}}

// 初始化隐藏状态
allDatasets.forEach(ds => {{
    const cb = document.querySelector(`.char-cb[data-id="${{ds.id}}"]`);
    ds.hidden = cb ? !cb.checked : true;
}});

// 创建图表
const ctx = document.getElementById('chartMain').getContext('2d');

// 构建初始可见数据集
function getVisibleDatasets() {{
    return allDatasets.map((ds, i) => {{
        const cb = document.querySelector(`.char-cb[data-id="${{ds.id}}"]`);
        const visible = cb ? cb.checked : false;
        return {{ ...ds, hidden: !visible, borderWidth: visible ? (i < 3 ? 2.5 : 1.5) : 0 }};
    }});
}}

const chart = new Chart(ctx, {{
    type: 'line',
    data: {{
        labels: timestamps,
        datasets: getVisibleDatasets()
    }},
    options: {{
        responsive: true,
        maintainAspectRatio: false,
        animation: {{ duration: 400 }},
        interaction: {{ intersect: false, mode: 'nearest' }},
        layout: {{ padding: {{ right: 20 }} }},
        plugins: {{
            legend: {{
                position: 'top',
                labels: {{
                    color: '#aaa',
                    usePointStyle: true,
                    padding: 12,
                    font: {{ size: 11 }},
                    filter: item => !item.hidden,
                    generateLabels: function(chart) {{
                        const datasets = chart.data.datasets;
                        return datasets.map((ds, i) => ({{
                            text: ds.label,
                            fillStyle: ds.borderColor,
                            strokeStyle: ds.borderColor,
                            lineWidth: ds.borderWidth,
                            hidden: ds.hidden,
                            index: i,
                            pointStyle: 'circle',
                            fontColor: ds.hidden ? '#444' : '#aaa'
                        }}));
                    }}
                }}
            }},
            tooltip: {{
                backgroundColor: '#1a1a3e',
                titleColor: '#fff',
                bodyColor: '#ddd',
                borderColor: '#333',
                borderWidth: 1,
                callbacks: {{
                    label: function(ctx) {{
                        return (ctx.dataset.label || '') + ': ' + ctx.parsed.y.toLocaleString() + ' 票';
                    }}
                }}
            }}
        }},
        scales: {{
            x: {{
                ticks: {{ color: '#666', maxTicksLimit: 15, font: {{ size: 10 }} }},
                grid: {{ color: '#1a1a2e' }}
            }},
            y: {{
                ticks: {{ 
                    color: '#666',
                    font: {{ size: 10 }},
                    callback: v => v.toLocaleString()
                }},
                grid: {{ color: '#1a1a2e' }}
            }}
        }}
    }}
}});

// 修复 Canvas 高度
function fixCanvasSize() {{
    const wrap = document.querySelector('.chart-wrap');
    const visibleCount = allDatasets.filter(d => {{
        const cb = document.querySelector(`.char-cb[data-id="${{d.id}}"]`);
        return cb && cb.checked;
    }}).length;
    wrap.style.minHeight = Math.max(300, Math.min(visibleCount * 50 + 250, 800)) + 'px';
    chart.resize();
}}

// Checkbox 交互
cbs.forEach(cb => {{
    cb.addEventListener('change', () => {{
        const ds = allDatasets.find(d => d.id === cb.dataset.id);
        if (ds) {{
            ds.hidden = !cb.checked;
            const ci = allDatasets.indexOf(ds);
            if (chart.data.datasets[ci]) {{
                chart.data.datasets[ci].hidden = !cb.checked;
            }}
        }}
        saveSelection(Array.from(cbs).filter(c => c.checked).map(c => c.dataset.id));
        updateCount();
        fixCanvasSize();
        chart.update();
    }});
}});

function updateCount() {{
    const n = Array.from(cbs).filter(c => c.checked).length;
    document.getElementById('selectedCount').textContent = '已选 ' + n + ' 项';
}}

function selectTop(n) {{
    cbs.forEach((cb, i) => cb.checked = i < n);
    allDatasets.forEach((ds, i) => {{
        ds.hidden = i >= n;
        if (chart.data.datasets[i]) chart.data.datasets[i].hidden = i >= n;
    }});
    saveSelection(Array.from(cbs).filter(c => c.checked).map(c => c.dataset.id));
    updateCount();
    fixCanvasSize();
    chart.update();
    document.querySelectorAll('.filter-bar button').forEach(b => b.classList.remove('active'));
    document.querySelector(`.filter-bar button:nth-child(${{Math.min(n, 5) + (n === {len(items)} ? 4 : (n > 20 ? 3 : (n > 10 ? 2 : (n > 5 ? 1 : 0))))}})`);
}}

function clearAll() {{
    cbs.forEach(cb => cb.checked = false);
    allDatasets.forEach((ds, i) => {{ ds.hidden = true; if (chart.data.datasets[i]) chart.data.datasets[i].hidden = true; }});
    saveSelection([]);
    updateCount();
    fixCanvasSize();
    chart.update();
}}

updateCount();
fixCanvasSize();

// 自动刷新
let sec = 5;
setInterval(() => {{
    sec--;
    document.getElementById('countdown').textContent = sec + 's 后自动刷新';
    if (sec <= 0) location.reload();
}}, 1000);
</script>
</body>
</html>"""

    with open(REPORT_FILE, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"HTML 报表已生成: {REPORT_FILE}")


def main_loop():
    print("=" * 80)
    print("  奥特曼60周年光之创想季 — 投票数据实时追踪")
    print(f"  刷新间隔: {POLL_INTERVAL}s  |  角色数: {MAX_ITEMS}  |  Ctrl+C 退出")
    print(f"  数据目录: {SNAPSHOTS_DIR}")
    print(f"  历史记录: {HISTORY_INTERVAL*POLL_INTERVAL}s 间隔, 保留 {MAX_HISTORY_POINTS} 点 ({MAX_HISTORY_POINTS*HISTORY_INTERVAL*POLL_INTERVAL//3600}h)")
    print("=" * 80)

    signal.signal(signal.SIGINT, lambda sig, frame: graceful_exit())
    prev = load_previous()
    fetch_count = 0

    while True:
        try:
            now = datetime.now(TZ)
            data = fetch_data()
            save_snapshot(data, now)
            fetch_count += 1
            should_save_history = (fetch_count % HISTORY_INTERVAL == 0)
            if should_save_history:
                save_history(data, now)

            if prev:
                print_update(data, prev)
            else:
                print_update(data, data)

            prev = data

            if fetch_count % 6 == 0 or fetch_count == 0:
                generate_report()

            export_csv()

            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            break
        except Exception as e:
            ts = datetime.now(TZ).strftime("%H:%M:%S")
            print(f"\n[{ts}] ⚠ 请求失败: {e}，{POLL_INTERVAL}s 后重试...")
            time.sleep(POLL_INTERVAL)


def graceful_exit():
    print("\n\n追踪结束。")
    export_csv()
    generate_report()
    print("数据已保存。")
    sys.exit(0)


def server_loop():
    run_seconds = int(os.environ.get("SERVER_DURATION", "21000"))
    push_interval = int(os.environ.get("PUSH_INTERVAL", "12"))
    branch = os.environ.get("GIT_BRANCH", "master")

    print(f"[server] duration={run_seconds}s, push_every={push_interval * POLL_INTERVAL}s, branch={branch}")

    def git_push():
        try:
            subprocess.run(
                ["git", "add", "history.json", "latest.json", "vote_data.csv", "report.html"],
                cwd=DATA_DIR, capture_output=True, timeout=15,
            )
            r = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=DATA_DIR, capture_output=True, timeout=10,
            )
            if r.returncode == 0:
                return
            subprocess.run(
                ["git", "commit", "-m", f"[auto] {datetime.now(TZ).strftime('%Y-%m-%d %H:%M:%S')} CST"],
                cwd=DATA_DIR, capture_output=True, timeout=15,
            )
            subprocess.run(
                ["git", "push", "origin", branch],
                cwd=DATA_DIR, capture_output=True, timeout=30,
            )
        except Exception as e:
            print(f"  [git] push failed: {e}")

    prev = load_previous()
    fetch_count = 0
    start = time.time()

    while time.time() - start < run_seconds:
        try:
            now = datetime.now(TZ)
            data = fetch_data()
            save_snapshot(data, now)
            fetch_count += 1

            if fetch_count % HISTORY_INTERVAL == 0:
                save_history(data, now)
            if fetch_count % 6 == 0:
                generate_report()
            export_csv()

            if fetch_count % push_interval == 0:
                git_push()

            prev = data
            time.sleep(POLL_INTERVAL)

        except KeyboardInterrupt:
            break
        except Exception as e:
            ts = datetime.now(TZ).strftime("%H:%M:%S")
            print(f"[{ts}] err: {e}, retry in {POLL_INTERVAL}s")
            time.sleep(POLL_INTERVAL)

    git_push()
    export_csv()
    generate_report()
    elapsed = time.time() - start
    print(f"[server] done. {fetch_count} fetches in {elapsed:.0f}s")


if __name__ == "__main__":
    if "--server" in sys.argv:
        server_loop()
    elif "--ci" in sys.argv:
        now = datetime.now(TZ)
        data = fetch_data()
        with open(LATEST_FILE, "w") as f:
            json.dump({"timestamp": now.isoformat(), **data}, f, ensure_ascii=False, indent=2)
        save_history(data, now)
        export_csv()
        generate_report()
        print(f"[{now.strftime('%H:%M:%S')}] CI fetch done: {len(data['items'])} chars, top={data['items'][0]['title']} {data['items'][0]['vote']:,}")
    elif "--once" in sys.argv:
        now = datetime.now(TZ)
        data = fetch_data()
        save_snapshot(data, now)
        save_history(data, now)
        print(f"单次抓取完成，获取到 {len(data['items'])} 位角色。")
        print_update(data, None)
    elif "--export-csv" in sys.argv:
        export_csv()
    elif "--report" in sys.argv:
        generate_report()
    else:
        main_loop()
