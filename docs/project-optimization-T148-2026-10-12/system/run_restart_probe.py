"""Use the existing restart probe against only the owned dirty-source stack."""
from pathlib import Path
import importlib.util
import sys

ROOT = Path(__file__).resolve().parents[3]
spec = importlib.util.spec_from_file_location("restart_probe", ROOT / "scripts/experiments/validate_experiment_restart.py")
probe = importlib.util.module_from_spec(spec)
spec.loader.exec_module(probe)
probe.COMPOSE_WRAPPER = Path(__file__).with_name("compose-owned-shim.sh")
sys.argv = [str(probe.__file__), "--compose-file", str(ROOT / "docker-compose.e2e.yml"),
            "--compose-project", "eln-t148-e2e", "--password", "admin123",
            "--output", str(Path(__file__).with_name("restart-result.json"))]
raise SystemExit(probe.main())
