from sqlalchemy.orm import sessionmaker

from app.core.config import Settings
from app.core.database import Base
from app.models import *  # noqa: F403
from app.models.ai import AIExperimentRun, AIQueryLog
from app.models.project import Project
from app.models.user import User, UserRole
from app.services.seed import ensure_seed_data, recover_interrupted_experiment_runs


def test_startup_seed_does_not_delete_existing_ai_records(db_engine) -> None:
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)
    with SessionLocal() as db:
        db.add(User(id=1, username="scientist", password_hash="x", display_name="Scientist", role=UserRole.MEMBER))
        db.add(Project(id=1, name="Existing project", owner_user_id=1))
        db.add(
            AIQueryLog(
                id=1,
                project_id=1,
                user_id=1,
                question="existing question",
                answer="existing answer",
                conversation_id="demo-conversation-1",
            )
        )
        db.commit()

        ensure_seed_data(
            db,
            Settings(
                _env_file=None,
                seed_demo_data=False,
                bootstrap_admin_username="bootstrap-admin",
                bootstrap_admin_password="local-test-password",
            ),
        )

        assert db.get(AIQueryLog, 1) is not None
        assert db.query(Project).filter(Project.name.like("论文演示项目%" )).count() == 0
        assert db.query(User).filter(User.username == "bootstrap-admin").count() == 1


def test_startup_reconciles_and_closes_interrupted_experiment(db_engine) -> None:
    SessionLocal = sessionmaker(bind=db_engine, autoflush=False, autocommit=False, expire_on_commit=False)
    Base.metadata.create_all(bind=db_engine)
    with SessionLocal() as db:
        db.add(User(id=1, username="admin", password_hash="x", display_name="Admin", role=UserRole.SUPER_ADMIN))
        db.add(Project(id=1, name="Interrupted project", owner_user_id=1))
        db.add(
            AIExperimentRun(
                id=1,
                project_id=1,
                created_by=1,
                name="Interrupted run",
                status="running",
                total_cases=3,
            )
        )
        db.add(
            AIQueryLog(
                project_id=1,
                user_id=1,
                question="retried case",
                answer="",
                error_message="temporary failure",
                experiment_run_id=1,
                experiment_execution_order=1,
            )
        )
        db.add(
            AIQueryLog(
                project_id=1,
                user_id=1,
                question="completed case",
                answer="answer",
                experiment_run_id=1,
                experiment_execution_order=1,
            )
        )
        db.commit()

        assert recover_interrupted_experiment_runs(db) == 1
        run = db.get(AIExperimentRun, 1)
        assert run.status == "interrupted"
        assert run.completed_cases == 1
        assert run.failed_cases == 0
        assert run.summary_json["unexecuted_cases"] == 2
        assert run.completed_at is not None
        assert recover_interrupted_experiment_runs(db) == 0
