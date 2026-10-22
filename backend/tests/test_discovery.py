"""Phase 5 API/privacy/search regressions on disposable databases only."""

import json
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from test_complaints import ORIGIN, PASSWORD, fields, register_login, submit
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client

from app.main import create_app
from app.models.discovery import Bounds, search_matches
from app.models.user import Role
from app.schemas.auth import RegisterInput
from app.utils.geography import cells_for_bounds, geo_cell, haversine


def login_staff(app, client, role=Role.ADMIN):
    email = f"{role.lower()}-{uuid4()}@example.com"
    app.state.auth_service.register(
        RegisterInput(
            display_name="Trusted Staff", email=email, password=PASSWORD, confirm_password=PASSWORD
        ),
        role,
    )
    assert (
        client.post("/api/auth/login", json={"email": email, "password": PASSWORD}).status_code
        == 200
    )


def request_publication(client, complaint_id, requested=True):
    return client.patch(
        f"/api/complaints/{complaint_id}/publication-request", json={"requested": requested}
    )


def approval(client, complaint_id, **changes):
    return client.patch(
        f"/api/admin/complaints/{complaint_id}/publication",
        json={
            "decision": "APPROVE",
            "publicSummary": "Road surface damage near the community junction",
            "publicLatitude": 12.971642,
            "publicLongitude": 77.594641,
            "reviewedForPrivacy": True,
            **changes,
        },
    )


def bounds(**changes):
    return {
        "minLatitude": 12.95,
        "maxLatitude": 13.00,
        "minLongitude": 77.57,
        "maxLongitude": 77.62,
        **changes,
    }


@pytest.mark.parametrize(
    "query", ["LARGE", "cyclists", "community", "LIBRARY road", "lib", "  LiBrArY  "]
)
def test_search_fields_case_prefix_and_owner(complaint_client, query):
    created = submit(complaint_client).json()
    response = complaint_client.get("/api/complaints", params={"q": query})
    assert response.status_code == 200, response.text
    assert [item["complaintId"] for item in response.json()["items"]] == [created["complaintId"]]
    register_login(complaint_client, f"other-{uuid4()}@example.com")
    assert complaint_client.get("/api/complaints", params={"q": query}).json()["items"] == []
    assert complaint_client.get("/api/complaints/summary").json()["total"] == 0


@pytest.mark.parametrize(
    "query", ["", "   ", '" OR * --', "100%_", "'; DROP TABLE users;--", "near:()", "NOT (library)"]
)
def test_search_special_characters_are_plain_text_not_syntax(complaint_client, query):
    submit(complaint_client)
    assert complaint_client.get("/api/complaints", params={"q": query}).status_code == 200
    assert complaint_client.get("/api/auth/me").status_code == 200


@pytest.mark.parametrize(
    "query",
    [
        {"q": "x" * 161},
        {"q": "hello\x00world"},
        {"category": "INVALID"},
        {"status": "PRIVATE"},
        {"reportedSeverity": "URGENT"},
        {"dateFrom": "not-a-date"},
        {"dateFrom": "2026-02-02", "dateTo": "2026-01-01"},
        {"sortBy": "DROP TABLE"},
        {"sortOrder": "sideways"},
        {"limit": 101},
        {"citizenId": "foreign"},
    ],
)
def test_invalid_search_parameters(complaint_client, query):
    assert complaint_client.get("/api/complaints", params=query).status_code == 422


def test_combined_filters_total_keyset_and_context(complaint_client, complaint_app):
    ids = [submit(complaint_client).json()["complaintId"] for _ in range(4)]
    submit(complaint_client, fields(category="GARBAGE"))
    with complaint_app.state.auth_service.store.connection() as db:
        db.execute("UPDATE complaints SET created_at='2026-10-01T12:00:00.000Z'")
    filters = {
        "q": "library",
        "category": "POTHOLE",
        "status": "SUBMITTED",
        "reportedSeverity": "HIGH",
        "dateFrom": "2026-10-01",
        "dateTo": "2026-10-01",
        "limit": 2,
    }
    first = complaint_client.get("/api/complaints", params=filters).json()
    assert first["total"] == 4 and len(first["items"]) == 2
    second = complaint_client.get(
        "/api/complaints", params={**filters, "cursor": first["nextCursor"]}
    ).json()
    found = [item["complaintId"] for item in first["items"] + second["items"]]
    assert found == sorted(ids, reverse=True) and second["nextCursor"] is None
    for changed in [
        {"q": "road"},
        {"category": "GARBAGE"},
        {"sortOrder": "asc"},
        {"dateTo": "2026-10-02"},
    ]:
        assert (
            complaint_client.get(
                "/api/complaints", params={**filters, **changed, "cursor": first["nextCursor"]}
            ).status_code
            == 400
        )
    assert (
        complaint_client.get(
            "/api/complaints", params={**filters, "reportedSeverity": "LOW"}
        ).json()["total"]
        == 0
    )
    assert (
        complaint_client.get(
            "/api/complaints", params={**filters, "dateFrom": "2026-10-02", "dateTo": "2026-10-03"}
        ).json()["items"]
        == []
    )


@pytest.mark.parametrize("sort_by", ["createdAt", "category", "status"])
@pytest.mark.parametrize("order", ["asc", "desc"])
def test_all_sort_orders_with_ties(complaint_client, sort_by, order):
    saved = [
        submit(complaint_client, fields(category=category)).json()
        for category in ["POTHOLE", "GARBAGE", "DRAINAGE", "POTHOLE"]
    ]
    expected = sorted(
        saved,
        key=lambda item: (item[sort_by], item["createdAt"], item["complaintId"]),
        reverse=order == "desc",
    )
    found, cursor = [], None
    for _ in range(4):
        page = complaint_client.get(
            "/api/complaints",
            params={
                "sortBy": sort_by,
                "sortOrder": order,
                "limit": 1,
                **({"cursor": cursor} if cursor else {}),
            },
        ).json()
        found.extend(page["items"])
        cursor = page["nextCursor"]
    assert [item["complaintId"] for item in found] == [item["complaintId"] for item in expected]


def test_unicode_fts_sync_and_safe_fallback(complaint_client, complaint_app):
    saved = submit(
        complaint_client,
        fields(
            title="Café Straße सड़क damaged path",
            landmark="École Québec",
            addressLabel="Αθήνα Square",
        ),
    ).json()
    store = complaint_app.state.auth_service.store
    queries = ["CAFE", "STRASSE", "सड़क", "éCOLE", "QUÉBEC", "Αθήνα"]
    for query in queries:
        assert complaint_client.get("/api/complaints", params={"q": query}).json()["total"] == 1
    with store.connection() as db:
        db.execute(
            "UPDATE complaints SET title='Updated footpath beside the market' WHERE complaint_id=?",
            (saved["complaintId"],),
        )
    assert complaint_client.get("/api/complaints?q=market").json()["total"] == 1
    assert complaint_client.get("/api/complaints?q=STRASSE").json()["total"] == 0
    # Simulate a SQLite build without FTS5: safely fall back to owner-scoped SQL function filtering.
    with store.connection() as db:
        db.executescript(
            "DROP TRIGGER complaints_search_insert; DROP TRIGGER complaints_search_update; "
            "DROP TRIGGER complaints_search_delete; DROP TABLE complaint_search;"
        )
    assert complaint_client.get("/api/complaints?q=MARKET").json()["total"] == 1
    assert search_matches("Café Straße", "cafe strasse")


def test_summary_aggregates_all_statuses_and_days_not_current_page(complaint_client, complaint_app):
    statuses = ["SUBMITTED", "UNDER_REVIEW", "ASSIGNED", "IN_PROGRESS", "RESOLVED", "REJECTED"]
    for status in statuses:
        saved = submit(complaint_client).json()
        with complaint_app.state.auth_service.store.connection() as db:
            db.execute(
                "UPDATE complaints SET status=? WHERE complaint_id=?",
                (status, saved["complaintId"]),
            )
    summary = complaint_client.get("/api/complaints/summary?days=7").json()
    assert summary["total"] == 6 and summary["counts"] == dict.fromkeys(statuses, 1)
    assert summary["byCategory"] == [{"category": "POTHOLE", "count": 6}]
    assert len(summary["recent"]) == 3 and summary["recentActivity"] == []
    assert (
        len(summary["submissionTrend"]) == 7
        and sum(item["count"] for item in summary["submissionTrend"]) == 6
    )
    assert summary["submissionTrend"][-1]["date"] == str(datetime.now(UTC).date())
    assert complaint_client.get("/api/complaints?limit=1").json()["total"] == 6
    register_login(complaint_client, "empty-account@example.com")
    empty = complaint_client.get("/api/complaints/summary").json()
    assert (
        empty["total"] == 0
        and empty["counts"] == {}
        and empty["byCategory"] == empty["submissionTrend"] == []
    )


def test_publication_workflow_privacy_and_atomic_audit(complaint_client, complaint_app):
    client = complaint_client
    saved = submit(client).json()
    cid = saved["complaintId"]
    assert saved["publication"]["publicationStatus"] == "PRIVATE"
    assert client.get("/api/public/issues", params=bounds()).json()["items"] == []
    assert request_publication(client, cid).json()["publicationStatus"] == "PENDING_REVIEW"
    assert approval(client, cid).status_code == 403
    assert client.get("/api/public/issues", params=bounds()).json()["items"] == []
    login_staff(complaint_app, client)
    published = approval(client, cid)
    assert published.status_code == 200, published.text
    public_id = published.json()["publicIssueId"]
    assert public_id != cid and published.json()["publicLatitude"] == 12.972
    public = client.get("/api/public/issues", params=bounds()).json()["items"][0]
    assert set(public) == {
        "publicIssueId",
        "category",
        "status",
        "summary",
        "latitude",
        "longitude",
        "publishedAt",
    }
    assert not any(
        secret in json.dumps(public)
        for secret in [
            saved["citizenId"],
            saved["description"],
            cid,
            "storageKey",
            "images",
            "email",
        ]
    )
    assert client.get(f"/api/public/issues/{public_id}").json() == public
    with TestClient(complaint_app, base_url="http://localhost:8000") as anonymous:
        assert anonymous.get(f"/api/public/issues/{public_id}").json() == public
        assert anonymous.get(f"/api/complaints/{cid}").status_code == 401
    with complaint_app.state.auth_service.store.connection() as db:
        actions = [
            row[0]
            for row in db.execute(
                "SELECT action FROM publication_audit ORDER BY created_at,event_id"
            )
        ]
        assert set(actions) == {"REQUEST", "APPROVE"}
    assert (
        client.patch(
            f"/api/admin/complaints/{cid}/publication", json={"decision": "UNPUBLISH"}
        ).status_code
        == 200
    )
    assert client.get("/api/public/issues", params=bounds()).json()["items"] == []
    assert client.get(f"/api/public/issues/{public_id}").status_code == 404


def test_citizen_withdraws_published_entry_and_other_owner_cannot_request(
    complaint_client, complaint_app
):
    client = complaint_client
    cid = submit(client).json()["complaintId"]
    request_publication(client, cid)
    login_staff(complaint_app, client)
    published = approval(client, cid).json()
    assert (
        client.post(
            "/api/auth/login", json={"email": "citizen@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )
    assert request_publication(client, cid, False).json()["publicationStatus"] == "PRIVATE"
    assert client.get(f"/api/public/issues/{published['publicIssueId']}").status_code == 404
    register_login(client, "citizen-b@example.com")
    assert request_publication(client, cid).status_code == 404
    assert client.get(f"/api/complaints/{cid}").status_code == 404


@pytest.mark.parametrize(
    "changes",
    [
        {"reviewedForPrivacy": False},
        {"publicSummary": "Email someone@example.com to report"},
        {"publicSummary": "Call +91 9988776655 at the gate"},
        {"publicSummary": "<script>unsafe public summary</script>"},
        {"publicSummary": "short"},
        {"publicLatitude": 91},
        {"publicLongitude": -181},
        {"citizenId": "fake"},
    ],
)
def test_unsafe_approval_rejected(complaint_client, complaint_app, changes):
    cid = submit(complaint_client).json()["complaintId"]
    request_publication(complaint_client, cid)
    login_staff(complaint_app, complaint_client)
    assert approval(complaint_client, cid, **changes).status_code == 422


def test_officer_anonymous_and_no_consent_review_rejected(complaint_client, complaint_app):
    cid = submit(complaint_client).json()["complaintId"]
    login_staff(complaint_app, complaint_client, Role.OFFICER)
    assert approval(complaint_client, cid).status_code == 403
    login_staff(complaint_app, complaint_client)
    assert approval(complaint_client, cid).status_code == 409
    complaint_client.cookies.clear()
    assert approval(complaint_client, cid).status_code == 401
    assert complaint_client.get("/api/complaints?q=library").status_code == 401
    assert complaint_client.get("/api/complaints/summary").status_code == 401


def test_rejection_and_csrf_remain_enforced(complaint_client, complaint_app):
    cid = submit(complaint_client).json()["complaintId"]
    assert (
        complaint_client.patch(
            f"/api/complaints/{cid}/publication-request",
            json={"requested": True},
            headers={"Origin": "https://hostile.example"},
        ).status_code
        == 403
    )
    assert (
        complaint_client.patch(
            f"/api/complaints/{cid}/publication-request",
            json={"requested": True, "publicationStatus": "PUBLISHED"},
        ).status_code
        == 422
    )
    request_publication(complaint_client, cid)
    login_staff(complaint_app, complaint_client)
    assert (
        complaint_client.patch(
            f"/api/admin/complaints/{cid}/publication", json={"decision": "REJECT"}
        ).json()["publicationStatus"]
        == "REJECTED"
    )
    assert complaint_client.get("/api/public/issues", params=bounds()).json()["items"] == []


@pytest.mark.parametrize(
    "query",
    [
        {},
        bounds(minLatitude=91),
        bounds(maxLongitude=181),
        bounds(minLatitude=13.1, maxLatitude=13),
        bounds(maxLongitude=80),
        bounds(limit=101),
        bounds(minLongitude=77.6, maxLongitude=77.6),
    ],
)
def test_invalid_unbounded_or_oversized_public_regions(complaint_client, query):
    assert complaint_client.get("/api/public/issues", params=query).status_code == 422


@pytest.mark.parametrize(
    "query",
    [
        {},
        {"latitude": 91, "longitude": 0},
        {"latitude": 0, "longitude": 0, "radiusMeters": 200001},
        {"latitude": 0, "longitude": 0, "radiusMeters": 0},
        {"latitude": "nan", "longitude": 0},
        {"latitude": 90, "longitude": 181},
    ],
)
def test_invalid_radius_parameters(complaint_client, query):
    assert complaint_client.get("/api/public/issues/nearby", params=query).status_code == 422


def test_geographic_pages_nearby_distances_and_context(complaint_client, complaint_app):
    ids = [submit(complaint_client).json()["complaintId"] for _ in range(3)]
    for cid in ids:
        request_publication(complaint_client, cid)
    login_staff(complaint_app, complaint_client)
    for index, cid in enumerate(ids):
        assert (
            approval(complaint_client, cid, publicLatitude=12.972 + index * 0.003).status_code
            == 200
        )
    first = complaint_client.get("/api/public/issues", params=bounds(limit=1)).json()
    second = complaint_client.get(
        "/api/public/issues", params=bounds(limit=1, cursor=first["nextCursor"])
    ).json()
    assert first["items"][0]["publicIssueId"] < second["items"][0]["publicIssueId"]
    assert (
        complaint_client.get(
            "/api/public/issues",
            params=bounds(limit=1, cursor=first["nextCursor"], category="GARBAGE"),
        ).status_code
        == 400
    )
    nearby = complaint_client.get(
        "/api/public/issues/nearby",
        params={"latitude": 12.972, "longitude": 77.595, "radiusMeters": 500, "limit": 1},
    ).json()
    assert nearby["items"][0]["distanceMeters"] == pytest.approx(0)
    assert nearby["nextCursor"]
    next_page = complaint_client.get(
        "/api/public/issues/nearby",
        params={
            "latitude": 12.972,
            "longitude": 77.595,
            "radiusMeters": 500,
            "limit": 1,
            "cursor": nearby["nextCursor"],
        },
    ).json()
    assert 300 < next_page["items"][0]["distanceMeters"] < 350
    assert (
        len(
            complaint_client.get(
                "/api/public/issues/nearby",
                params={"latitude": 12.972, "longitude": 77.595, "radiusMeters": 500},
            ).json()["items"]
        )
        == 2
    )


def test_haversine_dateline_and_neighboring_cells():
    assert haversine(0, 0, 0, 0) == 0
    assert haversine(0, 0, 0, 1) == pytest.approx(111195.08, abs=1)
    assert haversine(0, 179.999, 0, -179.999) == pytest.approx(222.39, abs=1)
    assert haversine(90, 0, -90, 0) == pytest.approx(20015114.44, abs=1)
    box = Bounds(minLatitude=-0.01, maxLatitude=0.01, minLongitude=179.99, maxLongitude=-179.99)
    cells = cells_for_bounds(box)
    assert geo_cell(0, 179.999) in cells and geo_cell(0, -179.999) in cells
    assert geo_cell(0, 180) == geo_cell(0, -180)


def test_public_rate_limit_persists_and_failure_is_safe(
    complaint_client, complaint_app, monkeypatch
):
    complaint_app.state.settings.public_query_rate_limit = 2
    for _ in range(2):
        assert complaint_client.get("/api/public/issues", params=bounds()).status_code == 200
    response = complaint_client.get("/api/public/issues", params=bounds())
    assert response.status_code == 429 and response.headers["Retry-After"]


def test_publication_survives_app_restart_and_account_data_preserved(
    complaint_client, complaint_app
):
    cid = submit(complaint_client).json()["complaintId"]
    request_publication(complaint_client, cid)
    login_staff(complaint_app, complaint_client)
    public_id = approval(complaint_client, cid).json()["publicIssueId"]
    with TestClient(
        create_app(complaint_app.state.settings), base_url="http://localhost:8000", headers=ORIGIN
    ) as restarted:
        assert restarted.get(f"/api/public/issues/{public_id}").status_code == 200
        assert (
            restarted.post(
                "/api/auth/login", json={"email": "citizen@example.com", "password": PASSWORD}
            ).status_code
            == 200
        )
        assert (
            restarted.get(f"/api/complaints/{cid}").json()["publication"]["publicationStatus"]
            == "PUBLISHED"
        )


def test_failed_audit_rolls_back_publication_and_returns_safe_error(
    complaint_client, complaint_app
):
    cid = submit(complaint_client).json()["complaintId"]
    request_publication(complaint_client, cid)
    login_staff(complaint_app, complaint_client)
    with complaint_app.state.auth_service.store.connection() as db:
        db.execute(
            "CREATE TRIGGER refuse_audit BEFORE INSERT ON publication_audit "
            "BEGIN SELECT RAISE(ABORT,'private failure payload'); END"
        )
    response = approval(complaint_client, cid)
    assert response.status_code == 503 and "private failure payload" not in response.text
    assert complaint_client.get("/api/public/issues", params=bounds()).json()["items"] == []
    with complaint_app.state.auth_service.store.connection() as db:
        assert (
            db.execute("SELECT publication_status FROM complaint_publications").fetchone()[0]
            == "PENDING_REVIEW"
        )
        assert db.execute("SELECT COUNT(*) FROM publication_audit").fetchone()[0] == 1


def test_public_dateline_bounds_and_radius_match_both_sides(complaint_client, complaint_app):
    ids = [submit(complaint_client).json()["complaintId"] for _ in range(2)]
    for cid in ids:
        request_publication(complaint_client, cid)
    login_staff(complaint_app, complaint_client)
    for cid, longitude in zip(ids, [179.999, -179.999], strict=True):
        assert (
            approval(complaint_client, cid, publicLatitude=0, publicLongitude=longitude).status_code
            == 200
        )
    crossing = {
        "minLatitude": -0.01,
        "maxLatitude": 0.01,
        "minLongitude": 179.99,
        "maxLongitude": -179.99,
    }
    assert len(complaint_client.get("/api/public/issues", params=crossing).json()["items"]) == 2
    radius = complaint_client.get(
        "/api/public/issues/nearby", params={"latitude": 0, "longitude": 180, "radiusMeters": 250}
    ).json()["items"]
    assert len(radius) == 2 and all(110 < item["distanceMeters"] < 112 for item in radius)


def test_candidate_cap_refuses_partial_geographic_success(complaint_client, complaint_app):
    from app.scripts.benchmark_phase5 import seed

    seed(complaint_app.state.auth_service.store, 2000)
    complaint_app.state.settings.discovery_candidate_limit = 100
    response = complaint_client.get("/api/public/issues", params=bounds())
    assert response.status_code == 422 and "Too many geographic candidates" in response.text


def test_standard_access_logging_removes_search_and_gps_query_strings():
    import logging

    from app.core.logging import QueryPrivacyFilter

    record = logging.LogRecord(
        "uvicorn.access",
        logging.INFO,
        "",
        1,
        '%s - "%s %s HTTP/%s" %d',
        (
            "connection",
            "GET",
            "/api/public/issues/nearby?latitude=12.345678&longitude=77.123456",
            "1.1",
            200,
        ),
        None,
    )
    QueryPrivacyFilter().filter(record)
    assert (
        "latitude=" not in record.getMessage()
        and "/api/public/issues/nearby" in record.getMessage()
    )
    httpx_record = logging.LogRecord(
        "httpx",
        logging.INFO,
        "",
        1,
        'HTTP Request: %s %s "%s %s"',
        ("GET", "http://localhost/api/complaints?q=privateword", "HTTP/1.1", 200),
        None,
    )
    QueryPrivacyFilter().filter(httpx_record)
    assert "privateword" not in httpx_record.getMessage()
