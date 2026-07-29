from typing import Dict, Any, List
import numpy as np
import random
from collections import defaultdict, Counter

USER_TYPES = [
    {"name": "价格试探型", "share": 0.35, "patience": 5, "enter_check_probability": 0.55, "conversion_probability": 0.20, "trust_sensitivity": 0.35, "clarity_sensitivity": 0.70, "data_security_sensitivity": 0.25},
    {"name": "明确出售型", "share": 0.35, "patience": 10, "enter_check_probability": 0.90, "conversion_probability": 0.70, "trust_sensitivity": 0.55, "clarity_sensitivity": 0.55, "data_security_sensitivity": 0.45},
    {"name": "比价犹豫型", "share": 0.20, "patience": 8, "enter_check_probability": 0.75, "conversion_probability": 0.40, "trust_sensitivity": 0.70, "clarity_sensitivity": 0.75, "data_security_sensitivity": 0.45},
    {"name": "高价值设备型", "share": 0.10, "patience": 15, "enter_check_probability": 0.85, "conversion_probability": 0.60, "trust_sensitivity": 0.85, "clarity_sensitivity": 0.60, "data_security_sensitivity": 0.90},
]

NODE_MAP = {
    "快速估价后离店": "扫码估价/初步登记",
    "未进入检测": "扫码估价/初步登记",
    "等待检测": "等待检测",
    "等待报价沟通": "报价沟通",
    "报价后放弃": "报价沟通",
    "数据安全疑虑": "数据清除与隐私确认",
}

def choose_user_type(user_types):
    r = random.random()
    cum = 0
    for ut in user_types:
        cum += ut["share"]
        if r <= cum:
            return ut
    return user_types[-1]

def clamp(v, low=0, high=100):
    return max(low, min(high, v))

def run_experience_simulation(
    hours=3.0,
    arrival_rate_per_hour=15.0,
    check_stations=2,
    check_time_min=12.0,
    transaction_stations=1,
    transaction_time_min=6.0,
    data_wipe_stations=1,
    data_wipe_time_min=8.0,
    has_entry_triage=False,
    has_waiting_content=False,
    has_price_explanation=False,
    has_data_security_visualization=False,
    simulation_runs=100,
    seed=11,
    user_types=None
):
    random.seed(seed)
    np.random.seed(seed)
    user_types = user_types or USER_TYPES
    total_minutes = hours * 60

    aggregate_users = []
    node_dropoffs_total = Counter()
    mapped_node_dropoffs = Counter()
    type_summary = defaultdict(lambda: {
        "arrivals": 0, "dropoffs": 0, "conversions": 0, "waits": [],
        "clarity": [], "trust": [], "intent": [], "main_dropoff_nodes": Counter()
    })
    event_type_impacts = defaultdict(lambda: defaultdict(lambda: {"dropoffs": 0, "clarity_hits": 0, "trust_hits": 0, "intent_hits": 0}))
    total_arrivals = total_dropoffs = total_conversions = 0

    for run in range(simulation_runs):
        arrivals = []
        t = 0
        uid = 0
        while t < total_minutes:
            t += np.random.exponential(60 / arrival_rate_per_hour)
            if t < total_minutes:
                uid += 1
                arrivals.append({"user_id": f"R{run}_U{uid}", "arrival": t, "type": choose_user_type(user_types)})
        total_arrivals += len(arrivals)

        check_free = [0.0] * check_stations
        transaction_free = [0.0] * transaction_stations
        data_wipe_free = [0.0] * data_wipe_stations

        for u in arrivals:
            ut = u["type"]
            type_name = ut["name"]
            type_summary[type_name]["arrivals"] += 1
            time = u["arrival"]
            clarity, trust, intent = 48, 50, 45
            path = []
            total_wait = 0

            def record_drop(node, mapped, exp):
                nonlocal total_dropoffs
                total_dropoffs += 1
                node_dropoffs_total[node] += 1
                mapped_node_dropoffs[mapped] += 1
                event_type_impacts[mapped][type_name]["dropoffs"] += 1
                type_summary[type_name]["dropoffs"] += 1
                type_summary[type_name]["main_dropoff_nodes"][node] += 1
                type_summary[type_name]["waits"].append(total_wait)
                type_summary[type_name]["clarity"].append(clamp(clarity))
                type_summary[type_name]["trust"].append(clamp(trust))
                type_summary[type_name]["intent"].append(clamp(intent))
                path.append({"event": node, "status": "dropoff", "experience": exp})
                aggregate_users.append({
                    "user_type": type_name, "converted": False, "dropoff_node": node,
                    "mapped_node": mapped, "wait": round(total_wait, 2),
                    "clarity": clamp(clarity), "trust": clamp(trust), "intent": clamp(intent),
                    "path": path
                })

            if has_entry_triage:
                clarity += 18
                intent += 4
                path.append({"event": "入口分流", "status": "completed", "experience": "用户知道自己应进入哪条路径"})
                if type_name == "价格试探型" and random.random() > ut["enter_check_probability"] * 0.75:
                    record_drop("快速估价后离店", "扫码估价/初步登记", "低意向用户未进入完整检测队列")
                    continue
            else:
                clarity -= 4
                event_type_impacts["进店与需求识别"][type_name]["clarity_hits"] += 1

            enter_prob = ut["enter_check_probability"] + (0.05 if has_entry_triage and type_name != "价格试探型" else 0)
            if random.random() > min(1, enter_prob):
                record_drop("未进入检测", "扫码估价/初步登记", "用户认为价格或流程不值得继续")
                continue

            patience = ut["patience"]
            if has_waiting_content:
                patience += 3
                clarity += 15
                trust += 6
                path.append({"event": "等待区内容承接", "status": "completed", "experience": "等待被用于信息录入、检测说明和预期管理"})
            else:
                event_type_impacts["等待检测"][type_name]["clarity_hits"] += 1

            idx = min(range(len(check_free)), key=lambda i: check_free[i])
            wait = max(0.0, check_free[idx] - time)
            total_wait += wait
            if wait > patience:
                clarity -= 10
                trust -= 8
                intent -= 12
                record_drop("等待检测", "等待检测", "等待超过该类用户耐心阈值")
                continue

            start = max(time, check_free[idx])
            service_time = max(1.0, np.random.normal(check_time_min, check_time_min * 0.2))
            check_free[idx] = start + service_time
            time = start + service_time
            clarity += 6
            trust += 4
            path.append({"event": "设备检测", "status": "completed", "wait": round(wait, 2), "experience": "检测完成，用户获得正式报价依据"})

            quote_conversion = ut["conversion_probability"]
            if has_price_explanation:
                clarity += 12
                trust += 10 * ut["trust_sensitivity"]
                quote_conversion += 0.08
                path.append({"event": "报价解释", "status": "completed", "experience": "扣价依据和预估价差异被解释"})
            else:
                clarity -= 5 * ut["clarity_sensitivity"]
                trust -= 6 * ut["trust_sensitivity"]
                event_type_impacts["报价沟通"][type_name]["clarity_hits"] += 1
                event_type_impacts["报价沟通"][type_name]["trust_hits"] += 1

            tidx = min(range(len(transaction_free)), key=lambda i: transaction_free[i])
            twait = max(0.0, transaction_free[tidx] - time)
            total_wait += twait
            if twait > max(8, patience):
                trust -= 8
                intent -= 10
                record_drop("等待报价沟通", "报价沟通", "报价前等待过长")
                continue

            tstart = max(time, transaction_free[tidx])
            tdur = max(1.0, np.random.normal(transaction_time_min, transaction_time_min * 0.2))
            transaction_free[tidx] = tstart + tdur
            time = tstart + tdur
            path.append({"event": "报价沟通", "status": "completed", "wait": round(twait, 2), "experience": "用户进入价格决策"})

            quote_conversion = max(0.02, min(0.95, quote_conversion + (trust - 50) / 300 + (clarity - 50) / 350))
            if random.random() > quote_conversion:
                intent -= 15
                record_drop("报价后放弃", "报价沟通", "用户认为价格或解释不足以支持成交")
                continue

            if has_data_security_visualization:
                trust += 15 * ut["data_security_sensitivity"]
                clarity += 6
                path.append({"event": "数据清除可视化", "status": "completed", "experience": "隐私处理被前台可见化"})
            else:
                trust -= 10 * ut["data_security_sensitivity"]
                event_type_impacts["数据清除与隐私确认"][type_name]["trust_hits"] += 1
                if type_name == "高价值设备型" and random.random() < 0.18:
                    record_drop("数据安全疑虑", "数据清除与隐私确认", "高价值设备用户因隐私不透明放弃")
                    continue

            didx = min(range(len(data_wipe_free)), key=lambda i: data_wipe_free[i])
            dwait = max(0.0, data_wipe_free[didx] - time)
            total_wait += dwait
            dstart = max(time, data_wipe_free[didx])
            ddur = max(1.0, np.random.normal(data_wipe_time_min, data_wipe_time_min * 0.2))
            data_wipe_free[didx] = dstart + ddur
            trust += 5
            intent += 8
            total_conversions += 1
            path.append({"event": "数据清除与收款", "status": "converted", "wait": round(dwait, 2), "experience": "交易完成"})
            type_summary[type_name]["conversions"] += 1
            type_summary[type_name]["waits"].append(total_wait)
            type_summary[type_name]["clarity"].append(clamp(clarity))
            type_summary[type_name]["trust"].append(clamp(trust))
            type_summary[type_name]["intent"].append(clamp(intent))
            aggregate_users.append({
                "user_type": type_name, "converted": True, "dropoff_node": None,
                "mapped_node": None, "wait": round(total_wait, 2),
                "clarity": clamp(clarity), "trust": clamp(trust), "intent": clamp(intent), "path": path
            })

    user_type_rows = []
    for type_name, s in type_summary.items():
        arrivals = s["arrivals"]
        if not arrivals:
            continue
        main_node = s["main_dropoff_nodes"].most_common(1)[0][0] if s["main_dropoff_nodes"] else "-"
        user_type_rows.append({
            "用户类型": type_name,
            "到达数": arrivals,
            "流失率": round(s["dropoffs"] / max(arrivals, 1), 3),
            "成交率": round(s["conversions"] / max(arrivals, 1), 3),
            "平均等待/min": round(float(np.mean(s["waits"])), 2) if s["waits"] else 0,
            "平均清晰度": round(float(np.mean(s["clarity"])), 1) if s["clarity"] else 0,
            "平均信任感": round(float(np.mean(s["trust"])), 1) if s["trust"] else 0,
            "平均转化意愿": round(float(np.mean(s["intent"])), 1) if s["intent"] else 0,
            "主要流失节点": main_node
        })

    all_waits = [u["wait"] for u in aggregate_users]
    all_clarity = [u["clarity"] for u in aggregate_users]
    all_trust = [u["trust"] for u in aggregate_users]
    all_intent = [u["intent"] for u in aggregate_users]

    event_risk_rows = []
    for node, type_dict in event_type_impacts.items():
        for type_name, imp in type_dict.items():
            score = imp["dropoffs"] * 3 + imp["clarity_hits"] + imp["trust_hits"] + imp["intent_hits"]
            if score > 0:
                event_risk_rows.append({
                    "服务节点": node,
                    "用户类型": type_name,
                    "流失数": imp["dropoffs"],
                    "清晰度风险": imp["clarity_hits"],
                    "信任风险": imp["trust_hits"],
                    "转化风险": imp["intent_hits"],
                    "风险分": score
                })

    risk_notes = []
    avg_clarity = float(np.mean(all_clarity)) if all_clarity else 0
    avg_trust = float(np.mean(all_trust)) if all_trust else 0
    drop_rate = total_dropoffs / max(total_arrivals, 1)
    if avg_clarity < 55:
        risk_notes.append("流程清晰度偏低，用户可能不知道下一步该做什么或为什么要等待。")
    if avg_trust < 55:
        risk_notes.append("信任感偏低，检测、报价或数据清除需要更透明的前台触点。")
    if drop_rate > 0.25:
        risk_notes.append("整体流失率较高，需要优先处理等待流失或报价后放弃。")
    if not risk_notes:
        risk_notes.append("整体体验状态相对稳定，可继续比较不同设计干预方案。")

    return {
        "summary": {
            "total_arrivals": total_arrivals,
            "dropoff_rate": round(drop_rate, 3),
            "conversion_rate": round(total_conversions / max(total_arrivals, 1), 3),
            "avg_wait_min": round(float(np.mean(all_waits)), 2) if all_waits else 0,
            "avg_clarity": round(avg_clarity, 1),
            "avg_trust": round(avg_trust, 1),
            "avg_intent": round(float(np.mean(all_intent)), 1) if all_intent else 0,
            "main_dropoff_node": node_dropoffs_total.most_common(1)[0][0] if node_dropoffs_total else "-"
        },
        "user_type_rows": user_type_rows,
        "dropoff_nodes": [{"节点": k, "流失数": v, "映射服务节点": NODE_MAP.get(k, k)} for k, v in node_dropoffs_total.most_common()],
        "mapped_node_dropoffs": [{"服务节点": k, "流失数": v} for k, v in mapped_node_dropoffs.most_common()],
        "event_risk_rows": sorted(event_risk_rows, key=lambda x: x["风险分"], reverse=True),
        "sample_paths": aggregate_users[:8],
        "experience_risk_notes": risk_notes,
        "interventions_enabled": {
            "has_entry_triage": has_entry_triage,
            "has_waiting_content": has_waiting_content,
            "has_price_explanation": has_price_explanation,
            "has_data_security_visualization": has_data_security_visualization
        },
        "model_notes": [
            "v0.7 用于服务体验仿真原型验证，不适合作为经营预测。",
            "清晰度、信任感、转化意愿是设计假设指标，需要通过真实研究校准。"
        ]
    }
