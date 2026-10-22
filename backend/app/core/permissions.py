from app.models.user import Role

# Exact policy used by backend dependencies and matrix tests. No implied role inheritance.
PORTAL_ROLES: dict[str, frozenset[Role]] = {
    "citizen": frozenset({Role.CITIZEN, Role.ADMIN}),
    "officer": frozenset({Role.OFFICER, Role.ADMIN}),
    "admin": frozenset({Role.ADMIN}),
}
