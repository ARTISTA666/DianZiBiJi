"""Route-walking safety net: every API endpoint must require authentication.

These tests iterate over every route registered on the real application so
that a newly added endpoint can never silently ship without an auth guard:

1. A static check that ``get_current_user`` appears in the dependency tree.
2. A dynamic probe that an anonymous request is rejected with 401.

Endpoints that are intentionally public must be listed in ``PUBLIC_ROUTES``.
"""

from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.api.deps import get_current_user
from app.main import app

# (method, path) pairs that are public by design.
PUBLIC_ROUTES = {
    ("GET", "/health"),
    ("GET", "/metrics"),
    ("GET", "/ready"),
    ("POST", "/auth/login"),
}

IGNORED_METHODS = {"HEAD", "OPTIONS"}


def _api_route_targets() -> list[tuple[str, str, APIRoute]]:
    targets = []
    for route in app.routes:
        if not isinstance(route, APIRoute):
            continue
        for method in sorted(route.methods - IGNORED_METHODS):
            targets.append((method, route.path, route))
    return targets


def _uses_current_user(dependant) -> bool:
    if dependant.call is get_current_user:
        return True
    return any(_uses_current_user(sub) for sub in dependant.dependencies)


def test_public_allowlist_matches_registered_routes():
    registered = {(method, path) for method, path, _route in _api_route_targets()}
    unknown = PUBLIC_ROUTES - registered
    assert not unknown, f"PUBLIC_ROUTES contains unregistered endpoints: {sorted(unknown)}"


def test_every_endpoint_declares_an_auth_dependency():
    missing = [
        f"{method} {path}"
        for method, path, route in _api_route_targets()
        if (method, path) not in PUBLIC_ROUTES and not _uses_current_user(route.dependant)
    ]
    assert not missing, f"Endpoints without get_current_user in their dependency tree: {missing}"


def test_every_endpoint_rejects_anonymous_requests():
    client = TestClient(app)
    leaks = []
    for method, path, _route in _api_route_targets():
        if (method, path) in PUBLIC_ROUTES:
            continue
        # Substitute every path parameter with a dummy value.
        probe_path = "/".join(
            "1" if segment.startswith("{") and segment.endswith("}") else segment
            for segment in path.split("/")
        )
        response = client.request(method, probe_path)
        if response.status_code != 401:
            leaks.append(f"{method} {path} -> {response.status_code}")
    assert not leaks, f"Endpoints reachable without credentials: {leaks}"
