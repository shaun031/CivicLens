from app.algorithms.priority_scoring.assessment import finite_score


def classify(score, thresholds=(40, 60, 80)):
    finite_score(score, 100)
    return ("LOW", "MEDIUM", "HIGH", "CRITICAL")[sum(score >= bound for bound in thresholds)]
