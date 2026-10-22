"""Indexed bounding boxes + exact shared Haversine inside SQLite, bounded result hydration."""

from app.models.discovery import NearbyIssue, NearbyIssuePage
from app.utils.context_cursor import pack_cursor, unpack_cursor
from app.utils.geography import longitude_ranges, nearby_bounds


def radius_rows(discovery, query, category, status, limit, cursor, owner=None):
    context = {
        "provider": "sqlite-radius-v1",
        "owner": owner,
        "query": query.model_dump(),
        "category": category,
        "status": status,
    }
    key = unpack_cursor(cursor, context, (2,))
    bounds = nearby_bounds(query)
    parameters, selections = [], []

    def predicate(latitude, longitude):
        parameters.extend([bounds.minLatitude, bounds.maxLatitude])
        ranges = longitude_ranges(bounds)
        for low, high in ranges:
            parameters.extend([low, high])
        return (
            f"{latitude} BETWEEN ? AND ? AND ("
            + " OR ".join(f"{longitude} BETWEEN ? AND ?" for _ in ranges)
            + ")"
        )

    for own in [True, False] if owner is not None else [False]:
        parameters.extend([query.latitude, query.longitude])
        if own:
            select = """SELECT c.complaint_id issueId,c.title,c.category,c.status,
                c.latitude,c.longitude,
                haversine(?,?,c.latitude,c.longitude) distanceMeters,c.created_at createdAt,
                'Reported' dateLabel,1 isOwn,COALESCE(p.publication_status='PUBLISHED',0) isPublic,
                '/citizen/complaints/'||c.complaint_id detailsUrl
                FROM complaints c INDEXED BY complaints_owner_radius
                LEFT JOIN complaint_publications p USING(complaint_id)
                JOIN users u ON u.id=c.citizen_id WHERE c.citizen_id=? AND """
            parameters.append(owner)
            select += predicate("c.latitude", "c.longitude")
        else:
            select = """SELECT p.public_issue_id issueId,p.public_summary title,c.category,c.status,
                p.public_latitude latitude,p.public_longitude longitude,
                haversine(?,?,p.public_latitude,p.public_longitude) distanceMeters,
                p.published_at createdAt,'Published' dateLabel,0 isOwn,1 isPublic,
                '/issues/'||p.public_issue_id detailsUrl
                FROM complaint_publications p INDEXED BY publications_radius
                JOIN complaints c USING(complaint_id) JOIN users u ON u.id=c.citizen_id
                WHERE p.publication_status='PUBLISHED' AND """
            select += predicate("p.public_latitude", "p.public_longitude")
            if owner is not None:
                select += " AND c.citizen_id<>?"
                parameters.append(owner)
        select += (
            " AND c.status<>'REJECTED' AND u.is_active=1 AND u.is_verified=1 AND u.role='CITIZEN'"
        )
        for value, name in [(category, "category"), (status, "status")]:
            if value:
                select += f" AND c.{name}=?"
                parameters.append(value)
        selections.append(select)
    sql = "SELECT * FROM (" + " UNION ALL ".join(selections) + ") WHERE distanceMeters<=?"
    parameters.append(query.radiusMeters + 1e-7)
    if key:
        sql += " AND (distanceMeters,issueId)>(?,?)"
        parameters.extend(key)
    sql += " ORDER BY distanceMeters,issueId LIMIT ?"
    parameters.append(limit + 1)
    with discovery.store.connection() as db:
        db.execute("BEGIN")
        rows = db.execute(sql, parameters).fetchall()
    return rows[:limit], (
        pack_cursor(context, [rows[limit - 1]["distanceMeters"], rows[limit - 1]["issueId"]])
        if len(rows) > limit
        else None
    )


def citizen_page(discovery, owner, query, category, status, limit, cursor):
    rows, token = radius_rows(discovery, query, category, status, limit, cursor, owner)
    return NearbyIssuePage(
        items=[NearbyIssue.model_validate(dict(row)) for row in rows], nextCursor=token
    )
