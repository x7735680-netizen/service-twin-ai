import os, json
from typing import Dict, Any

def _mock_event_table() -> Dict[str, Any]:
    return {
        "scenario_name": "爱回收 70㎡标准回收门店",
        "service_events": [
            {"event_id":"E1","event_name":"进店与需求识别","user_action":"用户进入门店，说明是估价、回收还是咨询","required_resources":["入口空间","接待员"],"duration_range":"1-2min","queue_possible":True,"dropoff_risk":"中","next_events":["E2"]},
            {"event_id":"E2","event_name":"扫码估价/初步登记","user_action":"用户输入机型、容量、外观等基础信息","required_resources":["自助扫码","接待员辅助"],"duration_range":"2-4min","queue_possible":True,"dropoff_risk":"中","next_events":["E3"]},
            {"event_id":"E3","event_name":"等待检测","user_action":"用户等待检测台和检测员空出","required_resources":["等候区","排队系统"],"duration_range":"0-15min","queue_possible":True,"dropoff_risk":"高","next_events":["E4","DROP_OFF"]},
            {"event_id":"E4","event_name":"设备检测","user_action":"用户交付设备，等待外观和功能检测","required_resources":["检测员","检测台","检测系统"],"duration_range":"8-15min","queue_possible":True,"dropoff_risk":"中","next_events":["E5"]},
            {"event_id":"E5","event_name":"报价沟通","user_action":"用户听取报价并判断是否接受","required_resources":["检测员/交易顾问","交易确认位"],"duration_range":"3-8min","queue_possible":True,"dropoff_risk":"高","next_events":["E6","DROP_OFF"]},
            {"event_id":"E6","event_name":"数据清除与隐私确认","user_action":"用户确认清除数据，并等待处理完成","required_resources":["数据清除位","后台人员/检测员"],"duration_range":"5-12min","queue_possible":True,"dropoff_risk":"中","next_events":["E7"]},
            {"event_id":"E7","event_name":"收款确认与离店","user_action":"用户完成签署、收款并离店","required_resources":["交易确认位","支付系统"],"duration_range":"2-4min","queue_possible":False,"dropoff_risk":"低","next_events":["END"]}
        ],
        "user_types": [
            {"type_name":"价格试探型","estimated_share":"35%","motivation":"想知道设备大概值多少钱，不一定当天出售","patience":"低","main_dropoff_points":["等待检测","报价低于预期"]},
            {"type_name":"明确出售型","estimated_share":"35%","motivation":"希望快速完成回收变现","patience":"中高","main_dropoff_points":["检测等待过长","流程不清楚"]},
            {"type_name":"比价犹豫型","estimated_share":"20%","motivation":"比较不同渠道价格","patience":"中","main_dropoff_points":["报价解释不足","感觉被压价"]},
            {"type_name":"高价值设备型","estimated_share":"10%","motivation":"设备价值高，更关注数据安全和交易可信度","patience":"高","main_dropoff_points":["数据清除不透明","检测过程不可信"]}
        ],
        "resources": [{"resource_name":"接待员","quantity":1,"capacity_logic":"同时服务 1 组"},{"resource_name":"检测台","quantity":2,"capacity_logic":"每台同时处理 1 台设备"},{"resource_name":"交易确认位","quantity":1,"capacity_logic":"同时服务 1 组"},{"resource_name":"数据清除位","quantity":1,"capacity_logic":"同时处理 1 台设备"}]
    }

def _mock_interpretation():
    return {
        "key_findings":["主要流失集中在等待检测、报价沟通和数据安全疑虑。","不同用户类型的体验风险不同，不能只看平均等待。"],
        "experience_risks":[{"risk":"信任建立前发生等待","explanation":"用户尚未理解检测与报价逻辑时进入等待，容易提前离开。"},{"risk":"报价解释不足","explanation":"比价犹豫型用户更容易在报价后放弃。"}],
        "design_interventions":[{"intervention":"入口分流/快速估价","priority":"高","expected_effect":"减少低意向用户占用完整检测队列。"},{"intervention":"等待区内容承接","priority":"高","expected_effect":"提升等待清晰度与可接受度。"},{"intervention":"报价解释卡","priority":"高","expected_effect":"提升报价可信度。"},{"intervention":"数据清除可视化","priority":"中高","expected_effect":"提升高价值设备用户信任。"}],
        "next_validation_plan":["现场记录 3 个高峰时段到店人数与等待时长。","计时 30 个检测样本。","短访 10 位用户，验证等待耐心、报价理解和数据安全顾虑。"],
        "client_summary":"本次体验仿真显示，当前服务风险主要集中在检测前等待、报价解释和数据安全信任节点。建议优先试点入口分流、等待区内容承接、报价解释卡和数据清除可视化。"
    }

def run_llm(task: str, user_input: str):
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        if task == "event_table": return _mock_event_table()
        if task == "interpretation": return _mock_interpretation()
        return {}
    from openai import OpenAI
    client = OpenAI(api_key=api_key)
    prompt_files = {"event_table":"prompts/01_service_parser.md","interpretation":"prompts/03_result_interpreter.md"}
    with open(prompt_files[task],"r",encoding="utf-8") as f:
        system_prompt=f.read()
    completion=client.chat.completions.create(model=os.getenv("OPENAI_MODEL","gpt-4.1-mini"),messages=[{"role":"system","content":system_prompt},{"role":"user","content":user_input}],response_format={"type":"json_object"})
    return json.loads(completion.choices[0].message.content)
