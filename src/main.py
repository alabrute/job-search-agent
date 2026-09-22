import json
import os
import re
import unicodedata

import requests
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore


TOKEN_URL = (
    "https://entreprise.francetravail.fr/connexion/"
    "oauth2/access_token?realm=/partenaire"
)

FRANCE_TRAVAIL_SEARCH_URL = (
    "https://api.francetravail.io/"
    "partenaire/offresdemploi/v2/offres/search"
)

ADZUNA_SEARCH_URL = (
    "https://api.adzuna.com/v1/api/jobs/fr/search/1"
)


def load_config():
    with open(
        "config/searches.json",
        "r",
        encoding="utf-8"
    ) as file:
        return json.load(file)


# ---------------------------------------------------------
# NORMALISATION / DEDUPLICATION
# ---------------------------------------------------------

def normalize_text(value):
    if not value:
        return ""

    value = str(value).lower()

    value = unicodedata.normalize(
        "NFD",
        value
    )

    value = "".join(
        char
        for char in value
        if unicodedata.category(char) != "Mn"
    )

    value = re.sub(
        r"\b(h/f|f/h|hf|fh)\b",
        "",
        value
    )

    value = re.sub(
        r"[^a-z0-9]+",
        " ",
        value
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    ).strip()

    return value


def normalize_company(value):
    value = normalize_text(value)

    for suffix in [
        "sas",
        "sasu",
        "sa",
        "sarl",
        "eurl",
        "inc",
        "ltd",
        "limited",
        "gmbh",
    ]:
        value = re.sub(
            rf"\b{suffix}\b",
            "",
            value
        )

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


def normalize_title(value):
    return normalize_text(value)


def normalize_city(value):
    if not value:
        return ""

    value = normalize_text(value)

    replacements = {
        "strasbourg cedex": "strasbourg",
        "strasbourg": "strasbourg",
    }

    return replacements.get(
        value,
        value
    )


def deduplication_key(job):
    company = normalize_company(
        job.get("company")
    )

    title = normalize_title(
        job.get("title")
    )

    city = normalize_city(
        job.get("city")
    )

    return f"{company}|{title}|{city}"


# ---------------------------------------------------------
# FRANCE TRAVAIL
# ---------------------------------------------------------

def get_france_travail_token():

    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ[
                "FRANCE_TRAVAIL_CLIENT_ID"
            ],
            "client_secret": os.environ[
                "FRANCE_TRAVAIL_CLIENT_SECRET"
            ],
            "scope": (
                "api_offresdemploiv2 "
                "o2dsoffre"
            )
        }
    )

    response.raise_for_status()

    return response.json()["access_token"]


def search_france_travail(
    token,
    keywords,
    department="67"
):

    params = {
        "motsCles": keywords,
        "departement": department,
        "range": "0-49"
    }

    response = requests.get(
        FRANCE_TRAVAIL_SEARCH_URL,
        headers={
            "Authorization": (
                f"Bearer {token}"
            )
        },
        params=params
    )

    if not response.ok:

        print(
            f"  ⚠️ France Travail : HTTP "
            f"{response.status_code} "
            f"pour '{keywords}'"
        )

        return []

    try:

        data = response.json()

    except ValueError:

        print(
            f"  ⚠️ France Travail : "
            f"réponse non JSON "
            f"pour '{keywords}'"
        )

        return []

    jobs = []

    for job in data.get(
        "resultats",
        []
    ):

        lieu = job.get(
            "lieuTravail",
            {}
        )

        jobs.append({

            "source": "france_travail",

            "source_id": job.get(
                "id"
            ),

            "title": job.get(
                "intitule"
            ),

            "description": job.get(
                "description"
            ),

            "company": job.get(
                "entreprise",
                {}
            ).get("nom"),

            "location": lieu.get(
                "libelle"
            ),

            "city": lieu.get(
                "libelle"
            ),

            "department": "67",

            "contract": job.get(
                "typeContrat"
            ),

            "contract_label": job.get(
                "typeContratLibelle"
            ),

            "published_at": job.get(
                "dateCreation"
            ),

            "url": job.get(
                "origineOffre",
                {}
            ).get("urlOrigine"),

        })

    return jobs


# ---------------------------------------------------------
# ADZUNA
# ---------------------------------------------------------

def search_adzuna(keywords):

    app_id = os.environ[
        "ADZUNA_APP_ID"
    ]

    app_key = os.environ[
        "ADZUNA_APP_KEY"
    ]

    params = {

        "app_id": app_id,

        "app_key": app_key,

        "what": keywords,

        "where": "Bas-Rhin",

        "results_per_page": 50,

        "content-type": "application/json"

    }

    response = requests.get(
        ADZUNA_SEARCH_URL,
        params=params
    )

    if not response.ok:

        print(
            f"  ⚠️ Adzuna : HTTP "
            f"{response.status_code} "
            f"pour '{keywords}'"
        )

        return []

    try:

        data = response.json()

    except ValueError:

        print(
            f"  ⚠️ Adzuna : réponse "
            f"non JSON "
            f"pour '{keywords}'"
        )

        return []

    jobs = []

    # -----------------------------------------------------
    # FILTRE DE PERTINENCE
    # -----------------------------------------------------

    keyword_words = normalize_text(
        keywords
    ).split()

    for job in data.get(
        "results",
        []
    ):

        title = job.get(
            "title"
        ) or ""

        description = job.get(
            "description"
        ) or ""

        text = normalize_text(
            f"{title} {description}"
        )

        # Tous les mots du mot-clé doivent apparaître
        # dans le titre ou la description.
        is_relevant = all(
            word in text
            for word in keyword_words
        )

        if not is_relevant:

            print(
                f"    ↳ hors sujet ignoré : "
                f"{title}"
            )

            continue

        location = job.get(
            "location",
            {}
        )

        area = location.get(
            "area",
            []
        )

        city = ""

        if area:
            city = area[-1]

        jobs.append({

            "source": "adzuna",

            "source_id": str(
                job.get("id")
            ),

            "title": job.get(
                "title"
            ),

            "description": job.get(
                "description"
            ),

            "company": job.get(
                "company",
                {}
            ).get(
                "display_name"
            ),

            "location": ", ".join(
                area
            ),

            "city": city,

            "department": "67",

            "contract": job.get(
                "contract_type"
            ),

            "contract_label": job.get(
                "contract_type"
            ),

            "published_at": job.get(
                "created"
            ),

            "url": job.get(
                "redirect_url"
            ),

        })

    return jobs


# ---------------------------------------------------------
# FIREBASE
# ---------------------------------------------------------

def initialize_firebase():

    service_account = os.environ[
        "FIREBASE_SERVICE_ACCOUNT"
    ]

    if not firebase_admin._apps:

        cred = credentials.Certificate(
            json.loads(
                service_account
            )
        )

        firebase_admin.initialize_app(
            cred
        )

    return firestore.client()


def save_jobs(
    db,
    jobs
):

    collection = db.collection(
        "jobs"
    )

    for job in jobs:

        source = job.get(
            "source"
        )

        source_id = job.get(
            "source_id"
        )

        if not source_id:
            continue

        document_id = (
            f"{source}_{source_id}"
        )

        document = {

            "source": source,

            "source_id": source_id,

            "title": job.get(
                "title"
            ),

            "description": job.get(
                "description"
            ),

            "company": job.get(
                "company"
            ),

            "location": job.get(
                "location"
            ),

            "city": job.get(
                "city"
            ),

            "department": "67",

            "contract": job.get(
                "contract"
            ),

            "contract_label": job.get(
                "contract_label"
            ),

            "published_at": job.get(
                "published_at"
            ),

            "url": job.get(
                "url"
            ),

            "searches": job.get(
                "_searches",
                []
            ),

            "keywords": job.get(
                "_keywords",
                []
            ),

            "deduplication_key": (
                deduplication_key(job)
            ),

            "updated_at": (
                firestore.SERVER_TIMESTAMP
            )

        }

        collection.document(
            document_id
        ).set(
            document,
            merge=True
        )


# ---------------------------------------------------------
# MAIN
# ---------------------------------------------------------

def main():

    print(
        "Chargement de la configuration..."
    )

    config = load_config()

    print(
        f"{len(config['searches'])} "
        f"recherches configurées."
    )

    db = initialize_firebase()

    all_jobs = {}

    # -----------------------------------------------------
    # FRANCE TRAVAIL
    # -----------------------------------------------------

    print(
        "\n=== FRANCE TRAVAIL ==="
    )

    token = get_france_travail_token()

    for search in config[
        "searches"
    ]:

        name = search[
            "name"
        ]

        print(
            f"\nRecherche : {name}"
        )

        for keyword in search[
            "keywords"
        ]:

            print(
                f"  Mot-clé : {keyword}"
            )

            jobs = search_france_travail(
                token,
                keyword,
                "67"
            )

            print(
                f"    → {len(jobs)} "
                f"offres trouvées"
            )

            for job in jobs:

                job[
                    "_searches"
                ] = [name]

                job[
                    "_keywords"
                ] = [keyword]

                key = deduplication_key(
                    job
                )

                if key not in all_jobs:

                    all_jobs[key] = job

                else:

                    existing = (
                        all_jobs[key]
                    )

                    existing[
                        "_searches"
                    ] = list(
                        set(
                            existing.get(
                                "_searches",
                                []
                            )
                            + [name]
                        )
                    )

                    existing[
                        "_keywords"
                    ] = list(
                        set(
                            existing.get(
                                "_keywords",
                                []
                            )
                            + [keyword]
                        )
                    )

    # -----------------------------------------------------
    # ADZUNA
    # -----------------------------------------------------

    print(
        "\n=== ADZUNA ==="
    )

    for search in config[
        "searches"
    ]:

        name = search[
            "name"
        ]

        print(
            f"\nRecherche : {name}"
        )

        for keyword in search[
            "keywords"
        ]:

            print(
                f"  Mot-clé : {keyword}"
            )

            jobs = search_adzuna(
                keyword
            )

            print(
                f"    → {len(jobs)} "
                f"offres pertinentes"
            )

            for job in jobs:

                job[
                    "_searches"
                ] = [name]

                job[
                    "_keywords"
                ] = [keyword]

                key = deduplication_key(
                    job
                )

                if key in all_jobs:

                    print(
                        f"    ↳ doublon ignoré : "
                        f"{job.get('title')}"
                    )

                    existing = (
                        all_jobs[key]
                    )

                    existing[
                        "_searches"
                    ] = list(
                        set(
                            existing.get(
                                "_searches",
                                []
                            )
                            + [name]
                        )
                    )

                    existing[
                        "_keywords"
                    ] = list(
                        set(
                            existing.get(
                                "_keywords",
                                []
                            )
                            + [keyword]
                        )
                    )

                else:

                    all_jobs[key] = job

    # -----------------------------------------------------
    # SAUVEGARDE
    # -----------------------------------------------------

    print(
        f"\nOffres uniques : "
        f"{len(all_jobs)}"
    )

    save_jobs(
        db,
        all_jobs.values()
    )

    print(
        "Import Firebase terminé."
    )


if __name__ == "__main__":
    main()
