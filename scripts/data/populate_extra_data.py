"""
论文数据膨胀脚本 — 生成大量真实感数据
在已有项目19的基础上，新增项目20、21并注入数据
"""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'backend'))

from datetime import date, timedelta
from sqlalchemy.orm import Session
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models.user import User, UserRole
from app.models.project import Project, ProjectMember
from app.models.note import ExperimentNote, NoteStatus, NoteVersion, NoteApproval
from app.models.file import StoredFile, FileCategory, FileStatus, KnowledgeSyncStatus
from app.models.knowledge_graph import KnowledgeEntity, KnowledgeRelation, KnowledgeExtractionRun
from app.services.knowledge_graph import KnowledgeGraphService
from random import seed, randint, choice, random

seed(2026)

kg_service = KnowledgeGraphService()


def create_users(db):
    """创建模拟用户"""
    users_data = [
        ("zhang", "张明", UserRole.PROJECT_OWNER),
        ("li", "李华", UserRole.PROJECT_OWNER),
        ("wang", "王芳", UserRole.REVIEWER),
        ("zhao", "赵强", UserRole.GROUP_LEADER),
        ("chen", "陈静", UserRole.PROJECT_OWNER),
    ]
    created = []
    for uname, dname, role in users_data:
        u = db.query(User).filter(User.username == uname).first()
        if not u:
            u = User(username=uname, password_hash=hash_password("123456"),
                     display_name=dname, email=f"{uname}@lab.local", role=role)
            db.add(u)
            db.flush()
        created.append(u)
    return created


def ensure_project(db, name, desc, admin):
    p = db.query(Project).filter(Project.name == name).first()
    if not p:
        p = Project(name=name, description=desc, owner_user_id=admin.id)
        db.add(p)
        db.flush()
    return p


def add_members(db, project, users):
    for u in users:
        existing = db.query(ProjectMember).filter(
            ProjectMember.project_id == project.id,
            ProjectMember.user_id == u.id
        ).first()
        if not existing:
            pm = ProjectMember(project_id=project.id, user_id=u.id,
                               can_read=True, can_write=True,
                               can_review=(u.role in [UserRole.REVIEWER, UserRole.GROUP_LEADER]),
                               can_manage=(u.role == UserRole.GROUP_LEADER))
            db.add(pm)
    db.flush()


def create_notes_for_project(db, project, admin, notes_def):
    """批量创建笔记并抽图谱"""
    notes = []
    for ndef in notes_def:
        n = db.query(ExperimentNote).filter(
            ExperimentNote.project_id == project.id,
            ExperimentNote.title == ndef["title"]
        ).first()
        if not n:
            n = ExperimentNote(
                project_id=project.id, title=ndef["title"],
                experiment_type=ndef["experiment_type"],
                experiment_date=ndef["experiment_date"],
                owner_user_id=choice([admin.id] + [u.id for u in db.query(User).filter(User.id != admin.id).limit(3).all()]),
                status=NoteStatus.APPROVED,
            )
            db.add(n)
            db.flush()
            v = NoteVersion(note_id=n.id, version_number=1,
                            fixed_fields_json=ndef["fixed_fields"],
                            content_json={"text": ndef["content_text"]},
                            created_by=admin.id, change_summary="实验记录", is_locked=True)
            db.add(v)
            db.flush()
            n.current_version_id = v.id
            db.add(NoteApproval(note_id=n.id, version_id=v.id,
                                reviewer_user_id=admin.id, action="approved",
                                comment="审核通过"))
            db.flush()
        notes.append(n)
    # KG抽取
    for n in notes:
        try:
            kg_service.extract_note(db, n, triggered_by=admin.id, rebuild=True)
        except:
            pass
    return notes


# ========= 项目20：癌症标志物筛选 =========
P20_NOTES = [
    {"title": "血清样本采集与处理", "experiment_type": "样本处理",
     "experiment_date": date(2026, 3, 10),
     "fixed_fields": {"reagents": "EDTA抗凝管、离心管、PBS、蛋白酶抑制剂",
                      "instrument": "低温离心机、超低温冰箱",
                      "sample": "健康对照血清10例、患者血清10例",
                      "result": "血清样本无溶血、无脂血，蛋白浓度在正常范围内。"},
     "content_text": "采集空腹静脉血5mL，EDTA抗凝，4℃ 3000rpm离心15min，取上清分装冻存。"},
    {"title": "外泌体提取与鉴定", "experiment_type": "样本处理",
     "experiment_date": date(2026, 3, 12),
     "fixed_fields": {"reagents": "外泌体提取试剂盒、PBS、BCA试剂盒",
                      "instrument": "超速离心机、纳米颗粒追踪分析仪、透射电镜",
                      "sample": "血清样本20例",
                      "result": "外泌体粒径集中在30-150nm，标志蛋白CD63、CD81阳性。"},
     "content_text": "采用超速离心法提取外泌体，BCA定量后NTA检测粒径分布。"},
    {"title": "miRNA芯片筛选", "experiment_type": "PCR",
     "experiment_date": date(2026, 3, 15),
     "fixed_fields": {"reagents": "miRNA提取试剂盒、miRNA芯片、杂交液",
                      "instrument": "芯片杂交仪、芯片扫描仪",
                      "sample": "外泌体RNA样本20例",
                      "result": "筛选出表达差异>2倍的miRNA共23个，其中上调14个，下调9个。"},
     "content_text": "提取外泌体RNA，质检合格后进行miRNA芯片杂交，扫描数据分析差异表达。"},
    {"title": "qPCR验证差异miRNA", "experiment_type": "PCR",
     "experiment_date": date(2026, 3, 18),
     "fixed_fields": {"reagents": "SYBR Green Master Mix、miRNA引物、cDNA模板",
                      "instrument": "荧光定量PCR仪",
                      "sample": "候选miRNA 8个、内参U6",
                      "result": "6个miRNA的差异表达趋势与芯片一致，其中miR-21和miR-155差异最显著。"},
     "content_text": "对芯片筛选出的8个miRNA进行qPCR验证，每个样本设3个复孔。"},
    {"title": "细胞转染与功能实验", "experiment_type": "质粒构建/转染",
     "experiment_date": date(2026, 3, 22),
     "fixed_fields": {"reagents": "miR-21 mimic、inhibitor、Lipofectamine 3000",
                      "instrument": "荧光显微镜、流式细胞仪",
                      "sample": "MCF-7细胞、MDA-MB-231细胞",
                      "result": "过表达miR-21后细胞增殖率提高35%，凋亡率降低12%。"},
     "content_text": "分别在两种乳腺癌细胞中转染miR-21 mimic和inhibitor，48h后检测细胞活力和凋亡。"},
    {"title": "Western Blot验证靶蛋白", "experiment_type": "Western Blot",
     "experiment_date": date(2026, 3, 25),
     "fixed_fields": {"reagents": "PTEN抗体、p-AKT抗体、AKT抗体、GAPDH抗体",
                      "instrument": "电泳仪、转膜仪、化学发光成像系统",
                      "sample": "MCF-7细胞裂解液",
                      "result": "过表达miR-21后PTEN表达降低，p-AKT水平升高，与预测通路一致。"},
     "content_text": "分别检测PTEN、p-AKT、AKT蛋白水平，验证miR-21对PTEN/AKT通路的调控。"},
    {"title": "临床样本TCGA数据验证", "experiment_type": "PCR",
     "experiment_date": date(2026, 3, 28),
     "fixed_fields": {"reagents": "TCGA数据库分析工具、R包edgeR",
                      "instrument": "高性能计算服务器",
                      "sample": "TCGA乳腺癌数据集1080例",
                      "result": "miR-21在肿瘤组织中表达显著高于正常组织(P<0.001)，ROC曲线AUC=0.87。"},
     "content_text": "从TCGA下载乳腺癌miRNA表达数据，用edgeR进行差异分析和ROC评估。"},
    {"title": "ELISA检测炎症因子", "experiment_type": "Western Blot",
     "experiment_date": date(2026, 4, 2),
     "fixed_fields": {"reagents": "IL-6 ELISA试剂盒、TNF-α ELISA试剂盒",
                      "instrument": "酶标仪、洗板机",
                      "sample": "细胞培养上清液",
                      "result": "过表达miR-21组IL-6分泌量增加2.8倍，TNF-α增加1.9倍。"},
     "content_text": "收集转染后48h的细胞上清，按ELISA试剂盒说明操作，标准品做梯度稀释。"},
    {"title": "迁移侵袭实验", "experiment_type": "细胞培养",
     "experiment_date": date(2026, 4, 5),
     "fixed_fields": {"reagents": "Matrigel、结晶紫染液、Transwell小室",
                      "instrument": "倒置显微镜、CO2培养箱",
                      "sample": "MCF-7转染组和对照组",
                      "result": "miR-21过表达组迁移细胞数是对照组的2.3倍，侵袭细胞数是对照组的1.8倍。"},
     "content_text": "Transwell上室铺Matrigel，下室加完全培养基，24h后计数迁移和侵袭细胞。"},
    {"title": "动物体内成瘤实验", "experiment_type": "动物实验/样本处理",
     "experiment_date": date(2026, 4, 12),
     "fixed_fields": {"reagents": "Balb/c裸鼠、Matrigel、miR-21过表达细胞",
                      "instrument": "小动物活体成像系统、游标卡尺",
                      "sample": "裸鼠12只",
                      "result": "miR-21过表达组成瘤体积是对照组的2.1倍(P<0.01)，肿瘤重量增加1.8倍。"},
     "content_text": "皮下注射转染后的MCF-7细胞，每3天测量肿瘤体积，28天后处死取瘤称重。"},
]

# ========= 项目21：药物靶点验证 =========
P21_NOTES = [
    {"title": "药物亲和力测定(SPR)", "experiment_type": "Western Blot",
     "experiment_date": date(2026, 4, 8),
     "fixed_fields": {"reagents": "化合物A-G系列、PBS-Tween20、CM5芯片",
                      "instrument": "表面等离子体共振仪Biacore T200",
                      "sample": "重组靶蛋白5种",
                      "result": "化合物C对靶点3的亲和力最高(KD=8.3nM)，选择性优于其他靶点10倍以上。"},
     "content_text": "将靶蛋白偶联到CM5芯片，依次注入不同浓度化合物，拟合动力学曲线。"},
    {"title": "细胞活性抑制实验(MTT)", "experiment_type": "细胞培养",
     "experiment_date": date(2026, 4, 11),
     "fixed_fields": {"reagents": "化合物系列、MTT试剂、DMSO",
                      "instrument": "酶标仪、CO2培养箱",
                      "sample": "4种肿瘤细胞系",
                      "result": "化合物C对A549细胞的IC50=1.2μM，对HCT116的IC50=0.8μM。"},
     "content_text": "细胞种96孔板，24h后加不同浓度化合物，48h后加MTT测OD570。"},
    {"title": "细胞凋亡检测(流式)", "experiment_type": "细胞培养",
     "experiment_date": date(2026, 4, 15),
     "fixed_fields": {"reagents": "Annexin V-FITC、PI、结合缓冲液",
                      "instrument": "流式细胞仪",
                      "sample": "A549细胞",
                      "result": "化合物C处理48h后早凋比例28.5%，晚凋比例15.3%，总凋亡率43.8%。"},
     "content_text": "化合物C处理A549细胞48h，Annexin V/PI双染后流式检测凋亡比例。"},
    {"title": "细胞周期阻滞分析", "experiment_type": "细胞培养",
     "experiment_date": date(2026, 4, 18),
     "fixed_fields": {"reagents": "PI/RNase染色液、70%乙醇",
                      "instrument": "流式细胞仪、涡旋振荡器",
                      "sample": "A549细胞、HCT116细胞",
                      "result": "化合物C将A549细胞阻滞在G2/M期(G2/M比例从15%升至42%)。"},
     "content_text": "细胞经化合物C处理24h后，70%乙醇固定过夜，PI染色后流式检测周期分布。"},
    {"title": "激酶选择性 profiling", "experiment_type": "Western Blot",
     "experiment_date": date(2026, 4, 22),
     "fixed_fields": {"reagents": "激酶检测试剂盒、ATP、多肽底物",
                      "instrument": "多功能酶标仪、液体处理工作站",
                      "sample": "激酶组(50种激酶)",
                      "result": "化合物C对靶点3的IC50=4.2nM，对其他49种激酶IC50均>1μM，选择性>200倍。"},
     "content_text": "分别检测化合物C对50种激酶的抑制活性，计算IC50和选择性指数。"},
    {"title": "药物代谢稳定性实验", "experiment_type": "样本处理",
     "experiment_date": date(2026, 4, 25),
     "fixed_fields": {"reagents": "化合物C、肝微粒体、NADPH再生系统",
                      "instrument": "LC-MS/MS、恒温摇床",
                      "sample": "人肝微粒体、鼠肝微粒体",
                      "result": "化合物C在人肝微粒体中半衰期T1/2=45min，固有清除率Cl_int=12μL/min/mg。"},
     "content_text": "化合物C与肝微粒体共孵育，不同时间点取样LC-MS/MS检测剩余浓度，计算清除参数。"},
    {"title": "口服生物利用度实验", "experiment_type": "动物实验/样本处理",
     "experiment_date": date(2026, 4, 29),
     "fixed_fields": {"reagents": "化合物C(灌胃+静脉)、CMC-Na、肝素钠",
                      "instrument": "LC-MS/MS、冷冻离心机",
                      "sample": "SD大鼠12只",
                      "result": "口服生物利用度F=32%，Cmax=1.8μg/mL，Tmax=1.5h。"},
     "content_text": "SD大鼠分别灌胃和静脉注射化合物C，不同时间点采血检测药物浓度，计算药代参数。"},
    {"title": "体内药效实验(PDX模型)", "experiment_type": "动物实验/样本处理",
     "experiment_date": date(2026, 5, 6),
     "fixed_fields": {"reagents": "化合物C、溶剂对照、Matrigel",
                      "instrument": "游标卡尺、小动物成像系统",
                      "sample": "PDX荷瘤小鼠20只",
                      "result": "化合物C给药组肿瘤体积抑制率TGI=68%(P<0.01)，体重无明显下降。"},
     "content_text": "PDX模型小鼠随机分为4组，每日灌胃给药，每3天测量肿瘤体积和体重。"},
    {"title": "组织分布与H&E染色", "experiment_type": "动物实验/样本处理",
     "experiment_date": date(2026, 5, 10),
     "fixed_fields": {"reagents": "4%多聚甲醛、H&E染液、二甲苯",
                      "instrument": "组织切片机、显微镜",
                      "sample": "心肝脾肺肾肿瘤组织",
                      "result": "化合物C在肿瘤组织中浓度最高，心肝脾肺肾未见明显病理改变。"},
     "content_text": "取药代实验后各脏器组织，H&E染色后镜下观察组织形态学变化。"},
    {"title": "Western Blot验证通路抑制", "experiment_type": "Western Blot",
     "experiment_date": date(2026, 5, 14),
     "fixed_fields": {"reagents": "p-ERK抗体、ERK抗体、c-Myc抗体、β-actin抗体",
                      "instrument": "电泳仪、转膜仪、化学发光成像",
                      "sample": "肿瘤组织裂解液",
                      "result": "给药组p-ERK水平降低60%，c-Myc表达下降45%，与靶点抑制机制一致。"},
     "content_text": "提取肿瘤组织蛋白，Western Blot检测下游信号通路蛋白变化。"},
]


def main():
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        users = create_users(db)

        # === 项目20：癌症标志物筛选 ===
        proj2 = ensure_project(db, "癌症标志物筛选研究",
            "基于外泌体miRNA的乳腺癌标志物筛选与功能验证", admin)
        add_members(db, proj2, users)
        notes2 = create_notes_for_project(db, proj2, admin, P20_NOTES)
        print(f"项目20: {len(notes2)} 条笔记")

        # 资料文件
        for fname, content in [("exosome_protocol.txt", "超速离心法提取血清外泌体标准流程"),
                                ("mirna_qPCR_standard.txt", "miRNA qPCR检测标准操作程序")]:
            path = f"storage/demo/{fname}"
            sf = db.query(StoredFile).filter(StoredFile.project_id == proj2.id,
                                             StoredFile.original_filename == fname).first()
            if not sf:
                sf = StoredFile(project_id=proj2.id, uploaded_by=admin.id,
                                file_category=FileCategory.KNOWLEDGE_DOCUMENT,
                                original_filename=fname, storage_path=path,
                                mime_type="text/plain", file_size=len(content),
                                file_hash=f"demo-{fname}",
                                status=FileStatus.APPROVED,
                                knowledge_sync_status=KnowledgeSyncStatus.PENDING_SYNC.value,
                                knowledge_sync_message="等待本地向量入库")
                db.add(sf)

        # === 项目21：药物靶点验证 ===
        proj3 = ensure_project(db, "抗肿瘤化合物C的靶点验证与药效评价",
            "小分子化合物C的靶点确认、体外药效和体内药效学研究", admin)
        add_members(db, proj3, users)
        notes3 = create_notes_for_project(db, proj3, admin, P21_NOTES)
        print(f"项目21: {len(notes3)} 条笔记")

        for fname, content in [("spr_protocol.txt", "SPR亲和力测定标准流程"),
                                ("pdx_protocol.txt", "PDX模型建立与给药方案")]:
            path = f"storage/demo/{fname}"
            sf = db.query(StoredFile).filter(StoredFile.project_id == proj3.id,
                                             StoredFile.original_filename == fname).first()
            if not sf:
                sf = StoredFile(project_id=proj3.id, uploaded_by=admin.id,
                                file_category=FileCategory.KNOWLEDGE_DOCUMENT,
                                original_filename=fname, storage_path=path,
                                mime_type="text/plain", file_size=len(content),
                                file_hash=f"demo-{fname}",
                                status=FileStatus.APPROVED,
                                knowledge_sync_status=KnowledgeSyncStatus.PENDING_SYNC.value,
                                knowledge_sync_message="等待本地向量入库")
                db.add(sf)

        db.commit()

        # === 统计 ===
        for pid, pname in [(19, "KG-RAG Demo"), (proj2.id, "癌症标志物"), (proj3.id, "药物靶点")]:
            nc = db.query(ExperimentNote).filter(ExperimentNote.project_id == pid).count()
            ec = db.query(KnowledgeEntity).filter(KnowledgeEntity.project_id == pid).count()
            rc = db.query(KnowledgeRelation).filter(KnowledgeRelation.project_id == pid).count()
            print(f"  {pname}: {nc}笔记 {ec}实体 {rc}关系")

        total_notes = db.query(ExperimentNote).filter(ExperimentNote.project_id.in_([19, proj2.id, proj3.id])).count()
        total_entities = db.query(KnowledgeEntity).filter(KnowledgeEntity.project_id.in_([19, proj2.id, proj3.id])).count()
        total_relations = db.query(KnowledgeRelation).filter(KnowledgeRelation.project_id.in_([19, proj2.id, proj3.id])).count()
        print(f"\n总计: {total_notes}笔记 {total_entities}实体 {total_relations}关系")

    finally:
        db.close()


if __name__ == "__main__":
    main()
