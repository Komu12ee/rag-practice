import json
from rapidfuzz import fuzz
from pathlib import Path


# ==========================================================
# CONFIG
# ==========================================================

DETAILED_JSON =r"C:\Users\hp\OneDrive\Desktop\rti\data\departments.json"
ROUTING_JSON =r"C:\Users\hp\projects\rti-project\offline\rti\data\departments.json"

MASTER_OUTPUT = "departments_master.json"
CHUNKS_OUTPUT = "department_chunks.json"
UNMATCHED_OUTPUT = "unmatched_departments.json"

MATCH_THRESHOLD = 65


# ==========================================================
# HELPERS
# ==========================================================

def load_json(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(data, filepath):
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def normalize(text):

    if not text:
        return ""

    text = text.lower()

    replacements = {
        "&": "and",
        "department": "",
        "dept": "",
        "government": "",
        "welfare": "",
        "-": " ",
        "_": " "
    }

    for old, new in replacements.items():
        text = text.replace(old, new)

    return " ".join(text.split())


def unique(values):

    seen = set()
    result = []

    for item in values:

        if not item:
            continue

        if item not in seen:
            seen.add(item)
            result.append(item)

    return result


# ==========================================================
# FIND BEST MATCH
# ==========================================================

def find_best_match(dept_name, routing_departments):

    best_score = 0
    best_match = None

    dept_name_norm = normalize(dept_name)

    for candidate in routing_departments:

        candidate_name = candidate["name_en"]

        score = fuzz.token_sort_ratio(
            dept_name_norm,
            normalize(candidate_name)
        )

        if score > best_score:
            best_score = score
            best_match = candidate

    return best_match, best_score


# ==========================================================
# CREATE ALIASES
# ==========================================================

def create_aliases(detail, routing):

    aliases = []

    aliases.append(
        detail.get(
            "department_name",
            ""
        )
    )

    aliases.append(
        routing.get(
            "name_en",
            ""
        )
    )

    aliases.append(
        routing.get(
            "name_hi",
            ""
        )
    )

    aliases.append(
        routing.get(
            "parent_ministry",
            ""
        )
    )

    return unique(aliases)


# ==========================================================
# MERGE KEYWORDS
# ==========================================================

def merge_keywords(detail, routing):

    keywords = []

    keywords.extend(
        detail.get("keywords", [])
    )

    keywords.extend(
        routing.get("keywords_en", [])
    )

    keywords.extend(
        routing.get("keywords_hi", [])
    )

    return unique(keywords)


# ==========================================================
# CREATE SEARCH TEXT
# ==========================================================

def create_search_text(record):

    fields = []

    scalar_fields = [
        "department_name_en",
        "department_name_hi",
        "description",
        "jurisdiction_description",
        "parent_ministry"
    ]

    list_fields = [
        "aliases",
        "responsibilities",
        "schemes",
        "projects",
        "services",
        "citizen_facing_activities",
        "government_systems",
        "common_rti_types",
        "related_offices",
        "keywords"
    ]

    for field in scalar_fields:

        value = record.get(field)

        if value:
            fields.append(value)

    for field in list_fields:

        values = record.get(field, [])

        if values:
            fields.extend(values)

    return " ".join(fields)


# ==========================================================
# CREATE MASTER RECORD
# ==========================================================

def merge_department(detail, routing):

    merged = {

        "department_id":
            routing["id"],

        "department_name_en":
            routing["name_en"],

        "department_name_hi":
            routing.get(
                "name_hi",
                ""
            ),

        "aliases":
            create_aliases(
                detail,
                routing
            ),

        "parent_ministry":
            routing.get(
                "parent_ministry",
                ""
            ),

        "description":
            detail.get(
                "description",
                ""
            ),

        "jurisdiction_description":
            routing.get(
                "jurisdiction_description",
                ""
            ),

        "responsibilities":
            detail.get(
                "responsibilities",
                []
            ),

        "schemes":
            detail.get(
                "schemes",
                []
            ),

        "projects":
            detail.get(
                "projects",
                []
            ),

        "services":
            detail.get(
                "services",
                []
            ),

        "citizen_facing_activities":
            detail.get(
                "citizen_facing_activities",
                []
            ),

        "government_systems":
            detail.get(
                "government_systems_managed",
                []
            ),

        "common_rti_types":
            routing.get(
                "common_rti_types",
                []
            ),

        "related_offices":
            detail.get(
                "related_offices",
                []
            ),

        "keywords":
            merge_keywords(
                detail,
                routing
            )
    }

    merged["search_text"] = create_search_text(
        merged
    )

    return merged


# ==========================================================
# CHUNK CREATION
# ==========================================================

def create_chunks(department):

    chunks = []

    chunk_sources = {

        "jurisdiction":
            department.get(
                "jurisdiction_description",
                ""
            ),

        "description":
            department.get(
                "description",
                ""
            ),

        "responsibilities":
            " ".join(
                department.get(
                    "responsibilities",
                    []
                )
            ),

        "schemes":
            " ".join(
                department.get(
                    "schemes",
                    []
                )
            ),

        "projects":
            " ".join(
                department.get(
                    "projects",
                    []
                )
            ),

        "services":
            " ".join(
                department.get(
                    "services",
                    []
                )
            ),

        "systems":
            " ".join(
                department.get(
                    "government_systems",
                    []
                )
            ),

        "rti_types":
            " ".join(
                department.get(
                    "common_rti_types",
                    []
                )
            ),

        "keywords":
            " ".join(
                department.get(
                    "keywords",
                    []
                )
            )
    }

    for chunk_type, content in chunk_sources.items():

        if not content:
            continue

        chunks.append({

            "department_id":
                department[
                    "department_id"
                ],

            "department_name":
                department[
                    "department_name_en"
                ],

            "chunk_type":
                chunk_type,

            "content":
                content
        })

    return chunks


# ==========================================================
# MAIN
# ==========================================================

print("Loading files...")

detailed_departments = load_json(
    DETAILED_JSON
)

routing_departments = load_json(
    ROUTING_JSON
)

master_departments = []
all_chunks = []
unmatched = []

print(
    f"Detailed Departments: "
    f"{len(detailed_departments)}"
)

print(
    f"Routing Departments: "
    f"{len(routing_departments)}"
)

for detail in detailed_departments:

    department_name = detail.get(
        "department_name",
        ""
    )

    best_match, score = find_best_match(
        department_name,
        routing_departments
    )

    if score < MATCH_THRESHOLD:

        unmatched.append({

            "department":
                department_name,

            "best_score":
                score
        })

        print(
            f"NO MATCH -> "
            f"{department_name}"
        )

        continue

    merged = merge_department(
        detail,
        best_match
    )

    master_departments.append(
        merged
    )

    chunks = create_chunks(
        merged
    )

    all_chunks.extend(
        chunks
    )

    print(
        f"MATCHED: "
        f"{department_name}"
        f" -> "
        f"{best_match['name_en']}"
        f" ({score})"
    )


# ==========================================================
# SAVE FILES
# ==========================================================

save_json(
    master_departments,
    MASTER_OUTPUT
)

save_json(
    all_chunks,
    CHUNKS_OUTPUT
)

save_json(
    unmatched,
    UNMATCHED_OUTPUT
)

print("\nDONE")
print(
    f"Master Departments: "
    f"{len(master_departments)}"
)

print(
    f"Chunks: "
    f"{len(all_chunks)}"
)

print(
    f"Unmatched: "
    f"{len(unmatched)}"
)