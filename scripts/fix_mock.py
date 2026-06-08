# encoding: utf-8
import sys
sys.stdout.reconfigure(encoding='utf-8')

with open('scripts/populate_mock_data.py', 'r', encoding='utf-8') as f:
    content = f.read()

# Add Q21-Q25 to QUESTIONS list
old_q = '    ("Q20", "综合总结型", "根据当前实验记录，项目下一步可以重点复核哪些结果？"),'
new_q = old_q + '\n    ("Q21", "资料事实型", "项目资料库中已经审核通过的实验方案有哪些？"),\n    ("Q22", "实验对象关系型", "质粒构建实验使用了哪些工具酶？"),\n    ("Q23", "过程追溯型", "细胞凋亡检测的结果来自哪次实验？"),\n    ("Q24", "综合总结型", "项目中涉及的细胞实验可以按类型如何划分？"),\n    ("Q25", "资料事实型", "Western Blot 实验的标准流程在哪份资料中有详细说明？"),'
content = content.replace(old_q, new_q)

# Add Q21-Q25 to ANSWERS_PROJECT_RAG
old_pr = '"Q20": "建议进一步验证退火温度 58\u2103 条件的可重复性，并完善 Western Blot 的定量分析。"'
new_pr = old_pr + ',\n    "Q21": "项目中有PCR实验方案、细胞活力检测方案、细胞培养标准和Western Blot流程等资料。",\n    "Q22": "根据资料库文档，质粒构建使用EcoRI和HindIII两种限制性内切酶。",\n    "Q23": "根据实验笔记记录，细胞凋亡检测的结果来自5月15日的Annexin V-FITC/PI双染实验。",\n    "Q24": "项目中的细胞实验包括细胞活力检测、细胞传代冻存、细胞凋亡检测和克隆形成实验。",\n    "Q25": "Western Blot的标准流程在western_blot_protocol.txt资料中有详细说明。"'
content = content.replace(old_pr, new_pr)

# Add Q21-Q25 to ANSWERS_KG_ENHANCED
old_kg = '"Q20": "综合图谱分析，项目已覆盖 PCR 优化、细胞活力和蛋白验证三个方向。建议补充退火温度验证实验的重复记录，并完善 Western Blot 定量分析的笔记记录。"'
new_kg = old_kg + ',\n    "Q21": "图谱显示项目实体关联了多份资料文件，包括PCR方案、细胞培养标准和WB流程等。",\n    "Q22": "知识图谱中质粒构建实验节点通过使用试剂关系关联了EcoRI和HindIII两种内切酶。",\n    "Q23": "图谱显示细胞凋亡检测实验节点通过产生结果关联了凋亡比例结果实体。",\n    "Q24": "按实验类型分组，图谱显示项目包含PCR、细胞培养、Western Blot和质粒构建四类实验。",\n    "Q25": "知识图谱中WB相关节点关联了电泳仪、转膜仪和一抗二抗等试剂实体的详细信息。"'
content = content.replace(old_kg, new_kg)

with open('scripts/populate_mock_data.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Updated OK')
