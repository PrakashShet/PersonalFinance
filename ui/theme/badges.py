"""Shared badge colour maps for entity tiles across views."""

FALLBACK_BADGE = ("rgba(201, 170, 122, 0.18)", "#d2b98f")

INCOME_SOURCE_BADGE: dict[str, tuple[str, str]] = {
    "salary":    ("rgba(16, 185, 129, 0.16)", "#6ee7b7"),
    "web_app":   ("rgba(59, 130, 246, 0.16)", "#93c5fd"),
    "trading":   ("rgba(245, 158, 11, 0.16)", "#fbbf24"),
    "rental":    ("rgba(139, 92, 246, 0.16)", "#c4b5fd"),
    "freelance": ("rgba(236, 72, 153, 0.16)", "#f9a8d4"),
    "dividend":  ("rgba(14, 165, 233, 0.16)", "#7dd3fc"),
    "interest":  ("rgba(34, 197, 94, 0.16)",  "#86efac"),
    "other":     FALLBACK_BADGE,
}

HOLDING_TYPE_BADGE: dict[str, tuple[str, str]] = {
    "stock":          ("rgba(59, 130, 246, 0.16)", "#93c5fd"),
    "etf":            ("rgba(14, 165, 233, 0.16)", "#7dd3fc"),
    "sip":            ("rgba(16, 185, 129, 0.16)", "#6ee7b7"),
    "mutual_fund":    ("rgba(34, 197, 94, 0.16)",  "#86efac"),
    "fd":             ("rgba(245, 158, 11, 0.16)", "#fbbf24"),
    "ppf":            ("rgba(217, 119, 6, 0.16)",  "#fcd34d"),
    "epf":            ("rgba(234, 88, 12, 0.16)",  "#fdba74"),
    "nps":            ("rgba(239, 68, 68, 0.16)",  "#fca5a5"),
    "bond":           ("rgba(20, 184, 166, 0.16)", "#5eead4"),
    "gold_coin":      ("rgba(234, 179, 8, 0.16)",  "#fde047"),
    "gold_jewelry":   ("rgba(202, 138, 4, 0.16)",  "#fde68a"),
    "term_insurance": ("rgba(139, 92, 246, 0.16)", "#c4b5fd"),
    "crypto":         ("rgba(236, 72, 153, 0.16)", "#f9a8d4"),
    "real_estate":    ("rgba(124, 58, 237, 0.16)", "#c4b5fd"),
}

LIABILITY_TYPE_BADGE: dict[str, tuple[str, str]] = {
    "home_loan":       ("rgba(59, 130, 246, 0.16)", "#93c5fd"),
    "car_loan":        ("rgba(16, 185, 129, 0.16)", "#6ee7b7"),
    "personal_loan":   ("rgba(245, 158, 11, 0.16)", "#fbbf24"),
    "education_loan":  ("rgba(139, 92, 246, 0.16)", "#c4b5fd"),
    "credit_card":     ("rgba(239, 68, 68, 0.16)",  "#fca5a5"),
    "bnpl":            ("rgba(236, 72, 153, 0.16)", "#f9a8d4"),
}

GOAL_STATUS_BADGE: dict[str, tuple[str, str]] = {
    "active":    ("rgba(16, 185, 129, 0.16)", "#6ee7b7"),
    "achieved":  ("rgba(59, 130, 246, 0.16)", "#93c5fd"),
    "paused":    ("rgba(245, 158, 11, 0.16)", "#fbbf24"),
    "abandoned": ("rgba(239, 68, 68, 0.16)",  "#fca5a5"),
}

GOAL_PRIORITY_BADGE: dict[int, tuple[str, str]] = {
    1: ("rgba(239, 68, 68, 0.16)",  "#fca5a5"),
    2: ("rgba(234, 88, 12, 0.16)",  "#fdba74"),
    3: ("rgba(245, 158, 11, 0.16)", "#fbbf24"),
    4: ("rgba(16, 185, 129, 0.16)", "#6ee7b7"),
    5: FALLBACK_BADGE,
}
