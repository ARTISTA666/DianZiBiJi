from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api import knowledge_graph
from app.api.deps import get_current_user
from app.core.database import Base, get_db
from app.models import *  # noqa: F403
from app.models.file import FileCategory, FileStatus, KnowledgeSyncStatus, StoredFile
from app.models.knowledge_graph import KnowledgeEntity, KnowledgeEntityType, KnowledgeRelation
from app.models.note import ExperimentNote, NoteStatus, NoteVersion
from app.models.project import Project, ProjectMember, ProjectRole
from app.models.user import User, UserRole
from app.services.knowledge_graph import KnowledgeGraphService


@pytest.fixture()
def test_app(tmp_path: Path, db_engine):
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)

    upload_path = tmp_path / "protocol.pdf"
    upload_path.write_text("protocol", encoding="utf-8")

    db = SessionLocal()
    db.add_all(
        [
            User(id=1, username="admin", password_hash="x", display_name="Admin", role=UserRole.SUPER_ADMIN),
            User(id=2, username="reader", password_hash="x", display_name="Reader", role=UserRole.MEMBER),
            User(id=3, username="outsider", password_hash="x", display_name="Outsider", role=UserRole.MEMBER),
            Project(id=1, name="Project A", owner_user_id=1),
            ProjectMember(project_id=1, user_id=2, project_role=ProjectRole.VIEWER, can_read=True, can_write=False),
        ]
    )
    db.flush()
    note = ExperimentNote(
        id=1,
        project_id=1,
        title="Cell viability assay",
        experiment_type="Cell assay",
        owner_user_id=1,
        status=NoteStatus.APPROVED,
    )
    db.add(note)
    db.flush()
    version = NoteVersion(
        id=1,
        note_id=1,
        version_number=1,
        fixed_fields_json={
            "reagents": ["PBS", "Trypsin"],
            "instrument": "Centrifuge",
            "sample": "Cell sample A",
            "result": "Cells remained viable",
            "cell_line": "H226",
            "condition": "control",
            "processing_software": ["TopHat2 v2.0.13", "HTSeq v0.6.1"],
            "source_accession": "GSM3035185",
        },
        content_json={
            "text": "试剂: PBS、Trypsin\n仪器: Centrifuge\n样本: Cell sample A\n结果: Cells remained viable"
        },
        created_by=1,
    )
    db.add(version)
    db.flush()
    note.current_version_id = version.id
    db.add(
        StoredFile(
            id=1,
            project_id=1,
            note_id=1,
            uploaded_by=1,
            file_category=FileCategory.NOTE_ATTACHMENT,
            original_filename="protocol.pdf",
            storage_path=str(upload_path),
            mime_type="application/pdf",
            file_size=8,
            file_hash="hash-1",
            status=FileStatus.APPROVED,
            knowledge_sync_status=KnowledgeSyncStatus.NOT_APPLICABLE.value,
        )
    )
    db.commit()
    db.close()

    active_user_id = {"value": 1}
    app = FastAPI()
    app.include_router(knowledge_graph.router)

    def override_db():
        session = SessionLocal()
        try:
            yield session
        finally:
            session.close()

    def override_user():
        session = SessionLocal()
        try:
            return session.get(User, active_user_id["value"])
        finally:
            session.close()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = override_user
    return TestClient(app), SessionLocal, active_user_id


def test_extract_note_builds_graph(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 1

    response = client.post("/notes/1/kg/extract", json={"rebuild": True})
    assert response.status_code == 200
    run = response.json()
    assert run["status"] == "completed"
    assert run["extracted_entities"] >= 8
    assert run["extracted_relations"] >= 7

    graph_response = client.get("/notes/1/kg/graph")
    assert graph_response.status_code == 200
    graph = graph_response.json()
    labels = {entity["label"] for entity in graph["entities"]}
    relation_types = {relation["relation_type"] for relation in graph["relations"]}

    assert {
        "Project A",
        "Cell viability assay",
        "Admin",
        "protocol.pdf",
        "PBS",
        "Trypsin",
        "H226",
        "control",
        "TopHat2 v2.0.13",
        "HTSeq v0.6.1",
        "GSM3035185",
    }.issubset(labels)
    assert {
        "has_note",
        "created_by",
        "has_attachment",
        "has_experiment_type",
        "uses_reagent",
        "uses_instrument",
        "uses_sample",
        "produces_result",
        "has_biological_source",
        "has_condition",
        "uses_software",
        "has_identifier",
    }.issubset(relation_types)


def test_project_rebuild_is_idempotent(test_app):
    client, SessionLocal, active_user_id = test_app
    active_user_id["value"] = 1

    assert client.post("/projects/1/kg/rebuild").status_code == 200
    with SessionLocal() as db:
        first_entity_count = db.query(KnowledgeEntity).count()
        first_relation_count = db.query(KnowledgeRelation).count()

    assert client.post("/projects/1/kg/rebuild").status_code == 200
    with SessionLocal() as db:
        assert db.query(KnowledgeEntity).count() == first_entity_count
        assert db.query(KnowledgeRelation).count() == first_relation_count


def test_entity_normalization_unifies_width_case_and_punctuation(test_app):
    _, SessionLocal, _ = test_app
    service = KnowledgeGraphService()

    with SessionLocal() as db:
        legacy = KnowledgeEntity(
            project_id=1,
            entity_type=KnowledgeEntityType.REAGENT.value,
            label="Ｔａｑ-DNA Polymerase",
            normalized_label="ｔａｑ-dna polymerase",
            natural_key="reagent:ｔａｑ-dna polymerase",
            properties={},
        )
        db.add(legacy)
        db.flush()
        second = service._upsert_entity(
            db,
            1,
            KnowledgeEntityType.REAGENT,
            "taq DNA polymerase",
        )

        assert legacy.id == second.id
        assert second.normalized_label == "taq dna polymerase"
        assert second.natural_key == "reagent:taq dna polymerase"
        assert db.query(KnowledgeEntity).filter(KnowledgeEntity.entity_type == "reagent").count() == 1


def test_collection_query_expands_graph_context_limit(test_app):
    _, SessionLocal, _ = test_app
    service = KnowledgeGraphService()

    with SessionLocal() as db:
        project_entity = KnowledgeEntity(
            id=100,
            project_id=1,
            entity_type="project",
            label="Project A",
            normalized_label="project a",
            natural_key="project:project:1",
            source_type="project",
            source_id=1,
            properties={},
        )
        db.add(project_entity)
        db.flush()
        for index in range(1, 16):
            db.add(
                ExperimentNote(
                    id=index + 100,
                    project_id=1,
                    title=f"Approved note {index}",
                    experiment_type="assay",
                    owner_user_id=1,
                    status=NoteStatus.APPROVED,
                )
            )
            note_entity = KnowledgeEntity(
                id=100 + index,
                project_id=1,
                entity_type="note",
                label=f"Approved note {index}",
                normalized_label=f"approved note {index}",
                natural_key=f"note:note:{index + 100}",
                source_type="note",
                source_id=index + 100,
                properties={},
            )
            db.add(note_entity)
            db.flush()
            db.add(
                KnowledgeRelation(
                    project_id=1,
                    source_entity_id=project_entity.id,
                    target_entity_id=note_entity.id,
                    relation_type="has_note",
                    source_type="note",
                    source_id=index + 100,
                    confidence=1.0,
                    properties={},
                )
            )
        db.commit()

        context = service.find_relevant_context(db, 1, "当前项目包含哪些已审核实验笔记？")

    assert len(context) >= 15


def test_entity_focus_excludes_same_type_relations_from_other_notes(test_app):
    _, SessionLocal, _ = test_app
    service = KnowledgeGraphService()

    with SessionLocal() as db:
        db.add_all(
            [
                ExperimentNote(id=201, project_id=1, title="PCR condition experiment", experiment_type="PCR", owner_user_id=1, status=NoteStatus.APPROVED),
                ExperimentNote(id=202, project_id=1, title="Western blot experiment", experiment_type="Western Blot", owner_user_id=1, status=NoteStatus.APPROVED),
            ]
        )
        pcr_note = KnowledgeEntity(
            project_id=1,
            entity_type="note",
            label="PCR condition experiment",
            normalized_label="pcr condition experiment",
            natural_key="note:note:201",
            source_type="note",
            source_id=201,
            properties={},
        )
        wb_note = KnowledgeEntity(
            project_id=1,
            entity_type="note",
            label="Western blot experiment",
            normalized_label="western blot experiment",
            natural_key="note:note:202",
            source_type="note",
            source_id=202,
            properties={},
        )
        taq = KnowledgeEntity(
            project_id=1,
            entity_type="reagent",
            label="Taq DNA Polymerase",
            normalized_label="taq dna polymerase",
            natural_key="reagent:taq dna polymerase",
            properties={},
        )
        ripa = KnowledgeEntity(
            project_id=1,
            entity_type="reagent",
            label="RIPA buffer",
            normalized_label="ripa buffer",
            natural_key="reagent:ripa buffer",
            properties={},
        )
        db.add_all([pcr_note, wb_note, taq, ripa])
        db.flush()
        db.add_all([
            KnowledgeRelation(
                project_id=1,
                source_entity_id=pcr_note.id,
                target_entity_id=taq.id,
                relation_type="uses_reagent",
                source_type="note_extraction",
                source_id=201,
                confidence=0.7,
                properties={},
            ),
            KnowledgeRelation(
                project_id=1,
                source_entity_id=wb_note.id,
                target_entity_id=ripa.id,
                relation_type="uses_reagent",
                source_type="note_extraction",
                source_id=202,
                confidence=0.7,
                properties={},
            ),
        ])
        db.commit()

        focused = service.find_relevant_context(db, 1, "PCR 实验用了哪些试剂？")
        all_reagents = service.find_relevant_context(db, 1, "列出所有试剂")

    assert {item["target_label"] for item in focused} == {"Taq DNA Polymerase"}
    assert {item["target_label"] for item in all_reagents} == {"Taq DNA Polymerase", "RIPA buffer"}


def test_context_focuses_group_and_prefers_requested_software_roles(test_app):
    _, SessionLocal, _ = test_app
    service = KnowledgeGraphService()
    assert service._split_terms("1 µg/mL doxycycline") == ["1 µg/mL doxycycline"]
    assert set(service._inferred_roles(KnowledgeEntityType.RESULT, "total_count=10, detected_gene_rows=8, count_matrix_gene_rows=25369")) == {
        "total_count",
        "detected_gene_rows",
        "count_matrix_gene_rows",
    }
    assert service._inferred_roles(KnowledgeEntityType.RESULT, "基因级 HTSeq 计数矩阵；不是原始 FASTQ；不据此进行差异表达显著性推断") == ["data_boundary"]
    extracted = service.extract_terms(
        {},
        {
            "text": (
                "计数摘要为 GSM3035185: total_count=53924761, detected_gene_rows=17926；"
                "count_matrix_gene_rows=25369。\n"
                "处理流程：TopHat2 比对至 GRCh37/hg19，HTSeq 生成基因级原始计数；"
                "本文仅作记录管理与检索验证，不据此进行差异表达显著性推断。"
            )
        },
    )
    assert "count_matrix_gene_rows=25369" in extracted[KnowledgeEntityType.RESULT]
    assert {
        "基因级 HTSeq 计数矩阵",
        "不是原始 FASTQ",
        "不据此进行差异表达显著性推断",
    }.issubset(extracted[KnowledgeEntityType.RESULT])

    with SessionLocal() as db:
        db.add_all(
            [
                ExperimentNote(id=301, project_id=1, title="Control note", experiment_type="RNA-seq", owner_user_id=1, status=NoteStatus.APPROVED),
                ExperimentNote(id=302, project_id=1, title="p63 note", experiment_type="RNA-seq", owner_user_id=1, status=NoteStatus.APPROVED),
            ]
        )
        entities = [
            KnowledgeEntity(project_id=1, entity_type="note", label="Control note", normalized_label="control note", natural_key="note:note:301", source_type="note", source_id=301, properties={}),
            KnowledgeEntity(project_id=1, entity_type="note", label="p63 note", normalized_label="p63 note", natural_key="note:note:302", source_type="note", source_id=302, properties={}),
            KnowledgeEntity(project_id=1, entity_type="condition", label="Control", normalized_label="control", natural_key="condition:control", properties={}),
            KnowledgeEntity(project_id=1, entity_type="condition", label="p63_knockdown", normalized_label="p63_knockdown", natural_key="condition:p63 knockdown", properties={}),
            KnowledgeEntity(project_id=1, entity_type="identifier", label="SRX-CONTROL", normalized_label="srx-control", natural_key="identifier:srx control", properties={}),
            KnowledgeEntity(project_id=1, entity_type="identifier", label="SRX-P63", normalized_label="srx-p63", natural_key="identifier:srx p63", properties={}),
            KnowledgeEntity(project_id=1, entity_type="software", label="TopHat2 v2.0.13", normalized_label="tophat2 v2.0.13", natural_key="software:tophat2", properties={}),
            KnowledgeEntity(project_id=1, entity_type="software", label="HTSeq v0.6.1", normalized_label="htseq v0.6.1", natural_key="software:htseq", properties={}),
            KnowledgeEntity(project_id=1, entity_type="software", label="FASTQC v0.11.2", normalized_label="fastqc v0.11.2", natural_key="software:fastqc", properties={}),
            KnowledgeEntity(project_id=1, entity_type="software", label="SAMtools v0.1.19", normalized_label="samtools v0.1.19", natural_key="software:samtools", properties={}),
            KnowledgeEntity(project_id=1, entity_type="software", label="Picard v1.129", normalized_label="picard v1.129", natural_key="software:picard", properties={}),
            KnowledgeEntity(project_id=1, entity_type="result", label="基因级 HTSeq 计数矩阵", normalized_label="基因级 htseq 计数矩阵", natural_key="result:gene-level", properties={}),
            KnowledgeEntity(project_id=1, entity_type="result", label="不是原始 FASTQ", normalized_label="不是原始 fastq", natural_key="result:not-fastq", properties={}),
            KnowledgeEntity(project_id=1, entity_type="result", label="不据此进行差异表达显著性推断", normalized_label="不据此进行差异表达显著性推断", natural_key="result:no-de", properties={}),
        ]
        db.add_all(entities)
        db.flush()
        control_note, p63_note, control, p63, srx_control, srx_p63, top_hat, htseq, fastqc, samtools, picard, gene_level, not_fastq, no_de = entities
        db.add_all(
            [
                KnowledgeRelation(project_id=1, source_entity_id=control_note.id, target_entity_id=control.id, relation_type="has_condition", source_type="note_extraction", source_id=301, properties={"roles": ["group"]}),
                KnowledgeRelation(project_id=1, source_entity_id=p63_note.id, target_entity_id=p63.id, relation_type="has_condition", source_type="note_extraction", source_id=302, properties={"roles": ["group"]}),
                KnowledgeRelation(project_id=1, source_entity_id=control_note.id, target_entity_id=srx_control.id, relation_type="has_identifier", source_type="note_extraction", source_id=301, properties={"roles": ["sra_accession"]}),
                KnowledgeRelation(project_id=1, source_entity_id=p63_note.id, target_entity_id=srx_p63.id, relation_type="has_identifier", source_type="note_extraction", source_id=302, properties={"roles": ["sra_accession"]}),
                KnowledgeRelation(project_id=1, source_entity_id=control_note.id, target_entity_id=top_hat.id, relation_type="uses_software", source_type="note_extraction", source_id=301, properties={"roles": ["alignment_software"]}),
                KnowledgeRelation(project_id=1, source_entity_id=control_note.id, target_entity_id=htseq.id, relation_type="uses_software", source_type="note_extraction", source_id=301, properties={"roles": ["count_software"]}),
                KnowledgeRelation(project_id=1, source_entity_id=control_note.id, target_entity_id=fastqc.id, relation_type="uses_software", source_type="note_extraction", source_id=301, properties={"roles": ["processing_software"]}),
                KnowledgeRelation(project_id=1, source_entity_id=control_note.id, target_entity_id=samtools.id, relation_type="uses_software", source_type="note_extraction", source_id=301, properties={"roles": ["processing_software"]}),
                KnowledgeRelation(project_id=1, source_entity_id=control_note.id, target_entity_id=picard.id, relation_type="uses_software", source_type="note_extraction", source_id=301, properties={"roles": ["processing_software"]}),
                KnowledgeRelation(project_id=1, source_entity_id=control_note.id, target_entity_id=gene_level.id, relation_type="produces_result", source_type="note_extraction", source_id=301, properties={"roles": ["data_boundary"]}),
                KnowledgeRelation(project_id=1, source_entity_id=p63_note.id, target_entity_id=gene_level.id, relation_type="produces_result", source_type="note_extraction", source_id=302, properties={"roles": ["data_boundary"]}),
                KnowledgeRelation(project_id=1, source_entity_id=control_note.id, target_entity_id=not_fastq.id, relation_type="produces_result", source_type="note_extraction", source_id=301, properties={"roles": ["data_boundary"]}),
                KnowledgeRelation(project_id=1, source_entity_id=control_note.id, target_entity_id=no_de.id, relation_type="produces_result", source_type="note_extraction", source_id=301, properties={"roles": ["data_boundary"]}),
            ]
        )
        db.commit()

        control_context = service.find_relevant_context(db, 1, "非靶向对照组的 SRA 实验号", limit=10)
        software_context = service.find_relevant_context(db, 1, "比对软件和基因计数软件及版本", limit=2)
        pipeline_context = service.find_relevant_context(db, 1, "完整处理软件链包括哪些工具？", limit=3)
        boundary_context = service.find_relevant_context(db, 1, "数据是什么层级，不是什么 FASTQ，不能声称什么？", limit=3)

    assert {item["target_label"] for item in control_context} == {"Control", "SRX-CONTROL"}
    assert {item["target_label"] for item in software_context} == {"TopHat2 v2.0.13", "HTSeq v0.6.1"}
    assert {item["target_label"] for item in pipeline_context} == {
        "FASTQC v0.11.2",
        "SAMtools v0.1.19",
        "Picard v1.129",
    }
    assert {item["target_label"] for item in boundary_context} == {
        "基因级 HTSeq 计数矩阵",
        "不是原始 FASTQ",
        "不据此进行差异表达显著性推断",
    }

    numeric_text = service.format_context_for_prompt(
        [
            {"source_label": "n1", "source_entity_type_label": "实验笔记", "relation_label": "产生结果", "target_entity_type_label": "实验结果", "target_label": "GSM1: total_count=10, detected_gene_rows=7", "confidence": 1.0},
            {"source_label": "n2", "source_entity_type_label": "实验笔记", "relation_label": "产生结果", "target_entity_type_label": "实验结果", "target_label": "GSM2: total_count=12, detected_gene_rows=6", "confidence": 1.0},
        ],
        query="总基因计数最高的是哪个样本？",
    )
    assert "最高为 GSM2" in numeric_text
    assert "total_count=12" in numeric_text


def test_split_terms_expands_omitted_numeric_prefix_without_changing_normal_lists():
    service = KnowledgeGraphService()

    assert service._split_terms("cDNA 样本 1、2") == ["cDNA 样本 1", "cDNA 样本 2"]
    assert service._split_terms("cDNA 样本 1、2、3") == [
        "cDNA 样本 1",
        "cDNA 样本 2",
        "cDNA 样本 3",
    ]
    assert service._split_terms("PBS、Trypsin") == ["PBS", "Trypsin"]
    assert service._split_terms("1、2") == ["1", "2"]


def test_reader_can_view_graph_but_cannot_extract(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 2

    assert client.get("/projects/1/kg/graph").status_code == 200
    assert client.post("/notes/1/kg/extract", json={"rebuild": True}).status_code == 403


def test_outsider_cannot_view_graph(test_app):
    client, _, active_user_id = test_app
    active_user_id["value"] = 3

    assert client.get("/projects/1/kg/graph").status_code == 403
