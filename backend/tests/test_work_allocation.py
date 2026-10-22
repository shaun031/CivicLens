from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

import pytest
from test_complaints import PASSWORD, fields, submit
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_discovery import login_staff
from test_incidents import ADMIN, correction, create

from app.algorithms.department_assignment.officer_allocator import (
    rebalance_analysis,
    recommend,
    validate_weights,
)
from app.algorithms.department_assignment.routing_engine import route
from app.models.incident import IncidentError
from app.models.user import Role
from app.schemas.auth import RegisterInput
from app.schemas.work import AssignmentAction, DepartmentAction, MembershipAction, ProgressAction


def common(**extra):
    return {
        "operationId": str(uuid4()),
        "reason": "Trusted administrator reviewed municipal work allocation",
        "confirmed": True,
        **extra,
    }


def action(repo, identity, **extra):
    state = repo.detail(identity)
    return AssignmentAction.model_validate(
        common(
            expectedIncidentVersion=state["incidentVersion"],
            expectedAssignmentVersion=state["assignment"]["version"],
            **extra,
        )
    ).model_dump(mode="json")


def officer(app):
    email = f"officer-{uuid4()}@example.com"
    user = app.state.auth_service.register(
        RegisterInput(
            display_name="Field Officer", email=email, password=PASSWORD, confirm_password=PASSWORD
        ),
        Role.OFFICER,
    )
    return user.id, email


def setup(app, client, capacity=20):
    _, incident = create(client, app)
    repo = app.state.work_service.repository
    repo.seed(common(), ADMIN)
    assert repo.process_one()["departmentId"]
    identity = incident["incidentId"]
    app.state.priority_service.calculate(identity)
    state = repo.detail(identity)
    department = state["assignment"]["departmentId"]
    user, email = officer(app)
    payload = MembershipAction.model_validate(
        common(expectedVersion=0, officerId=user, capacity=capacity)
    ).model_dump(mode="json")
    repo.save_membership(department, payload, ADMIN)
    return repo, identity, department, user, email


@pytest.mark.parametrize(
    "category,code",
    [
        ("POTHOLE", "ROAD_MAINTENANCE"),
        ("DAMAGED_ROAD", "ROAD_MAINTENANCE"),
        ("BROKEN_STREETLIGHT", "ELECTRICAL_MAINTENANCE"),
        ("GARBAGE", "SANITATION"),
        ("DRAINAGE", "DRAINAGE_MAINTENANCE"),
        ("PUBLIC_PROPERTY_DAMAGE", "PUBLIC_WORKS"),
        ("OTHER", "GENERAL_REVIEW"),
    ],
)
def test_category_routing_is_real_and_idempotent(complaint_client, complaint_app, category, code):
    client, app = complaint_client, complaint_app
    report = submit(client, fields(category=category)).json()
    incident = app.state.incident_service.ensure_singleton(report["complaintId"])
    repo = app.state.work_service.repository
    repo.seed(common(), ADMIN)
    assert repo.seed(common(), ADMIN)["added"] == []
    result = repo.process_one()
    assert result["departmentId"] == next(
        d["id"] for d in repo.departments()["items"] if d["code"] == code
    )
    assert result["officerId"] is None
    assert (result["status"] == "NEEDS_REVIEW") == (category == "OTHER")
    assert repo.process_one() is None
    assert len(repo.history(incident["incidentId"])["items"]) == 1


def test_routing_geo_ambiguity_inactive_precedence_and_determinism():
    area = {"south": 0, "north": 20, "west": 0, "east": 30}
    departments = [
        {"id": "a", "active": True, "code": "ROAD", "areas": [area]},
        {"id": "b", "active": True, "code": "ROAD2", "areas": []},
    ]
    rules = [
        {"active": True, "category": "POTHOLE", "departmentId": d, "precedence": 100}
        for d in ("a", "b")
    ]
    assert route("POTHOLE", 10, 10, departments, rules)["review"]
    rules[0]["precedence"] = 1
    result = route("POTHOLE", 10, 10, departments, rules)
    assert result["departmentId"] == "a" and result["mode"] == "RECTANGLE_COVERAGE"
    assert result == route("POTHOLE", 10, 10, departments, rules)
    assert route("POTHOLE", -10, 10, departments, rules[:1])["departmentId"] is None
    departments[0]["active"] = False
    assert route("POTHOLE", 10, 10, departments, rules[:1])["review"]


@pytest.mark.parametrize(
    "weights", [[0, 2, 3, 4], [1, 3, 2, 4], [1, 2, 3], [1, 2, 3, float("nan")]]
)
def test_workload_configuration_validated(weights):
    with pytest.raises(ValueError):
        validate_weights(weights)


@pytest.mark.parametrize(
    "changes",
    [
        {"eligibleAccount": False},
        {"active": False},
        {"availability": "ON_LEAVE"},
        {"availability": "BUSY"},
        {"availability": "UNAVAILABLE"},
        {"capacity": 1},
        {"areas": [{"south": -20, "north": -10, "west": 0, "east": 20}]},
    ],
)
def test_ineligible_officers_excluded(changes):
    candidate = {
        "officerId": "o",
        "eligibleAccount": True,
        "active": True,
        "availability": "AVAILABLE",
        "capacity": 10,
        "workload": 0,
        "areas": [],
        **changes,
    }
    assert not recommend([candidate], 2, 10, 10)["ranked"]


def test_normalized_workload_not_raw_count():
    base = {"eligibleAccount": True, "active": True, "availability": "AVAILABLE", "areas": []}
    result = recommend(
        [
            base | {"officerId": "a", "capacity": 10, "workload": 5, "activeIncidents": 2},
            base | {"officerId": "b", "capacity": 30, "workload": 7, "activeIncidents": 7},
            base | {"officerId": "c", "capacity": None, "workload": 0},
        ],
        2,
        10,
        10,
    )
    assert [r["officerId"] for r in result["ranked"]] == ["b", "a", "c"]
    assert result["ranked"][-1]["utilization"] is None


def test_assignment_progress_permissions_history_and_reassignment(complaint_client, complaint_app):
    client, app = complaint_client, complaint_app
    repo, identity, dept, user, email = setup(app, client)
    candidate = repo.detail(identity)["recommendations"]
    assert candidate["ranked"][0]["officerId"] == user and not candidate["assignmentChanged"]
    login_staff(app, client)
    payload = action(repo, identity, officerId=user)
    url = f"/api/admin/incidents/{identity}/assign-officer"
    result = client.post(url, json=payload)
    assert result.status_code == 200, result.text
    assert client.post(url, json=payload).json() == result.json()
    assert client.post(url, json=payload | {"operationId": str(uuid4())}).status_code == 409
    assert (
        client.post(
            url, json=payload | {"reason": "Different input reusing same operation ID"}
        ).status_code
        == 409
    )
    assert (
        client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code
        == 200
    )
    queue = client.get("/api/officer/incidents").json()
    assert queue["items"][0]["incidentId"] == identity
    assert client.get(f"/api/officer/incidents?officerId={user}").status_code == 422
    state = client.get(f"/api/officer/incidents/{identity}")
    assert state.status_code == 200
    assert "citizenId" not in state.text and "recommendations" not in state.json()
    data = ProgressAction.model_validate(
        common(
            expectedIncidentVersion=state.json()["incidentVersion"],
            expectedAssignmentVersion=state.json()["assignment"]["version"],
            note="Officer inspected the road surface",
            percentage=10,
        )
    ).model_dump(mode="json")
    assert client.post(f"/api/officer/incidents/{identity}/progress", json=data).status_code == 409
    started = client.post(f"/api/officer/incidents/{identity}/start", json=data)
    assert started.status_code == 200, started.text
    assert (
        client.post(f"/api/officer/incidents/{identity}/start", json=data).json() == started.json()
    )
    data |= {
        "operationId": str(uuid4()),
        "expectedAssignmentVersion": started.json()["version"],
        "percentage": 100,
    }
    assert client.post(f"/api/officer/incidents/{identity}/progress", json=data).status_code == 200
    assert app.state.incident_service.require(identity).status == "OPEN"
    assert len(client.get(f"/api/officer/incidents/{identity}/history").json()["items"]) == 2
    other, _ = officer(app)
    repo.save_membership(
        dept,
        MembershipAction.model_validate(
            common(expectedVersion=0, officerId=other, capacity=20)
        ).model_dump(mode="json"),
        ADMIN,
    )
    repo.assign(
        identity, "REASSIGN", action(repo, identity, departmentId=dept, officerId=other), ADMIN
    )
    assert client.get(f"/api/officer/incidents/{identity}").status_code == 404
    assert client.get(f"/api/officer/incidents/{identity}/history").status_code == 404
    assert client.get("/api/officer/incidents").json()["items"] == []
    assert (
        client.post(
            f"/api/officer/incidents/{identity}/progress", json=data | {"operationId": str(uuid4())}
        ).status_code
        == 404
    )
    assert repo.workload_read(user)["activeIncidents"] == 0
    assert repo.workload_read(other)["activeIncidents"] == 1


def test_atomic_rollback_and_competing_assignments(complaint_client, complaint_app):
    repo, identity, _, user, _ = setup(complaint_app, complaint_client)
    data = action(repo, identity, officerId=user)
    with repo.store.connection() as db:
        db.execute(
            "CREATE TRIGGER fail_work BEFORE INSERT ON work_history "
            "BEGIN SELECT RAISE(ABORT,'injected'); END"
        )
    with pytest.raises(IncidentError):
        repo.assign(identity, "OFFICER", data, ADMIN)
    assert repo.detail(identity)["assignment"]["officerId"] is None
    with repo.store.connection() as db:
        db.execute("DROP TRIGGER fail_work")

    def assign(payload):
        try:
            return repo.assign(identity, "OFFICER", payload, ADMIN)
        except IncidentError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(assign, [data, data | {"operationId": str(uuid4())}]))
    assert sum(isinstance(r, dict) for r in results) == 1 and 409 in results
    assert repo.workload_read(user)["activeIncidents"] == 1


def test_capacity_serialization_and_no_silent_member_or_department_stranding(
    complaint_client, complaint_app
):
    app, client = complaint_app, complaint_client
    repo, identity, dept, user, _ = setup(app, client, capacity=0.5)
    # Even LOW costs one unit; pending priorities conservatively cost four units.
    with pytest.raises(IncidentError):
        repo.assign(identity, "OFFICER", action(repo, identity, officerId=user), ADMIN)
    repo.assign(
        identity, "OFFICER", action(repo, identity, officerId=user, capacityOverride=True), ADMIN
    )
    d = repo.department_detail(dept)
    payload = DepartmentAction.model_validate(
        common(expectedVersion=d["version"], code=d["code"], name=d["name"], active=False)
    ).model_dump(mode="json")
    with pytest.raises(IncidentError):
        repo.save_department(dept, payload, ADMIN)
    member = d["officers"][0]
    with pytest.raises(IncidentError):
        repo.remove_membership(dept, user, common(expectedVersion=member["version"]), ADMIN)
    repo.assign(identity, "UNASSIGN", action(repo, identity), ADMIN)
    assert repo.remove_membership(dept, user, common(expectedVersion=member["version"]), ADMIN)
    # Exercise real ADMIN CRUD/rule/membership routes as well as repository safety checks.
    login_staff(app, client)
    body = DepartmentAction.model_validate(
        common(expectedVersion=0, code="DEMO_PARKS", name="Demonstration Parks")
    ).model_dump(mode="json")
    created = client.post("/api/admin/departments", json=body)
    assert created.status_code == 201, created.text
    new_dept = created.json()
    assert (
        client.post("/api/admin/departments", json=body | {"operationId": str(uuid4())}).status_code
        == 409
    )
    edited = client.patch(
        f"/api/admin/departments/{new_dept['id']}",
        json=body
        | {"operationId": str(uuid4()), "expectedVersion": 1, "name": "Edited Demonstration Parks"},
    )
    assert edited.status_code == 200 and edited.json()["version"] == 2
    rule = client.post(
        "/api/admin/routing-rules",
        json=common(
            expectedVersion=0,
            category="OTHER",
            departmentId=new_dept["id"],
            precedence=10,
            active=True,
        ),
    )
    assert rule.status_code == 200, rule.text
    membership = MembershipAction.model_validate(
        common(expectedVersion=0, officerId=user, capacity=None)
    ).model_dump(mode="json")
    added = client.post(f"/api/admin/departments/{new_dept['id']}/officers", json=membership)
    assert added.status_code == 200, added.text
    assert (
        client.get(f"/api/admin/departments/{new_dept['id']}/officers").json()["items"][0][
            "capacity"
        ]
        is None
    )
    removal = common(expectedVersion=1)
    url = f"/api/admin/departments/{new_dept['id']}/officers/{user}"
    removed = client.request("DELETE", url, json=removal)
    assert (
        removed.status_code == 200
        and client.request("DELETE", url, json=removal).json() == removed.json()
    )
    inactive = client.patch(
        f"/api/admin/departments/{new_dept['id']}",
        json=body | {"operationId": str(uuid4()), "expectedVersion": 2, "active": False},
    )
    assert inactive.status_code == 200 and inactive.json()["active"] is False
    history = client.get(f"/api/admin/departments/{new_dept['id']}/history").json()["items"]
    assert {"DEPARTMENT_UPDATED", "MEMBERSHIP_UPDATED", "MEMBERSHIP_REMOVED"} <= {
        h["kind"] for h in history
    }


def test_merge_and_split_clear_allocations_keep_history(complaint_client, complaint_app):
    app, client = complaint_app, complaint_client
    repo, identity, dept, user, _ = setup(app, client)
    repo.assign(identity, "OFFICER", action(repo, identity, officerId=user), ADMIN)
    report, second = create(client, app)
    repo.process_one()
    repo.assign(
        second["incidentId"], "OFFICER", action(repo, second["incidentId"], officerId=user), ADMIN
    )
    first = app.state.incident_service.require(identity).model_dump(mode="json")
    merged = app.state.incident_service.mutate("MERGE", correction(second, first), ADMIN)
    state = repo.detail(identity)["assignment"]
    assert state["officerId"] is None and state["status"] == "NEEDS_REVIEW"
    repo.process_one()
    assert repo.detail(identity)["assignment"]["status"] == "NEEDS_REVIEW"
    assert repo.workload_read(user)["activeIncidents"] == 0
    assert any(h["kind"] == "ASSIGNMENT_REVIEW_REQUIRED" for h in repo.history(identity)["items"])
    split = app.state.incident_service.mutate(
        "SPLIT", correction(merged, complaintIds=[report["complaintId"]]), ADMIN
    )
    assert repo.detail(split["incidentId"])["assignment"]["officerId"] is None
    stats = repo.queue({"limit": 50})["stats"]
    assert stats["total"] == 2 and stats["assigned"] == 0


def test_priority_changes_refresh_queue_workload_without_reassignment(
    complaint_client, complaint_app
):
    repo, identity, _, user, _ = setup(complaint_app, complaint_client)
    repo.assign(identity, "OFFICER", action(repo, identity, officerId=user), ADMIN)
    version = repo.detail(identity)["assignment"]["version"]
    before = len(repo.history(identity)["items"])
    from test_priority_workflow import action as priority_action

    p = complaint_app.state.priority_service
    p.change(identity, "OVERRIDE", priority_action(p, identity, score=95), ADMIN)
    assert repo.workload_read(user)["workload"] == 4
    assert repo.detail(identity)["assignment"]["version"] == version
    assert len(repo.history(identity)["items"]) == before


@pytest.mark.parametrize("role", [Role.CITIZEN, Role.OFFICER])
def test_nonadmin_cannot_manage_or_self_assign(complaint_client, complaint_app, role):
    _, incident = create(complaint_client, complaint_app)
    if role == Role.OFFICER:
        login_staff(complaint_app, complaint_client, role)
    for url in ("/api/admin/departments", "/api/admin/assignments", "/api/admin/officers"):
        assert complaint_client.get(url).status_code == 403
    assert complaint_client.post("/api/admin/departments/seed", json=common()).status_code == 403
    assert (
        complaint_client.post(
            f"/api/admin/incidents/{incident['incidentId']}/assign-officer",
            json=action(complaint_app.state.work_service.repository, incident["incidentId"]),
        ).status_code
        == 403
    )


def test_work_queue_cursor_changes_and_restart_persistence(complaint_client, complaint_app):
    app, client = complaint_app, complaint_client
    repo, identity, _, user, _ = setup(app, client)
    create(client, app)
    login_staff(app, client)
    response = client.get("/api/admin/assignments?limit=1")
    assert response.status_code == 200, response.text
    cursor = response.json()["nextCursor"]
    assert cursor
    assert (
        client.get("/api/admin/assignments", params={"limit": 1, "cursor": cursor}).status_code
        == 200
    )
    repo.assign(identity, "OFFICER", action(repo, identity, officerId=user), ADMIN)
    assert (
        client.get("/api/admin/assignments", params={"limit": 1, "cursor": cursor}).status_code
        == 409
    )
    from app.main import create_app

    restarted = create_app(app.state.settings)
    restarted.state.auth_service.store.initialize()
    assert (
        restarted.state.work_service.repository.detail(identity)["assignment"]["officerId"] == user
    )
    assert restarted.state.work_service.repository.workload_read(user)["activeIncidents"] == 1


def test_rebalancing_is_advisory_only_and_excludes_started_work():
    base = {
        "eligibleAccount": True,
        "active": True,
        "availability": "AVAILABLE",
        "areas": [],
        "capacity": 10,
        "activeIncidents": 2,
        "pendingPriorities": 0,
    }
    officers = [base | {"officerId": "a", "workload": 8}, base | {"officerId": "b", "workload": 0}]
    work = {
        "incidentId": "i",
        "officerId": "a",
        "status": "OFFICER_ASSIGNED",
        "units": 4,
        "latitude": 12.97,
        "longitude": 77.59,
    }
    result = rebalance_analysis(officers, [work])
    assert result["automaticTransfers"] is False
    assert result["proposals"][0]["toOfficerId"] == "b"
    assert rebalance_analysis(officers, [work | {"status": "IN_PROGRESS"}] * 60 + [work])[
        "proposals"
    ]
    assert not rebalance_analysis(officers, [work | {"status": "IN_PROGRESS"}])["proposals"]
    assert not rebalance_analysis(
        [officers[0], officers[1] | {"availability": "ON_LEAVE"}], [work]
    )["proposals"]


@pytest.mark.parametrize("role", [None, Role.CITIZEN, Role.OFFICER])
def test_all_administrative_work_paths_enforce_roles(complaint_client, complaint_app, role):
    client, app = complaint_client, complaint_app
    if role is None:
        client.post("/api/auth/logout")
    elif role == Role.OFFICER:
        login_staff(app, client, role)
    expected = 401 if role is None else 403
    identity = str(uuid4())
    routes = [
        ("GET", "/admin/departments"),
        ("GET", "/admin/departments/summary"),
        ("POST", "/admin/departments/seed"),
        ("POST", "/admin/departments"),
        ("GET", f"/admin/departments/{identity}"),
        ("PATCH", f"/admin/departments/{identity}"),
        ("GET", f"/admin/departments/{identity}/officers"),
        ("POST", f"/admin/departments/{identity}/officers"),
        ("DELETE", f"/admin/departments/{identity}/officers/{identity}"),
        ("GET", f"/admin/departments/{identity}/incidents"),
        ("GET", f"/admin/departments/{identity}/history"),
        ("GET", "/admin/routing-rules"),
        ("POST", "/admin/routing-rules"),
        ("GET", "/admin/officers"),
        ("GET", "/admin/assignments"),
        ("GET", "/admin/assignments/unassigned"),
    ]
    routes += [
        ("POST", f"/admin/incidents/{identity}/{suffix}")
        for suffix in (
            "assign-department",
            "recommend-officer",
            "assign-officer",
            "reassign",
            "unassign-officer",
        )
    ]
    routes += [
        ("GET", f"/admin/incidents/{identity}/{suffix}")
        for suffix in ("assignment", "assignment-history")
    ]
    for method, path in routes:
        response = client.request(
            method, "/api" + path, json={} if method not in ("GET",) else None
        )
        assert response.status_code == expected, (method, path, response.text)


@pytest.mark.parametrize("role", [None, Role.CITIZEN, Role.ADMIN])
def test_officer_paths_require_officer_not_administrator_role(
    complaint_client, complaint_app, role
):
    client, app = complaint_client, complaint_app
    if role is None:
        client.post("/api/auth/logout")
    elif role == Role.ADMIN:
        login_staff(app, client)
    identity = str(uuid4())
    expected = 401 if role is None else 403
    for method, path in [
        ("GET", "/officer/incidents"),
        ("GET", f"/officer/incidents/{identity}"),
        ("GET", f"/officer/incidents/{identity}/history"),
        ("POST", f"/officer/incidents/{identity}/start"),
        ("POST", f"/officer/incidents/{identity}/progress"),
        ("GET", f"/officer/incidents/{identity}/complaints/{identity}/images/{identity}"),
    ]:
        assert (
            client.request(method, "/api" + path, json={} if method == "POST" else None).status_code
            == expected
        )


def test_assignment_capacity_concurrency_is_global_and_serialized(complaint_client, complaint_app):
    app, client = complaint_app, complaint_client
    repo, identity, dept, user, _ = setup(app, client, capacity=1)
    _, other = create(client, app)
    repo.process_one()
    app.state.priority_service.calculate(other["incidentId"])
    payloads = [(i, action(repo, i, officerId=user)) for i in (identity, other["incidentId"])]

    def apply(item):
        try:
            return repo.assign(item[0], "OFFICER", item[1], ADMIN)
        except IncidentError as error:
            return error.status

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(apply, payloads))
    assert sum(isinstance(r, dict) for r in results) == 1 and 422 in results
    assert repo.workload_read(user)["workload"] == 1


def test_officer_evidence_scope_origin_and_current_eligibility(complaint_client, complaint_app):
    app, client = complaint_app, complaint_client
    repo, identity, dept, user, email = setup(app, client)
    report, unrelated = create(client, app, images=True)
    repo.assign(identity, "OFFICER", action(repo, identity, officerId=user), ADMIN)
    assert (
        client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code
        == 200
    )
    photo = report["images"][0]["imageId"]
    path = f"/api/officer/incidents/{identity}/complaints/{report['complaintId']}/images/{photo}"
    assert client.get(path).status_code == 404
    repo.process_one()
    repo.assign(
        unrelated["incidentId"],
        "OFFICER",
        action(repo, unrelated["incidentId"], officerId=user),
        ADMIN,
    )
    allowed = client.get(
        f"/api/officer/incidents/{unrelated['incidentId']}/complaints/{report['complaintId']}/images/{photo}"
    )
    assert allowed.status_code == 200 and allowed.headers["content-type"] == "image/jpeg"
    data = ProgressAction.model_validate(
        common(
            expectedIncidentVersion=repo.detail(identity)["incidentVersion"],
            expectedAssignmentVersion=repo.detail(identity)["assignment"]["version"],
            note="Field inspection before starting work",
        )
    ).model_dump(mode="json")
    assert (
        client.post(
            f"/api/officer/incidents/{identity}/start",
            json=data,
            headers={"Origin": "https://untrusted.example"},
        ).status_code
        == 403
    )
    with repo.store.connection() as db:
        db.execute("UPDATE users SET is_active=0 WHERE id=?", (user,))
    assert repo.detail(identity)["assignment"]["officerId"] is None
    assert repo.workload_read(user)["activeIncidents"] == 0
    assert client.get(f"/api/officer/incidents/{identity}").status_code in (401, 403)


def test_schema6_migration_preserves_all_existing_source_records(complaint_client, complaint_app):
    app, client = complaint_app, complaint_client
    report, incident = create(client, app, images=True)
    app.state.priority_service.calculate(incident["incidentId"])
    tables = (
        "users",
        "complaints",
        "complaint_images",
        "incidents",
        "incident_membership_events",
        "incident_audit",
        "incident_operations",
        "incident_priority",
        "priority_history",
    )
    store = app.state.auth_service.store
    with store.connection() as db:
        before = {
            table: [tuple(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
            for table in tables
        }
        triggers = db.execute(
            "SELECT name FROM sqlite_master WHERE type='trigger' AND name LIKE 'work_%'"
        ).fetchall()
        for row in triggers:
            db.execute(f'DROP TRIGGER "{row[0]}"')
        for table in (
            "work_history",
            "incident_assignments",
            "officer_memberships",
            "routing_rules",
            "departments",
            "work_meta",
        ):
            db.execute(f"DROP TABLE {table}")
        db.execute("PRAGMA user_version=6")
    store.initialize()
    with store.connection() as db:
        assert db.execute("PRAGMA user_version").fetchone()[0] == 8
        after = {
            table: [tuple(r) for r in db.execute(f"SELECT * FROM {table} ORDER BY rowid")]
            for table in tables
        }
        assert before == after
        assert db.execute("SELECT count(*) FROM incident_assignments").fetchone()[0] == 1
    assert client.get(f"/api/complaints/{report['complaintId']}").status_code == 200


def test_conservative_allocation_requires_explicit_configuration_fresh_score_and_reliable_capacity(
    complaint_client, complaint_app
):
    app, client = complaint_app, complaint_client
    repo, identity, dept, user, _ = setup(app, client)
    with pytest.raises(IncidentError):
        repo.assign(
            identity, "ROUTE", action(repo, identity, mode="CONSERVATIVE_AUTO_ASSIGN"), ADMIN
        )
    repo.settings = repo.settings.model_copy(update={"assignment_mode": "CONSERVATIVE_AUTO_ASSIGN"})
    assigned = repo.assign(
        identity, "ROUTE", action(repo, identity, mode="CONSERVATIVE_AUTO_ASSIGN"), ADMIN
    )
    assert assigned["officerId"] == user
    repo.assign(identity, "UNASSIGN", action(repo, identity), ADMIN)
    with repo.store.connection() as db:
        db.execute(
            "UPDATE incident_priority SET needs_recalculation=1 WHERE incident_id=?", (identity,)
        )
    result = repo.assign(
        identity, "ROUTE", action(repo, identity, mode="CONSERVATIVE_AUTO_ASSIGN"), ADMIN
    )
    assert result["officerId"] is None
    # The future event port reuses exact actions without enabling orchestration.
    event = {"version": 1, "incidentId": identity, "action": action(repo, identity)}
    first = app.state.work_service.route_event(event)
    assert app.state.work_service.route_event(event) == first
