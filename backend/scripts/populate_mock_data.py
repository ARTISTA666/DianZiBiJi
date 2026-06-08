"""
论文 Mock 数据批量生成脚本
============================
为论文演示项目生成全套 mock 数据，包括：
  - 15~20 条已审核实验笔记（多种实验类型）
  - 配套的图谱实体与关系（100+ 实体 / 150+ 关系）
  - 40 条 AI 问答日志（附录 A 20 题 × 普通 RAG / 图谱增强 RAG 两种模式）
  - 40 条人工评价记录
  - 多条智能辅助生成记录
  - 额外的资料库文件

用法：
    python scripts/populate_mock_data.py

要求：PostgreSQL 已运行，后端已至少启动过一次（建表 + 基础 seed）。
"""

import sys
import os
from pathlib import Path
from datetime import date, timedelta, datetime

# 添加 backend 到 sys.path
# Docker 内路径: /app/scripts/...  ->  /app
# 本地路径:   scripts/...          ->  . (backend 在 project_root/backend)
_script_dir = Path(__file__).resolve().parent
if _script_dir.name == "scripts":
    # 可能是在 backend/scripts/ 下 (Docker 场景)
    if (_script_dir.parent / "app").exists():
        sys.path.insert(0, str(_script_dir.parent))
    else:
        # 本地场景: scripts/ 和 backend/ 同级的
        sys.path.insert(0, str(_script_dir.parent / "backend"))
else:
    sys.path.insert(0, str(_script_dir))

from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.project import Project, ProjectMember
from app.models.note import ExperimentNote, NoteStatus, NoteVersion, NoteApproval
from app.models.file import StoredFile, FileCategory, FileStatus, KnowledgeSyncStatus
from app.models.knowledge_graph import KnowledgeEntity, KnowledgeRelation, KnowledgeExtractionRun
from app.models.ai import AIQueryLog, AIQueryEvaluation, AgentGenerationRun, AgentTaskType, AgentRunStatus, RagMode
from app.models.rag import ProjectRagDataset, RagFileSync, RagSyncStatus
from app.models.audit import AuditLog
from app.services.knowledge_graph import KnowledgeGraphService
from app.services.agent import AgentGenerationService

# ── 附录 A 的 20 个问题 ──────────────────────────────────────
QUESTIONS = [
    # 资料事实型 (Q01-Q05)
    ("Q01", "资料事实型", "PCR 条件优化实验的退火温度优化依据是什么？"),
    ("Q02", "资料事实型", "PCR 体系配置和循环条件主要来自哪份资料？"),
    ("Q03", "资料事实型", "CCK-8 检测步骤和读数要求主要来自哪份资料？"),
    ("Q04", "资料事实型", "细胞活力检测实验中读数和统计应关注什么？"),
    ("Q05", "资料事实型", "项目资料库中哪些资料已经同步到知识库？"),
    # 实验对象关系型 (Q06-Q10)
    ("Q06", "实验对象关系型", "PCR 条件优化实验使用了哪些试剂？"),
    ("Q07", "实验对象关系型", "PCR 条件优化实验使用了哪些样本？"),
    ("Q08", "实验对象关系型", "细胞活力检测实验使用了哪些试剂和仪器？"),
    ("Q09", "实验对象关系型", "Western Blot 蛋白表达验证使用了哪些试剂？"),
    ("Q10", "实验对象关系型", "Western Blot 蛋白表达验证使用了哪些仪器？"),
    # 过程追溯型 (Q11-Q15)
    ("Q11", "过程追溯型", "退火温度 58℃ 条带最清晰这一结果来自哪条实验笔记？"),
    ("Q12", "过程追溯型", "处理组细胞活力下降约 18% 这一结论来自哪条实验笔记？"),
    ("Q13", "过程追溯型", "处理组目标蛋白表达降低这一结果来自哪条实验笔记？"),
    ("Q14", "过程追溯型", "三条实验笔记分别由谁创建？"),
    ("Q15", "过程追溯型", "当前项目包含哪些已审核实验笔记？"),
    # 综合总结型 (Q16-Q20)
    ("Q16", "综合总结型", "2026 年 6 月 3 日至 6 月 5 日项目完成了哪些实验？"),
    ("Q17", "综合总结型", "这三项实验分别产生了哪些主要结果？"),
    ("Q18", "综合总结型", "项目中涉及的主要试剂可以按实验类型如何归纳？"),
    ("Q19", "综合总结型", "项目中涉及的主要仪器可以按实验类型如何归纳？"),
    ("Q20", "综合总结型", "根据当前实验记录，项目下一步可以重点复核哪些结果？"),
    ("Q21", "资料事实型", "项目资料库中已经审核通过的实验方案有哪些？"),
    ("Q22", "实验对象关系型", "质粒构建实验使用了哪些工具酶？"),
    ("Q23", "过程追溯型", "细胞凋亡检测的结果来自哪次实验？"),
    ("Q24", "综合总结型", "项目中涉及的细胞实验可以按类型如何划分？"),
    ("Q25", "资料事实型", "Western Blot 实验的标准流程在哪份资料中有详细说明？"),
    ("Q21", "资料事实型", "项目资料库中已经审核通过的实验方案有哪些？"),
    ("Q22", "实验对象关系型", "质粒构建实验使用了哪些工具酶？"),
    ("Q23", "过程追溯型", "细胞凋亡检测的结果来自哪次实验？"),
    ("Q24", "综合总结型", "项目中涉及的细胞实验可以按类型如何划分？"),
    ("Q25", "资料事实型", "Western Blot 实验的标准流程在哪份资料中有详细说明？"),
]

# ── 模拟回答（普通 RAG 版 / 图谱增强 RAG 版）───────────────
ANSWERS_PROJECT_RAG = {
    "Q01": "根据项目资料库中的 PCR 实验方案文档，退火温度优化是通过设置 55℃-65℃ 梯度 PCR 完成的。文档详细说明了体系配置和循环参数。",
    "Q02": "PCR 体系配置和循环条件主要来自项目资料库中的《PCR 实验方案》文档，该文档已同步至项目知识库。",
    "Q03": "CCK-8 检测步骤和读数要求来自项目资料库中的细胞活力检测参考文档，已同步到知识库可供查阅。",
    "Q04": "细胞活力检测实验中需要关注 450nm 吸光度读数、重复孔标准差和相对活力百分比计算，详见资料库文档。",
    "Q05": "当前项目资料库中已有 2 份资料同步到知识库：PCR 实验方案和细胞活力检测参考文档。",
    "Q06": "根据资料库检索，PCR 条件优化实验使用了 Taq DNA Polymerase、dNTP、MgCl2 和模板 DNA 等试剂。",
    "Q07": "PCR 条件优化实验使用了样本 A 和样本 B 作为扩增模板。",
    "Q08": "细胞活力检测实验使用了 CCK-8 试剂、PBS 和 DMEM 培养基，仪器包括酶标仪和 CO2 培养箱。",
    "Q09": "Western Blot 实验使用了 RIPA 裂解液、BCA 试剂盒、一抗和二抗等试剂。",
    "Q10": "Western Blot 实验使用了电泳仪、转膜仪和凝胶成像系统等仪器。",
    "Q11": "退火温度 58℃ 条带最清晰这一结果来自 PCR 条件优化实验笔记。",
    "Q12": "处理组细胞活力下降约 18% 这一结论来自细胞活力检测实验笔记。",
    "Q13": "处理组目标蛋白表达降低这一结果来自 Western Blot 蛋白表达验证笔记。",
    "Q14": "三条实验笔记均由管理员用户创建。",
    "Q15": "当前项目包含 PCR 条件优化实验、细胞活力检测实验和 Western Blot 蛋白表达验证三条已审核实验笔记。",
    "Q16": "2026 年 6 月 3 日至 6 月 5 日项目完成了 PCR 条件优化、细胞活力检测和 Western Blot 验证三项实验。",
    "Q17": "三项实验的主要结果：PCR 退火温度 58℃ 最佳；细胞活力下降 18%；目标蛋白表达降低。",
    "Q18": "PCR 实验使用 Taq 酶体系试剂；细胞实验使用 CCK-8 体系；Western Blot 使用蛋白裂解和免疫检测体系。",
    "Q19": "PCR 使用 Thermal Cycler；细胞实验使用酶标仪和培养箱；Western Blot 使用电泳转膜成像系统。",
    "Q20": "建议进一步验证退火温度 58℃ 条件的可重复性，并完善 Western Blot 的定量分析。",
    "Q21": "项目中有PCR实验方案、细胞活力检测方案、细胞培养标准和Western Blot流程等资料。",
    "Q22": "根据资料库文档，质粒构建使用EcoRI和HindIII两种限制性内切酶。",
    "Q23": "根据实验笔记记录，细胞凋亡检测的结果来自5月15日的Annexin V-FITC/PI双染实验。",
    "Q24": "项目中的细胞实验包括细胞活力检测、细胞传代冻存、细胞凋亡检测和克隆形成实验。",
    "Q25": "Western Blot的标准流程在western_blot_protocol.txt资料中有详细说明。",
}

ANSWERS_KG_ENHANCED = {
    "Q01": "根据项目资料库中的 PCR 实验方案以及知识图谱中'PCR 条件优化实验'节点的关联信息，退火温度优化依据为 55℃-65℃ 梯度实验结果。图谱显示该笔记关联了 PCR 实验类型、Taq DNA Polymerase 等试剂和 PCR Thermal Cycler 仪器。",
    "Q02": "PCR 体系配置和循环条件来自资料库中的 PCR 实验方案文件。知识图谱显示该资料已关联到项目知识库，且 PCR 条件优化实验笔记中记录了完整的体系配置信息。",
    "Q03": "CCK-8 检测步骤主要来自资料库中的细胞活力检测参考文档。知识图谱中'细胞活力检测实验'节点关联了 CCK-8 试剂、酶标仪和 CO2 培养箱等实体。",
    "Q04": "细胞活力检测实验需关注 450nm 吸光度。图谱显示实验使用了 CCK-8 试剂和酶标仪，样本包括处理组和对照组细胞，结果记录了约 18% 的活力下降。",
    "Q05": "当前项目已同步 2 份资料到知识库。图谱显示项目实体下包含'PCR 实验方案'和'细胞活力检测参考文档'两个文件实体。",
    "Q06": "知识图谱中 PCR 条件优化实验节点通过'使用试剂'关系关联了 Taq DNA Polymerase、dNTP、MgCl2 等试剂实体。这些结构化信息来自审核通过的实验笔记字段。",
    "Q07": "知识图谱显示 PCR 条件优化实验通过'使用样本'关系关联了样本 A 和样本 B 两个样本实体。",
    "Q08": "图谱显示细胞活力检测实验通过'使用试剂'关系关联 CCK-8、PBS、DMEM 培养基，通过'使用仪器'关系关联酶标仪和 CO2 培养箱。",
    "Q09": "知识图谱中 Western Blot 实验通过'使用试剂'关系关联了 RIPA 裂解液、BCA 试剂盒、一抗和二抗等试剂实体。",
    "Q10": "图谱显示 Western Blot 实验通过'使用仪器'关系关联了电泳仪、转膜仪和凝胶成像系统等仪器实体。",
    "Q11": "知识图谱显示退火温度 58℃ 条带最清晰这一结果实体通过'产生结果'关系关联到 PCR 条件优化实验笔记，该笔记审核通过后已进入图谱。",
    "Q12": "图谱中'细胞活力下降约 18%'结果实体通过'产生结果'关系关联到细胞活力检测实验笔记，来源可追溯。",
    "Q13": "知识图谱显示'目标蛋白表达降低'结果实体通过'产生结果'关系关联到 Western Blot 蛋白表达验证笔记。",
    "Q14": "图谱显示三条实验笔记均通过'创建者'关系关联到管理员用户实体，创建者信息完整可查。",
    "Q15": "知识图谱项目实体下通过'包含笔记'关系关联了三条实验笔记，分别为 PCR 条件优化实验、细胞活力检测实验和 Western Blot 蛋白表达验证。",
    "Q16": "根据知识图谱中实验笔记的时间属性和实验类型关系，2026 年 6 月 3-5 日项目完成了 PCR（PCR 条件优化）、细胞培养（细胞活力检测）和 Western Blot（蛋白表达验证）三类实验。",
    "Q17": "图谱中'产生结果'关系显示：PCR 实验产生退火温度优化结果、细胞实验产生活力下降结果、Western Blot 产生蛋白表达降低结果。",
    "Q18": "知识图谱按实验类型分组：PCR 类型关联 Taq 酶体系试剂；细胞培养类型关联 CCK-8 体系试剂；Western Blot 类型关联蛋白裂解和免疫检测体系试剂。",
    "Q19": "图谱按实验类型分组显示仪器使用情况：PCR 类型使用 Thermal Cycler；细胞培养类型使用酶标仪和培养箱；Western Blot 类型使用电泳转膜成像系统。",
    "Q20": "综合图谱分析，项目已覆盖 PCR 优化、细胞活力和蛋白验证三个方向。建议补充退火温度验证实验的重复记录，并完善 Western Blot 定量分析的笔记记录。",
    "Q21": "图谱显示项目实体关联了多份资料文件，包括PCR方案、细胞培养标准和WB流程等。",
    "Q22": "知识图谱中质粒构建实验节点通过使用试剂关系关联了EcoRI和HindIII两种内切酶。",
    "Q23": "图谱显示细胞凋亡检测实验节点通过产生结果关联了凋亡比例结果实体。",
    "Q24": "按实验类型分组，图谱显示项目包含PCR、细胞培养、Western Blot和质粒构建四类实验。",
    "Q25": "知识图谱中WB相关节点关联了电泳仪、转膜仪和一抗二抗等试剂实体的详细信息。",
}

# ── 额外的实验笔记数据（论文演示用）─────────────────────────
EXTRA_NOTES = [
    {
        "title": "qPCR 定量验证实验",
        "experiment_type": "PCR",
        "experiment_date": date(2026, 5, 28),
        "fixed_fields": {
            "reagents": "SYBR Green Master Mix、cDNA 模板、引物对、无酶水",
            "instrument": "荧光定量 PCR 仪、微量分光光度计",
            "sample": "cDNA 样本 1、cDNA 样本 2、阴性对照",
            "result": "目标基因在样本 1 中表达量约为样本 2 的 2.3 倍，融解曲线单一峰。",
        },
        "content_text": "试剂: SYBR Green Master Mix、cDNA 模板、引物对\n仪器: 荧光定量 PCR 仪\n样本: cDNA 样本 1、2\n结果: 目标基因差异表达约 2.3 倍。",
    },
    {
        "title": "细胞传代与冻存记录",
        "experiment_type": "细胞培养",
        "experiment_date": date(2026, 5, 25),
        "fixed_fields": {
            "reagents": "胰酶、PBS、DMEM 完全培养基、DMSO",
            "instrument": "超净工作台、CO2 培养箱、液氮罐",
            "sample": "HEK293T 细胞、HeLa 细胞",
            "result": "HEK293T 传代后 24h 汇合度达 85%，冻存细胞复苏活力约 92%。",
        },
        "content_text": "试剂: 胰酶、PBS、DMEM、DMSO\n仪器: 超净工作台、培养箱、液氮罐\n样本: HEK293T、HeLa\n结果: 传代正常，冻存复苏活力约 92%。",
    },
    {
        "title": "质粒提取与酶切鉴定",
        "experiment_type": "质粒构建/转染",
        "experiment_date": date(2026, 5, 20),
        "fixed_fields": {
            "reagents": "质粒提取试剂盒、限制性内切酶 EcoRI、HindIII、琼脂糖",
            "instrument": "微量离心机、电泳仪、凝胶成像系统、Nanodrop",
            "sample": "pCDNA3.1 质粒、pEGFP-C1 质粒",
            "result": "pCDNA3.1 浓度 320 ng/μL，A260/280=1.85；酶切产物与预期片段大小一致。",
        },
        "content_text": "试剂: 质粒提取试剂盒、EcoRI、HindIII\n仪器: 离心机、电泳仪、凝胶成像\n样本: pCDNA3.1、pEGFP-C1\n结果: 质粒质量合格，酶切鉴定正确。",
    },
    {
        "title": "细胞转染效率优化",
        "experiment_type": "质粒构建/转染",
        "experiment_date": date(2026, 5, 22),
        "fixed_fields": {
            "reagents": "Lipofectamine 3000、Opti-MEM、pEGFP-C1 质粒",
            "instrument": "荧光显微镜、CO2 培养箱、超净工作台",
            "sample": "HEK293T 细胞",
            "result": "Lipofectamine 3000 比例 1:1.5 时转染效率约 75%，细胞状态良好。",
        },
        "content_text": "试剂: Lipofectamine 3000、Opti-MEM、pEGFP-C1\n仪器: 荧光显微镜、培养箱\n样本: HEK293T\n结果: 转染效率约 75%。",
    },
    {
        "title": "蛋白浓度标准曲线测定",
        "experiment_type": "Western Blot",
        "experiment_date": date(2026, 5, 18),
        "fixed_fields": {
            "reagents": "BSA 标准品、BCA 工作液、RIPA 裂解液",
            "instrument": "酶标仪、恒温孵育箱",
            "sample": "BSA 标准品系列稀释液",
            "result": "标准曲线 R²=0.998，线性范围 0.1-2.0 mg/mL。",
        },
        "content_text": "试剂: BSA、BCA 工作液、RIPA\n仪器: 酶标仪、孵育箱\n样本: BSA 标准品\n结果: R²=0.998，标准曲线可靠。",
    },
    {
        "title": "SDS-PAGE 凝胶配制与电泳",
        "experiment_type": "Western Blot",
        "experiment_date": date(2026, 5, 19),
        "fixed_fields": {
            "reagents": "30% 丙烯酰胺、Tris-HCl、SDS、APS、TEMED、蛋白 Marker",
            "instrument": "电泳仪、垂直电泳槽、制胶架",
            "sample": "蛋白样本 P1、P2、蛋白 Marker",
            "result": "分离胶 12% 浓度效果最佳，条带分离清晰，Marker 条带完整。",
        },
        "content_text": "试剂: 丙烯酰胺、Tris-HCl、SDS、APS、TEMED\n仪器: 电泳仪、垂直电泳槽\n样本: 蛋白样本 P1、P2\n结果: 12% 分离胶分离效果最佳。",
    },
    {
        "title": "细胞凋亡检测实验",
        "experiment_type": "细胞培养",
        "experiment_date": date(2026, 5, 15),
        "fixed_fields": {
            "reagents": "Annexin V-FITC、PI 染料、结合缓冲液",
            "instrument": "流式细胞仪、离心机",
            "sample": "处理组细胞、对照组细胞",
            "result": "处理组早期凋亡比例约 12.5%，对照组约 3.2%，差异有统计学意义。",
        },
        "content_text": "试剂: Annexin V-FITC、PI、结合缓冲液\n仪器: 流式细胞仪、离心机\n样本: 处理组、对照组细胞\n结果: 处理组凋亡比例 12.5%。",
    },
    {
        "title": "RNA 提取与逆转录",
        "experiment_type": "PCR",
        "experiment_date": date(2026, 5, 12),
        "fixed_fields": {
            "reagents": "TRIzol、氯仿、异丙醇、75% 乙醇、无酶水、逆转录试剂盒",
            "instrument": "微量分光光度计、PCR 仪、冷冻离心机",
            "sample": "处理组细胞、对照组细胞",
            "result": "RNA 浓度：处理组 450 ng/μL，对照组 520 ng/μL；A260/280 均为 2.0 以上。cDNA 合成成功。",
        },
        "content_text": "试剂: TRIzol、氯仿、异丙醇、逆转录试剂盒\n仪器: 分光光度计、PCR 仪、冷冻离心机\n样本: 处理组、对照组细胞\n结果: RNA 质量合格，逆转录成功。",
    },
    {
        "title": "免疫荧光染色实验",
        "experiment_type": "细胞培养",
        "experiment_date": date(2026, 5, 10),
        "fixed_fields": {
            "reagents": "多聚甲醛、Triton X-100、BSA、一抗、荧光二抗、DAPI",
            "instrument": "荧光显微镜、共聚焦显微镜、摇床",
            "sample": "处理组细胞爬片、对照组细胞爬片",
            "result": "处理组细胞核中目标蛋白荧光强度明显高于对照组，定位清晰。",
        },
        "content_text": "试剂: 多聚甲醛、Triton X-100、BSA、一抗、荧光二抗、DAPI\n仪器: 荧光显微镜、共聚焦显微镜\n样本: 处理组、对照组细胞爬片\n结果: 目标蛋白荧光增强。",
    },
    {
        "title": "克隆形成实验",
        "experiment_type": "细胞培养",
        "experiment_date": date(2026, 5, 5),
        "fixed_fields": {
            "reagents": "结晶紫染液、PBS、DMEM 培养基、甲醛",
            "instrument": "CO2 培养箱、倒置显微镜",
            "sample": "处理组细胞、对照组细胞",
            "result": "处理组克隆形成率约 8%，对照组约 22%，差异显著（P<0.01）。",
        },
        "content_text": "试剂: 结晶紫、PBS、DMEM、甲醛\n仪器: 培养箱、倒置显微镜\n样本: 处理组、对照组细胞\n结果: 克隆形成率 8% vs 22%。",
    },
    {
        "title": "ELISA 检测实验",
        "experiment_type": "Western Blot",
        "experiment_date": date(2026, 5, 8),
        "fixed_fields": {
            "reagents": "ELISA 试剂盒、洗涤缓冲液、终止液、TMB 底物",
            "instrument": "酶标仪、恒温孵育箱、洗板机",
            "sample": "细胞上清样本、标准品系列",
            "result": "处理组 IL-6 浓度约 320 pg/mL，对照组约 85 pg/mL。",
        },
        "content_text": "试剂: ELISA 试剂盒、TMB、终止液\n仪器: 酶标仪、孵育箱、洗板机\n样本: 细胞上清、标准品\n结果: IL-6 浓度 320 vs 85 pg/mL。",
    },
    {
        "title": "质粒测序结果分析",
        "experiment_type": "质粒构建/转染",
        "experiment_date": date(2026, 5, 3),
        "fixed_fields": {
            "reagents": "测序引物、BigDye Terminator",
            "instrument": "测序仪、序列分析软件",
            "sample": "重组质粒 DNA",
            "result": "测序结果与目标序列比对一致率 99.8%，无移码突变。",
        },
        "content_text": "试剂: 测序引物、BigDye\n仪器: 测序仪\n样本: 重组质粒\n结果: 序列正确，一致率 99.8%。",
    },
]

# ── 额外资料库文件 ──────────────────────────────────────────
EXTRA_FILES = [
    ("qPCR_protocol.txt", "SYBR Green 法 qPCR 实验流程：1. cDNA 稀释 10 倍；2. 配置 20μL 体系；3. 三步法扩增；4. 融解曲线分析。"),
    ("cell_culture_standard.txt", "细胞培养标准操作流程：1. 培养基预热；2. 细胞复苏；3. 传代比例 1:3-1:4；4. 定期支原体检测。"),
    ("western_blot_protocol.txt", "Western Blot 标准流程：1. 蛋白提取与定量；2. SDS-PAGE 电泳；3. 转膜条件 100V 60min；4. 封闭 5% BSA；5. 一抗 4℃ 过夜。"),
    ("plasmid_extraction_protocol.txt", "质粒提取流程：1. 过夜培养菌液；2. 碱裂解法提取；3. 柱纯化；4. 浓度和纯度检测。"),
    ("flow_cytometry_protocol.txt", "流式细胞术检测流程：1. 细胞收集；2. 染色 30min；3. 上机检测；4. 数据分析。"),
]


def _create_or_get_admin(db: Session) -> User:
    user = db.query(User).filter(User.username == "admin").first()
    if not user:
        user = User(
            username="admin",
            password_hash=hash_password("admin123"),
            display_name="系统管理员",
            email="admin@example.local",
            role=UserRole.SUPER_ADMIN,
        )
        db.add(user)
        db.flush()
    return user


def _ensure_project(db: Session, admin: User) -> Project:
    project = db.query(Project).filter(Project.name == "论文演示项目：KG-RAG 实验流程").first()
    if project is None:
        project = Project(
            name="论文演示项目：KG-RAG 实验流程",
            description="用于论文截图和实验章节的演示项目，覆盖实验笔记、资料库、知识图谱、RAG 问答、评价和智能体生成闭环。",
            owner_user_id=admin.id,
        )
        db.add(project)
        db.flush()
    return project


def _create_demo_files(db: Session, project: Project, admin: User) -> list[StoredFile]:
    """创建演示资料文件，返回文件列表"""
    # Storage path: working_dir/storage/demo/
    demo_dir = Path("storage/demo")
    demo_dir.mkdir(parents=True, exist_ok=True)

    files_created = []
    all_file_defs = [
        ("PCR_protocol_demo.txt", "PCR 体系配置、循环条件和退火温度优化说明。"),
        ("cell_assay_reference_demo.txt", "CCK-8 检测步骤、读数要求和细胞活力统计说明。"),
    ] + EXTRA_FILES

    for filename, content in all_file_defs:
        path = demo_dir / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")

        stored = (
            db.query(StoredFile)
            .filter(StoredFile.project_id == project.id, StoredFile.original_filename == filename)
            .first()
        )
        if stored is None:
            stored = StoredFile(
                project_id=project.id,
                uploaded_by=admin.id,
                file_category=FileCategory.KNOWLEDGE_DOCUMENT,
                original_filename=filename,
                storage_path=str(path),
                mime_type="text/plain",
                file_size=path.stat().st_size,
                file_hash=f"demo-{filename}-{path.stat().st_size}",
                status=FileStatus.APPROVED,
                knowledge_sync_status=KnowledgeSyncStatus.SYNCED.value,
                knowledge_sync_message="论文演示资料已入库",
            )
            db.add(stored)
            db.flush()
        files_created.append(stored)

    return files_created


def _create_notes(db: Session, project: Project, admin: User, kg_service: KnowledgeGraphService) -> list[ExperimentNote]:
    """创建已审核实验笔记，返回笔记列表"""
    all_notes_def = [
        {
            "title": "PCR 条件优化实验",
            "experiment_type": "PCR",
            "experiment_date": date(2026, 6, 3),
            "fixed_fields": {
                "reagents": "Taq DNA Polymerase、dNTP、MgCl2、模板 DNA",
                "instrument": "PCR Thermal Cycler",
                "sample": "样本 A、样本 B",
                "result": "退火温度 58℃ 时扩增条带最清晰，非特异性条带减少。",
            },
            "content_text": "试剂: Taq DNA Polymerase、dNTP、MgCl2\n仪器: PCR Thermal Cycler\n样本: 样本 A、样本 B\n结果: 58℃ 条件下条带清晰。",
        },
        {
            "title": "细胞活力检测实验",
            "experiment_type": "细胞培养",
            "experiment_date": date(2026, 6, 4),
            "fixed_fields": {
                "reagents": "CCK-8、PBS、DMEM 培养基",
                "instrument": "酶标仪、CO2 培养箱",
                "sample": "处理组细胞、对照组细胞",
                "result": "处理组细胞活力较对照组下降约 18%，重复孔结果稳定。",
            },
            "content_text": "试剂: CCK-8、PBS、DMEM 培养基\n仪器: 酶标仪、CO2 培养箱\n样本: 处理组细胞、对照组细胞\n结果: 细胞活力下降约 18%。",
        },
        {
            "title": "Western Blot 蛋白表达验证",
            "experiment_type": "Western Blot",
            "experiment_date": date(2026, 6, 5),
            "fixed_fields": {
                "reagents": "RIPA 裂解液、BCA 试剂盒、一抗、二抗",
                "instrument": "电泳仪、转膜仪、凝胶成像系统",
                "sample": "蛋白样本 P1、蛋白样本 P2",
                "result": "目标蛋白在处理组表达降低，内参条带稳定。",
            },
            "content_text": "试剂: RIPA 裂解液、BCA 试剂盒、一抗、二抗\n仪器: 电泳仪、转膜仪、凝胶成像系统\n样本: 蛋白样本 P1、蛋白样本 P2\n结果: 处理组目标蛋白表达降低。",
        },
    ] + EXTRA_NOTES

    notes: list[ExperimentNote] = []
    for ndef in all_notes_def:
        note = (
            db.query(ExperimentNote)
            .filter(ExperimentNote.project_id == project.id, ExperimentNote.title == ndef["title"])
            .first()
        )
        if note is None:
            note = ExperimentNote(
                project_id=project.id,
                title=ndef["title"],
                experiment_type=ndef["experiment_type"],
                experiment_date=ndef["experiment_date"],
                owner_user_id=admin.id,
                status=NoteStatus.APPROVED,
            )
            db.add(note)
            db.flush()
            version = NoteVersion(
                note_id=note.id,
                version_number=1,
                fixed_fields_json=ndef["fixed_fields"],
                content_json={"text": ndef["content_text"]},
                created_by=admin.id,
                change_summary="论文演示数据",
                is_locked=True,
            )
            db.add(version)
            db.flush()
            note.current_version_id = version.id
            db.add(
                NoteApproval(
                    note_id=note.id,
                    version_id=version.id,
                    reviewer_user_id=admin.id,
                    action="approved",
                    comment="论文演示数据审核通过",
                )
            )
        notes.append(note)

    # 提取知识图谱
    for note in notes:
        kg_service.extract_note(db, note, triggered_by=admin.id, rebuild=True)

    return notes


def _ensure_rag_dataset(db: Session, project: Project, admin: User, files: list[StoredFile]) -> ProjectRagDataset:
    """确保 RAG 数据集存在"""
    dataset = db.query(ProjectRagDataset).filter(ProjectRagDataset.project_id == project.id).first()
    if dataset is None:
        dataset = ProjectRagDataset(
            project_id=project.id,
            dify_dataset_id=f"demo-dataset-{project.id}",
            dify_dataset_name=f"ELN Project {project.id} - {project.name}",
            created_by=admin.id,
        )
        db.add(dataset)
        db.flush()

    for f in files:
        sync = db.query(RagFileSync).filter(RagFileSync.file_id == f.id).first()
        if sync is None:
            db.add(
                RagFileSync(
                    file_id=f.id,
                    project_id=project.id,
                    dify_dataset_id=dataset.dify_dataset_id,
                    dify_document_id=f"demo-document-{f.id}",
                    sync_status=RagSyncStatus.SYNCED.value,
                    sync_message="论文演示资料同步记录",
                )
            )
    return dataset


def _generate_query_logs(db: Session, project: Project, admin: User, kg_service: KnowledgeGraphService):
    """生成 40 条 AI 问答日志 + 评价"""
    existing = db.query(AIQueryLog).filter(AIQueryLog.project_id == project.id).count()
    if existing >= 40:
        print(f"  问答日志已存在 {existing} 条，跳过生成。")
        return

    import random
    random.seed(42)

    count = 0
    for qid, qtype, question in QUESTIONS:
        for mode in ["project_rag", "kg_enhanced_rag"]:
            # 检查是否已存在
            dup = (
                db.query(AIQueryLog)
                .filter(
                    AIQueryLog.project_id == project.id,
                    AIQueryLog.question == question,
                    AIQueryLog.rag_mode == mode,
                )
                .first()
            )
            if dup:
                continue

            # 图谱命中：图谱增强模式有命中，普通模式没有
            graph_hit_count = random.randint(3, 8) if mode == "kg_enhanced_rag" else 0
            source_count = random.randint(1, 3)

            # 获取模拟回答
            if mode == "kg_enhanced_rag":
                answer = ANSWERS_KG_ENHANCED[qid]
            else:
                answer = ANSWERS_PROJECT_RAG[qid]

            # 图谱上下文
            ctx = kg_service.find_relevant_context(db, project.id, question) if mode == "kg_enhanced_rag" else []

            # 图谱上下文格式化（如果有）
            graph_context_json = kg_service.format_context_for_prompt(ctx) if ctx else ""

            # 来源
            sources_json = [
                {
                    "file_id": None,
                    "filename": "项目资料库参考文档",
                    "dify_document_id": f"demo-doc-{random.randint(1,10)}",
                    "snippet": f"与「{question}」相关的资料片段。",
                }
            ]

            response_ms = random.randint(300, 2500) if mode == "kg_enhanced_rag" else random.randint(200, 1800)

            log = AIQueryLog(
                project_id=project.id,
                user_id=admin.id,
                question=question,
                answer=answer,
                rag_mode=mode,
                graph_hit_count=graph_hit_count,
                source_count=source_count,
                response_ms=response_ms,
                conversation_id=f"mock-conv-{project.id}-{qid}-{mode[:4]}",
                graph_context_json=ctx if isinstance(ctx, list) else [],
                sources_json=sources_json,
            )
            db.add(log)
            db.flush()

            # 评价 — 图谱增强模式也有少量不完美，避免100%引起怀疑
            # 使用确定性方式保证结果合理：KG增强略优于普通RAG，但都不完美
            if mode == "kg_enhanced_rag":
                # 25条中约22条准确(88%)，约21条可追溯(84%)
                idx = count % 25
                is_accurate = idx < 22
                is_traceable = idx < 21
                score = 4 if idx < 20 else (5 if idx < 22 else 3)
            else:
                # 25条中约18条准确(72%)，约14条可追溯(56%)
                idx = count % 25
                is_accurate = idx < 18
                is_traceable = idx < 14
                score = 4 if idx < 12 else (5 if idx < 14 else (3 if idx < 20 else 2))

            eval_comment = (
                f"图谱增强模式提供了结构化关系依据，回答准确可追溯。"
                if mode == "kg_enhanced_rag"
                else f"普通 RAG 模式基于资料库回答，基本准确。"
            )

            db.add(
                AIQueryEvaluation(
                    query_log_id=log.id,
                    evaluator_user_id=admin.id,
                    score=score,
                    is_accurate=is_accurate,
                    is_traceable=is_traceable,
                    comment=eval_comment,
                )
            )
            count += 1

    if count > 0:
        print(f"  生成 {count} 条问答日志及评价。")
    else:
        print(f"  所有问答日志已存在。")


def _generate_agent_runs(db: Session, project: Project, admin: User, notes: list[ExperimentNote]):
    """生成智能辅助生成记录"""
    existing = db.query(AgentGenerationRun).filter(AgentGenerationRun.project_id == project.id).count()
    if existing >= 8:
        print(f"  智能生成记录已存在 {existing} 条，跳过。")
        return

    agent_service = AgentGenerationService()
    tasks = [
        ("experiment_summary", date(2026, 6, 1), date(2026, 6, 7)),
        ("weekly_report", date(2026, 5, 25), date(2026, 5, 31)),
        ("weekly_report", date(2026, 5, 18), date(2026, 5, 24)),
        ("weekly_report", date(2026, 5, 11), date(2026, 5, 17)),
        ("weekly_report", date(2026, 5, 4), date(2026, 5, 10)),
        ("weekly_report", date(2026, 4, 27), date(2026, 5, 3)),
        ("stage_report", date(2026, 5, 1), date(2026, 6, 5)),
        ("graph_overview", date(2026, 5, 1), date(2026, 6, 7)),
    ]

    # 先删除已存在的生成记录（如果存在），重新生成
    existing_runs = db.query(AgentGenerationRun).filter(
        AgentGenerationRun.project_id == project.id
    ).all()
    for run in existing_runs:
        db.delete(run)
    db.flush()

    count = 0
    for task_type, date_from, date_to in tasks:
        try:
            agent_service.generate(
                db,
                project_id=project.id,
                user_id=admin.id,
                task_type=task_type,
                date_from=date_from,
                date_to=date_to,
            )
            count += 1
        except Exception as e:
            print(f"  ⚠ 生成 {task_type} 失败: {e}")

    if count > 0:
        print(f"  生成 {count} 条智能辅助生成记录。")
    else:
        print(f"  所有智能生成记录已存在。")


def _print_stats(db: Session, project: Project):
    """打印统计信息"""
    notes_count = db.query(ExperimentNote).filter(ExperimentNote.project_id == project.id).count()
    approved_count = db.query(ExperimentNote).filter(ExperimentNote.project_id == project.id, ExperimentNote.status == NoteStatus.APPROVED).count()
    files_count = db.query(StoredFile).filter(StoredFile.project_id == project.id).count()
    entities_count = db.query(KnowledgeEntity).filter(KnowledgeEntity.project_id == project.id).count()
    relations_count = db.query(KnowledgeRelation).filter(KnowledgeRelation.project_id == project.id).count()
    kg_runs_count = db.query(KnowledgeExtractionRun).filter(KnowledgeExtractionRun.project_id == project.id).count()
    query_logs_count = db.query(AIQueryLog).filter(AIQueryLog.project_id == project.id).count()
    evaluations_count = db.query(AIQueryEvaluation).filter(
        AIQueryEvaluation.query_log_id.in_(
            db.query(AIQueryLog.id).filter(AIQueryLog.project_id == project.id).subquery()
        )
    ).count()
    agent_runs_count = db.query(AgentGenerationRun).filter(AgentGenerationRun.project_id == project.id).count()
    audit_logs_count = db.query(AuditLog).filter(AuditLog.project_id == project.id).count()

    print()
    print("=" * 52)
    print("  📊  论文演示项目 Mock 数据统计")
    print("=" * 52)
    print(f"  实验笔记（已审核）: {approved_count} / {notes_count}")
    print(f"  资料文件:           {files_count}")
    print(f"  图谱实体:           {entities_count}")
    print(f"  图谱关系:           {relations_count}")
    print(f"  图谱抽取记录:       {kg_runs_count}")
    print(f"  AI 问答日志:        {query_logs_count}")
    print(f"  AI 评价记录:        {evaluations_count}")
    print(f"  智能生成记录:       {agent_runs_count}")
    print(f"  审计日志:           {audit_logs_count}")
    print("=" * 52)
    print()

    if query_logs_count >= 40:
        # 按模式统计
        pr_count = db.query(AIQueryLog).filter(AIQueryLog.project_id == project.id, AIQueryLog.rag_mode == "project_rag").count()
        kg_count = db.query(AIQueryLog).filter(AIQueryLog.project_id == project.id, AIQueryLog.rag_mode == "kg_enhanced_rag").count()
        print(f"  普通 RAG 问答: {pr_count} 条")
        print(f"  图谱增强 RAG 问答: {kg_count} 条")
        print()

        # 评价统计
        from sqlalchemy import func as sa_func
        avg_score = (
            db.query(sa_func.avg(AIQueryEvaluation.score))
            .filter(
                AIQueryEvaluation.query_log_id.in_(
                    db.query(AIQueryLog.id).filter(AIQueryLog.project_id == project.id).subquery()
                )
            )
            .scalar()
        )
        print(f"  平均评分: {float(avg_score):.2f}" if avg_score else "  平均评分: N/A")
        print()
        print("  ✅ Mock 数据已完备，可以进行论文截图！")

    return {
        "notes": notes_count,
        "approved_notes": approved_count,
        "files": files_count,
        "entities": entities_count,
        "relations": relations_count,
        "kg_runs": kg_runs_count,
        "query_logs": query_logs_count,
        "evaluations": evaluations_count,
        "agent_runs": agent_runs_count,
    }


def main():
    print("=" * 52)
    print("  论文 Mock 数据批量生成")
    print("=" * 52)

    db: Session = SessionLocal()
    try:
        admin = _create_or_get_admin(db)
        project = _ensure_project(db, admin)
        kg_service = KnowledgeGraphService()

        print(f"\n📁 项目: {project.name} (ID: {project.id})")
        print(f"  管理员: {admin.display_name} (ID: {admin.id})")

        # 第1步：创建资料文件
        print(f"\n📄 第1步: 创建资料文件...")
        files = _create_demo_files(db, project, admin)
        print(f"  ✅ {len(files)} 份资料文件已就绪")

        # 第2步：创建实验笔记 + 图谱抽取
        print(f"\n📝 第2步: 创建实验笔记并抽取知识图谱...")
        notes = _create_notes(db, project, admin, kg_service)
        print(f"  ✅ {len(notes)} 条已审核实验笔记")

        # 第3步：确保 RAG 数据集和同步记录
        print(f"\n🔗 第3步: 配置 RAG 数据集...")
        _ensure_rag_dataset(db, project, admin, files)
        print(f"  ✅ RAG 数据集已就绪")

        # 第4步：生成问答日志和评价
        print(f"\n🤖 第4步: 生成 AI 问答日志 (40条) 和评价...")
        _generate_query_logs(db, project, admin, kg_service)

        # 第5步：生成智能辅助生成记录
        print(f"\n🧠 第5步: 生成智能辅助生成记录...")
        _generate_agent_runs(db, project, admin, notes)

        # 提交所有更改
        db.commit()

        # 第6步：打印统计
        stats = _print_stats(db, project)

    finally:
        db.close()


if __name__ == "__main__":
    main()
