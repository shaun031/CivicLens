"""Owner overlay and 200km contracts, only on disposable fixture databases."""

import json
import math

import pytest
from fastapi.testclient import TestClient
from test_complaints import PASSWORD, fields, register_login, submit
from test_complaints import complaint_app as complaint_app
from test_complaints import complaint_client as complaint_client
from test_discovery import approval, login_staff, request_publication

from app.models.discovery import Nearby
from app.utils.geography import EARTH_METERS, haversine, nearby_bounds, regions_for_bounds

PATH = "/api/citizen/issues/nearby"
QUERY = {"latitude": 12.9716, "longitude": 77.5946}


def search(client, **changes):
    return client.get(PATH, params=QUERY | changes)


def owner_login(client):
    assert (
        client.post(
            "/api/auth/login", json={"email": "citizen@example.com", "password": PASSWORD}
        ).status_code
        == 200
    )


def test_real_submission_immediately_discoverable_only_by_owner(complaint_client, complaint_app):
    client = complaint_client
    created = submit(client).json()
    page = search(client).json()
    assert len(page["items"]) == 1 and page["nextCursor"] is None
    item = page["items"][0]
    assert item == {
        "issueId": created["complaintId"],
        "title": created["title"],
        "category": "POTHOLE",
        "status": "SUBMITTED",
        **QUERY,
        "distanceMeters": 0,
        "createdAt": created["createdAt"],
        "dateLabel": "Reported",
        "isOwn": True,
        "isPublic": False,
        "detailsUrl": "/citizen/complaints/" + created["complaintId"],
    }
    assert not set(item) & {"citizenId", "description", "images", "incidentId", "storageKey"}
    register_login(client, "other-nearby@example.com")
    assert search(client).json()["items"] == []
    assert client.get(item["detailsUrl"].replace("/citizen", "/api")).status_code == 404
    with TestClient(complaint_app) as anonymous:
        assert anonymous.get(PATH, params=QUERY).status_code == 401
        assert anonymous.get("/api/public/issues/nearby", params=QUERY).json()["items"] == []


def test_public_approval_owner_dedup_and_withdrawal(complaint_client, complaint_app):
    client = complaint_client
    created = submit(client).json()
    cid = created["complaintId"]
    request_publication(client, cid)
    login_staff(complaint_app, client)
    publication = approval(client, cid).json()
    owner_login(client)
    own = search(client).json()["items"]
    assert len(own) == 1 and own[0]["issueId"] == cid and own[0]["isPublic"]
    assert (
        own[0]["latitude"] == created["latitude"]
    )  # Owner actual point, not rounded public point.
    register_login(client, "public-viewer@example.com")
    public = search(client).json()["items"]
    assert len(public) == 1 and public[0]["issueId"] == publication["publicIssueId"]
    assert public[0]["title"] == publication["publicSummary"]
    assert public[0]["isOwn"] is False and public[0]["isPublic"] is True
    assert public[0]["dateLabel"] == "Published"
    assert public[0]["detailsUrl"] == "/issues/" + publication["publicIssueId"]
    assert cid not in json.dumps(public) and created["description"] not in json.dumps(public)
    assert client.get("/api/public/issues/nearby", params=QUERY).json()["items"]
    owner_login(client)
    request_publication(client, cid, False)
    assert search(client).json()["items"][0]["isPublic"] is False
    client.post(
        "/api/auth/login", json={"email": "public-viewer@example.com", "password": PASSWORD}
    )
    assert search(client).json()["items"] == []


@pytest.mark.parametrize(
    "changes",
    [
        {"radiusKm": 201},
        {"radiusKm": -1},
        {"radiusKm": 0},
        {"radiusKm": 1.5},
        {"latitude": 91},
        {"latitude": "nan"},
        {"longitude": 181},
        {"longitude": "inf"},
        {"limit": 101},
        {"limit": 0},
        {"citizenId": "forged"},
        {"owner": "forged"},
        {"category": "STREETLIGHT"},
        {"status": "PUBLISHED"},
        {"radiusKm": "nan"},
    ],
)
def test_invalid_query_and_client_identity_rejected(complaint_client, changes):
    assert search(complaint_client, **changes).status_code == 422


@pytest.mark.parametrize("radius", [1, 10, 50, 200])
def test_exact_radius_boundary_inside_and_outside(complaint_client, radius):
    delta = math.degrees(radius * 1000 / EARTH_METERS)
    for distance in [delta - 0.000001, delta, delta + 0.000001]:
        assert (
            submit(complaint_client, fields(latitude=str(distance), longitude="0")).status_code
            == 201
        )
    response = search(complaint_client, latitude=0, longitude=0, radiusKm=radius)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 2
    assert items[1]["distanceMeters"] == pytest.approx(radius * 1000, abs=1e-7)


@pytest.mark.parametrize(
    "latitude,longitude,other_lat,other_lon",
    [
        (0, 179.999, 0, -179.999),
        (90, 180, 89.999, -170),
        (-90, -180, -89.999, 170),
        (89.9, 179.99, 89.9, -179.99),
    ],
)
def test_dateline_and_poles(complaint_client, latitude, longitude, other_lat, other_lon):
    submit(complaint_client, fields(latitude=str(other_lat), longitude=str(other_lon)))
    response = search(complaint_client, latitude=latitude, longitude=longitude, radiusKm=200)
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert len(items) == 1
    assert items[0]["distanceMeters"] == pytest.approx(
        haversine(latitude, longitude, other_lat, other_lon)
    )
    assert (
        complaint_client.get(
            "/api/public/issues/nearby",
            params={"latitude": latitude, "longitude": longitude, "radiusMeters": 200000},
        ).status_code
        == 200
    )


def test_filters_center_pagination_and_cursor_isolation(complaint_client, complaint_app):
    client = complaint_client
    ids = [submit(client).json()["complaintId"] for _ in range(3)]
    first = search(client, limit=1).json()
    second = search(client, limit=1, cursor=first["nextCursor"]).json()
    third = search(client, limit=1, cursor=second["nextCursor"]).json()
    assert [page["items"][0]["issueId"] for page in [first, second, third]] == sorted(ids)
    assert third["nextCursor"] is None
    assert search(client, category="GARBAGE").json()["items"] == []
    assert search(client, status="RESOLVED").json()["items"] == []
    assert len(search(client, category="POTHOLE", status="SUBMITTED").json()["items"]) == 3
    assert search(client, latitude=0, longitude=0, radiusKm=200).json()["items"] == []
    for changed in [
        {"radiusKm": 200},
        {"latitude": 13},
        {"category": "POTHOLE"},
        {"status": "SUBMITTED"},
    ]:
        assert search(client, cursor=first["nextCursor"], **changed).status_code == 400
    register_login(client, "cursor-other@example.com")
    assert search(client, cursor=first["nextCursor"]).status_code == 400
    assert search(client).json()["items"] == []
    owner_login(client)
    with complaint_app.state.auth_service.store.connection() as db:
        db.execute("UPDATE complaints SET status='REJECTED' WHERE complaint_id=?", (ids[0],))
    assert len(search(client).json()["items"]) == 2


def test_latest_location_is_owner_scoped_and_skips_rejected(complaint_client, complaint_app):
    client = complaint_client
    endpoint = "/api/citizen/issues/latest-location"
    assert client.get(endpoint).json() == {"location": None}
    a = submit(client).json()
    b = submit(client, fields(latitude="13", longitude="78")).json()
    with complaint_app.state.auth_service.store.connection() as db:
        db.execute(
            "UPDATE complaints SET created_at='2030-01-01',status='REJECTED' WHERE complaint_id=?",
            (b["complaintId"],),
        )
    assert client.get(endpoint).json() == {
        "location": {"latitude": a["latitude"], "longitude": a["longitude"]}
    }
    register_login(client, "latest-other@example.com")
    assert client.get(endpoint).json() == {"location": None}


@pytest.mark.parametrize("role", ["ADMIN", "OFFICER"])
def test_staff_cannot_use_owner_overlay(complaint_client, complaint_app, role):
    owner = complaint_client.get("/api/auth/me").json()["id"]
    with complaint_app.state.auth_service.store.connection() as db:
        db.execute("UPDATE users SET role=? WHERE id=?", (role, owner))
    assert search(complaint_client).status_code == 403
    assert complaint_client.get("/api/citizen/issues/latest-location").status_code == 403


def test_large_results_use_indexes_and_bounded_sql_hydration(complaint_client, complaint_app):
    created = submit(complaint_client).json()
    store = complaint_app.state.auth_service.store
    with store.connection() as db:
        # Scale only the isolated fixture, preserving the real-service row as the template.
        columns = [row[1] for row in db.execute("PRAGMA table_info(complaints)")]
        source = dict(db.execute("SELECT * FROM complaints").fetchone())
        for i in range(2200):
            row = source | {"complaint_id": f"nearby-load-{i:04d}"}
            db.execute(
                f"INSERT INTO complaints({','.join(columns)}) "
                f"VALUES({','.join('?' for _ in columns)})",
                [row[c] for c in columns],
            )
        plan = db.execute(
            "EXPLAIN QUERY PLAN SELECT complaint_id FROM complaints "
            "INDEXED BY complaints_owner_radius WHERE citizen_id=? "
            "AND latitude BETWEEN 11 AND 15 AND longitude BETWEEN 75 AND 80",
            (created["citizenId"],),
        ).fetchall()
        assert any("complaints_owner_radius" in row[3] and "SEARCH" in row[3] for row in plan)
        pubplan = db.execute(
            "EXPLAIN QUERY PLAN SELECT public_issue_id FROM complaint_publications "
            "INDEXED BY publications_radius WHERE publication_status='PUBLISHED' "
            "AND public_latitude BETWEEN 11 AND 15"
        ).fetchall()
        assert any("publications_radius" in row[3] and "SEARCH" in row[3] for row in pubplan)
    # Local radius query is not incorrectly truncated at the older viewport 2000-candidate cap.
    page = search(complaint_client, radiusKm=200, limit=100).json()
    assert len(page["items"]) == 100 and page["nextCursor"]
    assert (
        len(
            search(complaint_client, radiusKm=200, limit=100, cursor=page["nextCursor"]).json()[
                "items"
            ]
        )
        == 100
    )
    store.initialize()  # Idempotent additive index initialization does not reset reports.
    with store.connection() as db:
        assert db.execute("SELECT COUNT(*) FROM complaints").fetchone()[0] == 2201
        assert db.execute("PRAGMA user_version").fetchone()[0] == 8


@pytest.mark.parametrize("latitude,longitude", [(0, 0), (89.9, 180), (-90, -180), (80, 30)])
def test_regional_cover_is_bounded_at_200km(latitude, longitude):
    bounds = nearby_bounds(Nearby(latitude=latitude, longitude=longitude, radiusMeters=200000))
    assert 1 <= len(regions_for_bounds(bounds)) <= 144
