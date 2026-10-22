from app.models.complaint import Category


def compatibility(first: Category, second: Category, allow_related: bool = True) -> str:
    if first == second:
        return "CONSERVATIVE_OTHER" if first == Category.OTHER else "SAME_CATEGORY"
    if allow_related and {first, second} == {Category.POTHOLE, Category.DAMAGED_ROAD}:
        return "RELATED_CATEGORY"
    return "INCOMPATIBLE"


def compatible_categories(category: Category, allow_related: bool = True) -> tuple[Category, ...]:
    return tuple(
        item for item in Category if compatibility(category, item, allow_related) != "INCOMPATIBLE"
    )
