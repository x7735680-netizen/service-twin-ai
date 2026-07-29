from typing import Dict, Any
import html
from collections import defaultdict

DEFAULT_STEPS = [
    {"name": "进店与需求识别", "user": "进入门店，说明来意", "front": "接待员识别需求", "resource": "入口空间 / 接待员", "back": "无或轻量系统支持"},
    {"name": "扫码估价/初步登记", "user": "输入设备基础信息", "front": "引导扫码/快速估价", "resource": "自助扫码 / 接待辅助", "back": "系统记录机型与估价信息"},
    {"name": "等待检测", "user": "等待检测资源空出", "front": "等待区承接 / 进度提示", "resource": "等候区 / 检测队列", "back": "排队与检测调度"},
    {"name": "设备检测", "user": "交付设备检测", "front": "检测员说明检测进度", "resource": "检测员 / 检测台", "back": "检测系统生成结果"},
    {"name": "报价沟通", "user": "理解报价并决策", "front": "解释报价与扣价依据", "resource": "交易确认位 / 店员", "back": "报价规则与订单系统"},
    {"name": "数据清除与隐私确认", "user": "确认数据清除", "front": "隐私说明与可视化凭证", "resource": "数据清除位", "back": "后台执行数据清除"},
    {"name": "收款确认与离店", "user": "完成收款离店", "front": "确认收款与结束服务", "resource": "支付系统", "back": "交易记录与后续触达"},
]

TYPE_COLORS = {"价格试探型":"#5b6ee1","明确出售型":"#2f9e67","比价犹豫型":"#d58a00","高价值设备型":"#b445a0"}

def _node_risks(experience_result):
    risks = defaultdict(list)
    for row in experience_result.get("event_risk_rows", []):
        risks[row["服务节点"]].append(row)
    return risks

def render_experience_blueprint_html(experience_result: Dict[str, Any], steps=None) -> str:
    steps = steps or DEFAULT_STEPS
    summary = experience_result.get("summary", {})
    risks = _node_risks(experience_result)
    mapped_dropoffs = {r["服务节点"]: r["流失数"] for r in experience_result.get("mapped_node_dropoffs", [])}

    cols = []
    for step in steps:
        name = step["name"]
        risk_rows = risks.get(name, [])
        dropoffs = mapped_dropoffs.get(name, 0)
        risk_score = sum(r.get("风险分", 0) for r in risk_rows)
        cls = "risk-low"
        if risk_score > 120 or dropoffs > 80: cls = "risk-high"
        elif risk_score > 30 or dropoffs > 20: cls = "risk-mid"
        chips = []
        for r in risk_rows[:4]:
            color = TYPE_COLORS.get(r["用户类型"], "#666")
            chips.append(f"<span class='chip' style='border-color:{color};color:{color}'>{html.escape(r['用户类型'])} · 风险{r['风险分']}</span>")
        if not chips:
            chips.append("<span class='chip'>暂无显著风险</span>")
        cols.append(f"""
        <div class="col {cls}">
          <div class="cell user"><b>{html.escape(name)}</b><p>{html.escape(step['user'])}</p></div>
          <div class="cell front"><p>{html.escape(step['front'])}</p></div>
          <div class="cell resource"><p>{html.escape(step['resource'])}</p></div>
          <div class="cell back"><p>{html.escape(step['back'])}</p></div>
          <div class="cell risk"><div class="drop">流失映射：{dropoffs}</div>{''.join(chips)}</div>
        </div>
        """)

    user_type_cards = []
    for row in experience_result.get("user_type_rows", []):
        color = TYPE_COLORS.get(row["用户类型"], "#666")
        user_type_cards.append(f"""
        <div class="type-card" style="border-left-color:{color}">
          <b>{html.escape(row['用户类型'])}</b>
          <span>流失率 {row['流失率']*100:.1f}%</span>
          <span>成交率 {row['成交率']*100:.1f}%</span>
          <span>信任感 {row['平均信任感']}</span>
          <em>主要流失：{html.escape(str(row['主要流失节点']))}</em>
        </div>
        """)
    notes = "".join([f"<li>{html.escape(n)}</li>" for n in experience_result.get("experience_risk_notes", [])])
    return f"""
    <style>
    .ex-wrap{{font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif;color:#222;border:1px solid #e5e7ef;border-radius:18px;overflow:hidden;background:#fff}}
    .ex-head{{padding:18px 20px;background:#f8f9fc;border-bottom:1px solid #e5e7ef}}.ex-head h3{{margin:0;font-size:19px}}.ex-head p{{margin:6px 0 0;color:#666;font-size:13px}}
    .metrics{{display:grid;grid-template-columns:repeat(5,1fr);gap:10px;padding:14px 20px;background:#fbfcff;border-bottom:1px solid #e5e7ef}}.metrics div{{border:1px solid #e5e7ef;border-radius:12px;padding:10px;background:#fff}}.metrics span{{display:block;color:#666;font-size:12px}}.metrics b{{font-size:18px}}
    .types{{display:grid;grid-template-columns:repeat(4,1fr);gap:10px;padding:14px 20px;border-bottom:1px solid #e5e7ef}}.type-card{{border:1px solid #e5e7ef;border-left:5px solid #666;border-radius:12px;padding:10px;background:#fff}}.type-card b{{display:block;margin-bottom:6px}}.type-card span{{display:block;font-size:12px;color:#555}}.type-card em{{display:block;margin-top:6px;font-size:12px;color:#333;font-style:normal}}
    .grid{{display:grid;grid-template-columns:120px 1fr;overflow-x:auto}}.lanes{{display:grid;grid-template-rows:112px 88px 88px 88px 118px;background:#f8f9fc;border-right:1px solid #e5e7ef;min-width:120px}}.lanes div{{padding:12px;border-bottom:1px solid #e5e7ef;font-weight:700;font-size:13px;display:flex;align-items:center}}
    .flow{{display:flex;min-width:{max(1080, len(steps)*190)}px}}.col{{width:190px;display:grid;grid-template-rows:112px 88px 88px 88px 118px;border-right:1px solid #eef0f5;position:relative}}.col:after{{content:'→';position:absolute;right:-8px;top:46px;background:#fff;color:#aaa}}.col:last-child:after{{content:''}}
    .cell{{padding:10px;border-bottom:1px solid #eef0f5;font-size:12px;line-height:1.35}}.cell p{{margin:6px 0 0;color:#555}}.risk-high .risk{{background:#fff1ef}}.risk-mid .risk{{background:#fff8e5}}.risk-low .risk{{background:#f6fbf7}}.risk-high{{box-shadow:inset 0 0 0 3px #ef6b5a}}.risk-mid{{box-shadow:inset 0 0 0 2px #f0c14b}}.chip{{display:inline-block;border:1px solid #ccc;border-radius:999px;padding:3px 7px;margin:4px 4px 0 0;font-size:11px;background:#fff}}.drop{{font-size:12px;font-weight:700;margin-bottom:4px}}
    .notes{{padding:14px 20px;border-top:1px solid #e5e7ef;background:#fbfcff}}.notes h4{{margin:0 0 8px}}.notes li{{font-size:13px;margin:4px 0;color:#555}}
    </style>
    <div class="ex-wrap"><div class="ex-head"><h3>Experience Simulation Blueprint｜体验仿真蓝图</h3><p>把用户类型、流失节点、清晰度、信任感与转化意愿映射回服务蓝图。</p></div>
      <div class="metrics"><div><span>整体流失率</span><b>{summary.get('dropoff_rate',0)*100:.1f}%</b></div><div><span>整体成交率</span><b>{summary.get('conversion_rate',0)*100:.1f}%</b></div><div><span>平均清晰度</span><b>{summary.get('avg_clarity','-')}</b></div><div><span>平均信任感</span><b>{summary.get('avg_trust','-')}</b></div><div><span>主要流失</span><b>{html.escape(str(summary.get('main_dropoff_node','-')))}</b></div></div>
      <div class="types">{''.join(user_type_cards)}</div>
      <div class="grid"><div class="lanes"><div>用户动作</div><div>前台服务</div><div>资源占用</div><div>后台/系统</div><div>体验风险</div></div><div class="flow">{''.join(cols)}</div></div>
      <div class="notes"><h4>体验风险说明</h4><ul>{notes}</ul></div></div>
    """
