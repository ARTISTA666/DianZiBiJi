from datetime import date
from pathlib import Path

from sqlalchemy.orm import Session

from app.models.ai import AgentGenerationRun, AIQueryEvaluation, AIQueryLog
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.note import ExperimentNote, NoteApproval, NoteStatus, NoteVersion
from app.models.project import Project
from app.models.rag import ProjectRagDataset, RagFileSync, RagSyncStatus
from app.core.security import hash_password
from app.models.template import ExperimentTemplate
from app.models.user import User, UserRole
from app.services.agent import AgentGenerationService
from app.services.knowledge_graph import KnowledgeGraphService


def ensure_seed_data(db: Session) -> None:
    admin = db.query(User).filter(User.username == "admin").first()
    if not admin:
        admin = User(
            username="admin",
            password_hash=hash_password("admin123"),
            display_name="系统管理员",
            email="admin@example.local",
            role=UserRole.SUPER_ADMIN,
        )
        db.add(admin)
        db.flush()
    ensure_templates(db)
    ensure_thesis_demo_data(db, admin)
    db.commit()


def ensure_templates(db: Session) -> None:
    templates = [
        ("PCR", "PCR", ["实验目的", "样本信息", "引物信息", "反应体系", "循环条件", "电泳结果", "结论"]),
        ("Western Blot", "Western Blot", ["实验目的", "样本处理", "蛋白定量", "电泳转膜", "抗体信息", "显影结果", "结论"]),
        ("细胞培养", "细胞培养", ["细胞系", "培养基", "传代比例", "培养条件", "细胞状态", "污染检查", "下一步"]),
        ("质粒构建/转染", "质粒构建/转染", ["载体信息", "插入片段", "连接/转化", "菌检结果", "转染条件", "表达验证", "结论"]),
        ("动物实验/样本处理", "动物实验/样本处理", ["动物信息", "分组设计", "处理方案", "采样时间", "样本编号", "观察记录", "伦理备注"]),
    ]
    for name, experiment_type, fields in templates:
        exists = db.query(ExperimentTemplate).filter(ExperimentTemplate.name == name).first()
        if exists:
            continue
        db.add(
            ExperimentTemplate(
                name=name,
                experiment_type=experiment_type,
                schema_json={"fields": [{"key": field, "label": field, "type": "textarea"} for field in fields]},
                default_content_json={
                    "type": "doc",
                    "content": [
                        {"type": "heading", "attrs": {"level": 2}, "content": [{"type": "text", "text": name}]},
                        {"type": "paragraph", "content": [{"type": "text", "text": "请记录实验过程、关键观察、结果分析和下一步计划。"}]},
                    ],
                },
            )
        )


def ensure_thesis_demo_data(db: Session, admin: User) -> None:
    project = db.query(Project).filter(Project.name == "论文演示项目：KG-RAG 实验流程").first()
    if project is None:
        project = Project(
            name="论文演示项目：KG-RAG 实验流程",
            description="用于论文截图和实验章节的演示项目，覆盖实验笔记、资料库、知识图谱、RAG 问答、评价和智能体生成闭环。",
            owner_user_id=admin.id,
        )
        db.add(project)
        db.flush()

    notes_payload = [
        (
            "PCR 条件优化实验",
            "PCR",
            date(2026, 6, 3),
            {
                "reagents": "Taq DNA Polymerase、dNTP、MgCl2、模板 DNA",
                "instrument": "PCR Thermal Cycler",
                "sample": "样本 A、样本 B",
                "result": "退火温度 58℃ 时扩增条带最清晰，非特异性条带减少。",
            },
            "试剂: Taq DNA Polymerase、dNTP、MgCl2\n仪器: PCR Thermal Cycler\n样本: 样本 A、样本 B\n结果: 58℃ 条件下条带清晰。",
        ),
        (
            "细胞活力检测实验",
            "细胞培养",
            date(2026, 6, 4),
            {
                "reagents": "CCK-8、PBS、DMEM 培养基",
                "instrument": "酶标仪、CO2 培养箱",
                "sample": "处理组细胞、对照组细胞",
                "result": "处理组细胞活力较对照组下降约 18%，重复孔结果稳定。",
            },
            "试剂: CCK-8、PBS、DMEM 培养基\n仪器: 酶标仪、CO2 培养箱\n样本: 处理组细胞、对照组细胞\n结果: 细胞活力下降约 18%。",
        ),
        (
            "Western Blot 蛋白表达验证",
            "Western Blot",
            date(2026, 6, 5),
            {
                "reagents": "RIPA 裂解液、BCA 试剂盒、一抗、二抗",
                "instrument": "电泳仪、转膜仪、凝胶成像系统",
                "sample": "蛋白样本 P1、蛋白样本 P2",
                "result": "目标蛋白在处理组表达降低，内参条带稳定。",
            },
            "试剂: RIPA 裂解液、BCA 试剂盒、一抗、二抗\n仪器: 电泳仪、转膜仪、凝胶成像系统\n样本: 蛋白样本 P1、蛋白样本 P2\n结果: 处理组目标蛋白表达降低。",
        ),
    ]
    notes: list[ExperimentNote] = []
    for index, (title, experiment_type, experiment_date, fixed_fields, content_text) in enumerate(notes_payload, start=1):
        note = (
            db.query(ExperimentNote)
            .filter(ExperimentNote.project_id == project.id, ExperimentNote.title == title)
            .first()
        )
        if note is None:
            note = ExperimentNote(
                project_id=project.id,
                title=title,
                experiment_type=experiment_type,
                experiment_date=experiment_date,
                owner_user_id=admin.id,
                status=NoteStatus.APPROVED,
            )
            db.add(note)
            db.flush()
            version = NoteVersion(
                note_id=note.id,
                version_number=1,
                fixed_fields_json=fixed_fields,
                content_json={"text": content_text},
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

    demo_dir = Path("storage/demo")
    demo_dir.mkdir(parents=True, exist_ok=True)
    file_payloads = [
        ("PCR_protocol_demo.txt", "PCR 体系配置、循环条件和退火温度优化说明。"),
        ("cell_assay_reference_demo.txt", "CCK-8 检测步骤、读数要求和细胞活力统计说明。"),
    ]
    for filename, content in file_payloads:
        path = demo_dir / filename
        if not path.exists():
            path.write_text(content, encoding="utf-8")
        stored_file = (
            db.query(StoredFile)
            .filter(StoredFile.project_id == project.id, StoredFile.original_filename == filename)
            .first()
        )
        if stored_file is None:
            stored_file = StoredFile(
                project_id=project.id,
                uploaded_by=admin.id,
                file_category=FileCategory.KNOWLEDGE_DOCUMENT,
                original_filename=filename,
                storage_path=str(path),
                mime_type="text/plain",
                file_size=path.stat().st_size,
                file_hash=f"demo-{filename}",
                status=FileStatus.APPROVED,
                knowledge_sync_status=KnowledgeSyncStatus.SYNCED.value,
                knowledge_sync_message="论文演示资料已入库",
            )
            db.add(stored_file)
            db.flush()

    graph_service = KnowledgeGraphService()
    for note in notes:
        graph_service.extract_note(db, note, triggered_by=admin.id, rebuild=True)
    db.flush()

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
    for stored_file in db.query(StoredFile).filter(StoredFile.project_id == project.id, StoredFile.file_category == FileCategory.KNOWLEDGE_DOCUMENT).all():
        sync = db.query(RagFileSync).filter(RagFileSync.file_id == stored_file.id).first()
        if sync is None:
            db.add(
                RagFileSync(
                    file_id=stored_file.id,
                    project_id=project.id,
                    dify_dataset_id=dataset.dify_dataset_id,
                    dify_document_id=f"demo-document-{stored_file.id}",
                    sync_status=RagSyncStatus.SYNCED.value,
                    sync_message="论文演示资料同步记录",
                )
            )

    if db.query(AIQueryLog).filter(AIQueryLog.project_id == project.id).count() == 0:
        context = graph_service.find_relevant_context(db, project.id, "PCR 实验用了哪些试剂？")
        log = AIQueryLog(
            project_id=project.id,
            user_id=admin.id,
            question="PCR 实验用了哪些试剂？",
            answer="根据实验知识图谱，PCR 条件优化实验使用了 Taq DNA Polymerase、dNTP、MgCl2 和模板 DNA。",
            rag_mode="kg_enhanced_rag",
            graph_hit_count=len(context),
            source_count=2,
            response_ms=486,
            conversation_id="demo-conversation-1",
            graph_context_json=context,
            sources_json=[
                {"file_id": None, "filename": "PCR_protocol_demo.txt", "dify_document_id": "demo-document-1", "snippet": "PCR 体系配置、循环条件和退火温度优化说明。"}
            ],
        )
        db.add(log)
        db.flush()
        db.add(
            AIQueryEvaluation(
                query_log_id=log.id,
                evaluator_user_id=admin.id,
                score=5,
                is_accurate=True,
                is_traceable=True,
                comment="图谱依据和资料来源清晰，适合作为论文可信问答案例。",
            )
        )

    if db.query(AgentGenerationRun).filter(AgentGenerationRun.project_id == project.id).count() == 0:
        AgentGenerationService().generate(
            db,
            project_id=project.id,
            user_id=admin.id,
            task_type="weekly_report",
            date_from=date(2026, 6, 1),
            date_to=date(2026, 6, 5),
        )
