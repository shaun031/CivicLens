import csv
import io
import json

from app.models.incident import IncidentError

REPORTS = {
    "citywide": "overview",
    "categories": "incidents",
    "priorities": "priorities",
    "departments": "departments",
    "officers": "officers",
    "sla": "sla",
    "backlog": "backlog",
    "hotspots": "hotspots",
}
INTELLIGENCE_REPORTS = (
    "geographic-service-comparison",
    "sla-disparity",
    "unresolved-backlog-distribution",
    "recurring-infrastructure-failures",
    "repair-verification-outcomes",
)
REPORTS.update(dict.fromkeys(INTELLIGENCE_REPORTS, "fairness"))


def safe_cell(value):
    text = "" if value is None else str(value)
    # Leading whitespace/control characters must not bypass formula-injection protection.
    index = 0
    while index < len(text) and (
        text[index].isspace() or ord(text[index]) < 32 or text[index] == "\ufeff"
    ):
        index += 1
    if text[index:].startswith(("=", "+", "-", "@")):
        return "'" + text
    return text


def report(service, kind, filters):
    if kind not in REPORTS:
        raise IncidentError(422, "Unknown allowlisted report type")
    if kind in INTELLIGENCE_REPORTS:
        if not getattr(service, "intelligence", None):
            raise IncidentError(503, "Intelligence projection is not configured")
        return service.intelligence.report(kind, filters)
    data = service.view(REPORTS[kind], filters)
    if kind == "citywide":
        rows = [
            {"metric": key, "value": data[key]}
            for key in (
                "totalComplaints",
                "totalIncidents",
                "activeIncidents",
                "resolvedIncidents",
                "unassignedIncidents",
                "criticalIncidents",
                "overdueIncidents",
                "uniqueReporters",
            )
        ]
    elif kind in ("categories", "priorities"):
        rows = data["byCategory" if kind == "categories" else "distribution"]
    elif kind == "departments":
        columns = (
            "departmentId",
            "name",
            "activeIncidents",
            "assignedIncidents",
            "awaitingOfficer",
            "inProgress",
            "critical",
            "overdue",
            "workloadUnits",
            "availableOfficers",
            "resolved",
        )
        rows = [{key: r[key] for key in columns} for r in data["items"]]
    elif kind == "officers":
        columns = (
            "officerId",
            "displayName",
            "departmentId",
            "availability",
            "assignedActiveIncidents",
            "weightedWorkload",
            "selectedWorkload",
            "capacity",
            "utilization",
            "overdue",
        )
        rows = [{key: r[key] for key in columns} for r in data["items"]]
    elif kind == "sla":
        rows = [
            {"metric": key, "value": data[key]}
            for key in (
                "overdueIncidents",
                "approachingDeadline",
                "escalationCount",
                "distinctEscalatedIncidents",
                "acknowledged",
                "unacknowledged",
            )
        ]
        for milestone in ("responseCompliance", "resolutionCompliance"):
            rows.extend(
                {"metric": milestone + "." + k, "value": v} for k, v in data[milestone].items()
            )
    elif kind == "backlog":
        rows = [{"label": "Total unique active backlog", "count": data["totalBacklog"]}] + data[
            "overlappingSubgroups"
        ]
    else:
        columns = (
            "cell",
            "incidentCount",
            "activeIncidents",
            "criticalIncidents",
            "reportCount",
            "averageCalculatedScore",
            "overdueIncidents",
        )
        rows = [{key: r[key] for key in columns} for r in data["cells"]]
    if len(rows) > 2000:
        raise IncidentError(413, "Report exceeds2000 rows; narrow scope")
    columns = (
        list(rows[0])
        if rows
        else {
            "departments": ["departmentId", "name", "activeIncidents", "workloadUnits"],
            "officers": [
                "officerId",
                "displayName",
                "departmentId",
                "weightedWorkload",
                "capacity",
                "utilization",
            ],
            "hotspots": ["cell", "incidentCount", "reportCount"],
        }.get(kind, ["label", "count"])
    )
    return {
        "title": kind.replace("-", " ").title() + " municipal report",
        "reportType": kind,
        "generatedAt": data["calculatedAt"],
        "reportingTimezone": data["reportingTimezone"],
        "filters": data["filters"],
        "window": data["window"],
        "dataFreshness": data["dataFreshness"],
        "definitions": (
            "Creation-date cohort; current canonical state. "
            "Workload is not productivity; progress is not resolution."
        ),
        "sampleSize": len(rows),
        "columns": columns,
        "rows": rows,
        "nextCursor": data.get("nextCursor"),
        "pageOnly": bool(data.get("nextCursor") or filters.cursor),
    }


def csv_report(preview):
    output = io.StringIO(newline="")
    writer = csv.writer(output, lineterminator="\r\n")
    for key in (
        "title",
        "generatedAt",
        "reportingTimezone",
        "definitions",
        "sampleSize",
        "pageOnly",
    ):
        writer.writerow([key, safe_cell(preview[key])])
    for key in ("filters", "window", "dataFreshness"):
        writer.writerow([key, safe_cell(json.dumps(preview[key], sort_keys=True))])
    writer.writerow([])
    writer.writerow(preview["columns"])
    for row in preview["rows"]:
        writer.writerow([safe_cell(row.get(key)) for key in preview["columns"]])
    value = output.getvalue().encode("utf-8-sig")
    if len(value) > 1024 * 1024:
        raise IncidentError(413, "CSV exceeds1MiB; narrow scope")
    return value
