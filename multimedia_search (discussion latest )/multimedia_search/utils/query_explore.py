"""Build general related-search suggestions for the website UI.

This module does not change retrieval scoring.
It only creates clickable exploration queries.

Examples:
dog    -> golden retriever dog, dog in park, dog face
car    -> sports car, car on road, car headlights
camera -> camera close up, camera lens, camera indoors
flower -> flower petals, flower in garden, red flower
"""

from __future__ import annotations

import re
from typing import Dict, List, Tuple


_TOKEN_PATTERN = re.compile(r"[A-Za-z0-9]+")


# Specific well-known entities can have stronger "Types" suggestions.
# This is optional enrichment, not the whole system.
_ENTITY_SPECIALIZATIONS: Dict[str, Tuple[str, List[str]]] = {
    "dog": (
        "animal",
        [
            "golden retriever dog",
            "labrador dog",
            "german shepherd dog",
            "husky dog",
            "bulldog dog",
            "beagle dog",
            "poodle dog",
            "puppy dog",
        ],
    ),
    "cat": (
        "animal",
        [
            "persian cat",
            "siamese cat",
            "maine coon cat",
            "kitten cat",
            "black cat",
            "white cat",
            "orange cat",
        ],
    ),
    "car": (
        "vehicle",
        [
            "sports car",
            "classic car",
            "electric car",
            "red car",
            "black car",
            "white car",
            "police car",
        ],
    ),
    "bird": (
        "animal",
        [
            "small bird",
            "white bird",
            "black bird",
            "colorful bird",
            "eagle bird",
            "parrot bird",
        ],
    ),
    "flower": (
        "plant",
        [
            "red flower",
            "white flower",
            "yellow flower",
            "rose flower",
            "garden flower",
            "wild flower",
        ],
    ),
    "phone": (
        "device",
        [
            "smartphone",
            "mobile phone",
            "black phone",
            "white phone",
            "phone camera",
            "phone screen",
        ],
    ),
    "camera": (
        "device",
        [
            "digital camera",
            "black camera",
            "camera lens",
            "security camera",
            "phone camera",
        ],
    ),
}


_CATEGORY_TERMS: Dict[str, set[str]] = {
    "animal": {
        "animal",
        "dog",
        "cat",
        "bird",
        "horse",
        "cow",
        "sheep",
        "goat",
        "lion",
        "tiger",
        "bear",
        "fox",
        "rabbit",
        "elephant",
        "monkey",
        "fish",
        "duck",
        "chicken",
    },
    "vehicle": {
        "vehicle",
        "car",
        "bus",
        "truck",
        "bike",
        "bicycle",
        "motorcycle",
        "train",
        "plane",
        "airplane",
        "boat",
        "ship",
        "taxi",
        "van",
    },
    "person": {
        "person",
        "people",
        "man",
        "woman",
        "boy",
        "girl",
        "child",
        "baby",
        "face",
        "portrait",
    },
    "food": {
        "food",
        "meal",
        "pizza",
        "burger",
        "sandwich",
        "cake",
        "bread",
        "fruit",
        "apple",
        "banana",
        "orange",
        "rice",
        "pasta",
        "coffee",
        "tea",
    },
    "plant": {
        "plant",
        "tree",
        "flower",
        "leaf",
        "leaves",
        "grass",
        "garden",
        "rose",
    },
    "device": {
        "device",
        "phone",
        "camera",
        "laptop",
        "computer",
        "keyboard",
        "mouse",
        "screen",
        "monitor",
        "tv",
        "tablet",
        "watch",
    },
    "furniture": {
        "furniture",
        "chair",
        "table",
        "sofa",
        "couch",
        "bed",
        "desk",
        "shelf",
        "cabinet",
    },
    "building": {
        "building",
        "house",
        "home",
        "room",
        "kitchen",
        "bathroom",
        "school",
        "office",
        "street",
        "park",
        "beach",
    },
}


_CATEGORY_GROUPS = {
    "animal": [
        {
            "label": "Views",
            "templates": [
                "{q} close up",
                "{q} portrait",
                "{q} full body",
                "{q} side view",
            ],
        },
        {
            "label": "Places",
            "templates": [
                "{q} in park",
                "{q} in home",
                "{q} in garden",
                "{q} on beach",
                "{q} indoors",
                "{q} outdoors",
            ],
        },
        {
            "label": "Body details",
            "templates": [
                "{q} face",
                "{q} eyes",
                "{q} ears",
                "{q} nose",
                "{q} paws",
                "{q} tail",
                "{q} fur",
            ],
        },
        {
            "label": "Actions",
            "templates": [
                "{q} running",
                "{q} sitting",
                "{q} sleeping",
                "{q} playing",
                "{q} jumping",
                "{q} eating",
            ],
        },
    ],
    "vehicle": [
        {
            "label": "Views",
            "templates": [
                "{q} front view",
                "{q} back view",
                "{q} side view",
                "{q} close up",
                "{q} interior",
            ],
        },
        {
            "label": "Places",
            "templates": [
                "{q} on road",
                "{q} in street",
                "{q} in garage",
                "{q} in parking",
                "{q} outdoors",
            ],
        },
        {
            "label": "Parts",
            "templates": [
                "{q} wheel",
                "{q} headlights",
                "{q} door",
                "{q} window",
                "{q} engine",
                "{q} dashboard",
            ],
        },
    ],
    "person": [
        {
            "label": "Views",
            "templates": [
                "{q} face",
                "{q} portrait",
                "{q} full body",
                "{q} side view",
                "{q} close up",
            ],
        },
        {
            "label": "Places",
            "templates": [
                "{q} in park",
                "{q} at home",
                "{q} indoors",
                "{q} outdoors",
                "{q} in street",
            ],
        },
        {
            "label": "Actions",
            "templates": [
                "{q} walking",
                "{q} running",
                "{q} sitting",
                "{q} standing",
                "{q} working",
                "{q} playing",
            ],
        },
    ],
    "food": [
        {
            "label": "Types",
            "templates": [
                "fresh {q}",
                "hot {q}",
                "cold {q}",
                "homemade {q}",
                "fast food {q}",
            ],
        },
        {
            "label": "Views",
            "templates": [
                "{q} close up",
                "{q} on plate",
                "{q} top view",
                "{q} details",
            ],
        },
        {
            "label": "Places",
            "templates": [
                "{q} in kitchen",
                "{q} in restaurant",
                "{q} on table",
                "{q} at home",
            ],
        },
    ],
    "plant": [
        {
            "label": "Types",
            "templates": [
                "red {q}",
                "white {q}",
                "yellow {q}",
                "green {q}",
                "garden {q}",
                "wild {q}",
            ],
        },
        {
            "label": "Places",
            "templates": [
                "{q} in garden",
                "{q} in park",
                "{q} outdoors",
                "{q} in home",
                "{q} in pot",
            ],
        },
        {
            "label": "Details",
            "templates": [
                "{q} close up",
                "{q} leaves",
                "{q} petals",
                "{q} stem",
                "{q} roots",
                "{q} details",
            ],
        },
    ],
    "device": [
        {
            "label": "Views",
            "templates": [
                "{q} close up",
                "{q} front view",
                "{q} side view",
                "{q} details",
            ],
        },
        {
            "label": "Places",
            "templates": [
                "{q} on desk",
                "{q} in hand",
                "{q} indoors",
                "{q} at home",
                "{q} in office",
            ],
        },
        {
            "label": "Parts",
            "templates": [
                "{q} screen",
                "{q} button",
                "{q} camera",
                "{q} lens",
                "{q} keyboard",
            ],
        },
    ],
    "furniture": [
        {
            "label": "Views",
            "templates": [
                "{q} close up",
                "{q} front view",
                "{q} side view",
                "{q} full view",
                "{q} details",
            ],
        },
        {
            "label": "Places",
            "templates": [
                "{q} in home",
                "{q} in room",
                "{q} in office",
                "{q} indoors",
                "{q} near window",
            ],
        },
        {
            "label": "Details",
            "templates": [
                "{q} legs",
                "{q} surface",
                "{q} texture",
                "{q} fabric",
                "{q} wood",
            ],
        },
    ],
    "building": [
        {
            "label": "Views",
            "templates": [
                "{q} outside",
                "{q} inside",
                "{q} front view",
                "{q} wide view",
                "{q} close up",
            ],
        },
        {
            "label": "Details",
            "templates": [
                "{q} door",
                "{q} window",
                "{q} wall",
                "{q} roof",
                "{q} interior",
            ],
        },
        {
            "label": "Lighting",
            "templates": [
                "{q} daytime",
                "{q} night",
                "{q} bright",
                "{q} dark",
            ],
        },
    ],
}


_GENERIC_GROUPS = [
    {
        "label": "Views",
        "templates": [
            "{q} close up",
            "{q} full view",
            "{q} side view",
            "{q} front view",
            "{q} details",
        ],
    },
    {
        "label": "Places",
        "templates": [
            "{q} indoors",
            "{q} outdoors",
            "{q} in home",
            "{q} in park",
            "{q} in street",
        ],
    },
    {
        "label": "Style",
        "templates": [
            "{q} bright",
            "{q} dark",
            "{q} background",
            "{q} portrait",
            "{q} object",
        ],
    },
]


def _clean_query(query: str) -> str:
    """Normalize user query for suggestion generation."""
    return " ".join(str(query).strip().lower().split())


def _tokens(query: str) -> List[str]:
    """Return simple lowercase tokens."""
    return _TOKEN_PATTERN.findall(query.lower())


def _detect_category(query: str) -> Tuple[str, str, List[str]]:
    """Detect the best category for the query.

    Returns:
        focus_term, category_name, specialization_queries
    """
    tokens = _tokens(query)

    if not tokens:
        return "", "generic", []

    for token in tokens:
        if token in _ENTITY_SPECIALIZATIONS:
            category, special_queries = _ENTITY_SPECIALIZATIONS[token]
            return token, category, special_queries

    for token in tokens:
        for category, terms in _CATEGORY_TERMS.items():
            if token in terms:
                return token, category, []

    return tokens[-1], "generic", []


def _dedupe_queries(queries: List[str], original_query: str) -> List[str]:
    """Remove duplicates and the original query."""
    seen = set()
    cleaned_original = _clean_query(original_query)
    output = []

    for query in queries:
        cleaned = _clean_query(query)

        if not cleaned:
            continue

        if cleaned == cleaned_original:
            continue

        if cleaned in seen:
            continue

        seen.add(cleaned)
        output.append(cleaned)

    return output


def _render_templates(templates: List[str], query: str) -> List[str]:
    """Render query templates."""
    return [
        template.format(q=query)
        for template in templates
    ]

def build_query_exploration_groups(
    query: str,
    max_groups: int = 5,
    max_queries_per_group: int = 8,
) -> List[Dict[str, List[str]]]:
    
    """Build grouped related-search chips for any query.

    Known entities get better type suggestions.
    Unknown entities still get generic image-search exploration suggestions.
    """
    cleaned_query = _clean_query(query)
    if not cleaned_query:
        return []

    focus_term, category, special_queries = _detect_category(cleaned_query)
    groups: List[Dict[str, List[str]]] = []

    if special_queries and cleaned_query == focus_term:
        groups.append(
            {
                "label": "Types",
                "queries": special_queries,
            }
        )

    template_groups = _CATEGORY_GROUPS.get(category, _GENERIC_GROUPS)

    for group in template_groups:
        groups.append(
            {
                "label": group["label"],
                "queries": _render_templates(group["templates"], cleaned_query),
            }
        )

    final_groups: List[Dict[str, List[str]]] = []

    for group in groups:
        queries = _dedupe_queries(group.get("queries", []), cleaned_query)
        queries = queries[:max_queries_per_group]

        if queries:
            final_groups.append(
                {
                    "label": group.get("label", "Related"),
                    "queries": queries,
                }
            )

        if len(final_groups) >= max_groups:
            break

    return final_groups