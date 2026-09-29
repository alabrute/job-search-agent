import json
import os
import re
import unicodedata
from datetime import datetime, timezone

import requests
import firebase_admin
from bs4 import BeautifulSoup
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

LINKEDIN_SEARCH_URL = (
    "https://www.linkedin.com/jobs/search/"
)

LINKEDIN_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


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

    return f"{company}|{title}"


# ---------------------------------------------------------
# FILTRES COMMUNS
# ---------------------------------------------------------

def is_internship(job):

    title = normalize_text(
        job.get("title") or ""
    )

    description = normalize_text(
        job.get("description") or ""
    )

    contract_type = normalize_text(
        job.get("contract_type")
        or job.get("contract")
        or ""
    )

    contract_time = normalize_text(
        job.get("contract_time")
        or ""
    )

    text = " ".join([
        title,
        description,
        contract_type,
        contract_time
    ])

    internship_keywords = [
        "stage",
        "stagiaire",
        "internship",
        "intern",
        "alternance",
        "alternant",
        "apprentissage",
        "apprenti",
    ]

    for keyword in internship_keywords:

        if re.search(
            rf"\b{re.escape(keyword)}\b",
            text
        ):

            return True

    return False


def is_bas_rhin(location):

    text = normalize_text(
        location
    )

    if "bas rhin" in text:
        return True

    bas_rhin_locations = [
        "strasbourg",
        "obernai",
        "schirmeck",
        "molsheim",
        "vendenheim",
        "schiltigheim",
        "bischheim",
        "illkirch",
        "lingolsheim",
        "ostwald",
        "hoenheim",
        "haguenau",
        "saverne",
        "seltz",
        "brumath",
        "souffelweyersheim",
        "mundolsheim",
        "reichstett",
        "la wantzenau",
        "niederhausbergen",
        "mittelhausbergen",
        "oberhausbergen",
        "entzheim",
        "reichshoffen",
        "weyersheim",
        "eckbolsheim",
        "holtzheim",
        "hoerdt",
        "lipsheim",
        "oberbronn",
        "selestat",
        "sélestat",
        "erstein",
        "benfeld",
        "marlenheim",
        "wissembourg",
        "bischwiller",
        "soultz sous forets",
        "soultz-sous-forets",
        "marmoutier",
        "wasselonne",
        "muttersholtz",
        "rosheim",
        "barr",
        "schirmeck",
        "la broque",
        "semeurs",
        "truchtersheim",
        "wiwersheim",
        "geispolsheim",
        "fegersheim",
        "plobsheim",
        "eschau",
        "osthouse",
        "saint pierre",
        "duttlenheim",
        "duppigheim",
        "mommenheim",
        "dettwiller",
        "hochfelden",
    ]

    return any(
        city in text
        for city in bas_rhin_locations
    )


def is_linkedin_relevant(
    title,
    company,
    description=""
):

    text = normalize_text(
        f"{title} {company} {description}"
    )

    keywords = [
        "supply chain",
        "supply planning",
        "demand planning",
        "s&op",
        "ibp",
        "kinaxis",
        "rapidresponse",
        "maestro",
        "inventory planner",
        "material planner",
        "approvisionneur",
        "approvisionnement",
        "planification",
        "planning",
        "ordonnancement",
        "supplier performance",
        "responsable sc",
        "business analyst",
    ]

    return any(
        keyword in text
        for keyword in keywords
    )


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

    keyword_words = normalize_text(
        keywords
    ).split()

    for job in data.get(
        "results",
        []
    ):

        if is_internship(job):

            print(
                f"    ↳ stage/alternance ignoré : "
                f"{job.get('title')}"
            )

            continue

        title = job.get(
            "title"
        ) or ""

        description = job.get(
            "description"
        ) or ""

        text = normalize_text(
            f"{title} {description}"
        )

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
# LINKEDIN
# ---------------------------------------------------------

def search_linkedin(keywords):

    params = {
        "keywords": keywords,
        "location": (
            "Strasbourg, Grand Est, France"
        ),
    }

    try:

        response = requests.get(
            LINKEDIN_SEARCH_URL,
            headers=LINKEDIN_HEADERS,
            params=params,
            timeout=30
        )

    except requests.RequestException as error:

        print(
            f"  ⚠️ LinkedIn : erreur "
            f"de connexion pour '{keywords}' : "
            f"{error}"
        )

        return []

    if not response.ok:

        print(
            f"  ⚠️ LinkedIn : HTTP "
            f"{response.status_code} "
            f"pour '{keywords}'"
        )

        return []

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    cards = soup.select(
        "div.base-card"
    )

    print(
        f"    → {len(cards)} "
        f"offres LinkedIn trouvées"
    )

    jobs = []

    for card in cards:

        title_element = card.select_one(
            ".base-search-card__title"
        )

        company_element = card.select_one(
            ".base-search-card__subtitle"
        )

        location_element = card.select_one(
            ".job-search-card__location"
        )

        link_element = card.select_one(
            "a.base-card__full-link"
        )

        date_element = card.select_one(
            "time"
        )

        description_element = card.select_one(
            ".base-search-card__snippet"
        )

        title = (
            title_element.get_text(
                " ",
                strip=True
            )
            if title_element
            else ""
        )

        company = (
            company_element.get_text(
                " ",
                strip=True
            )
            if company_element
            else ""
        )

        location = (
            location_element.get_text(
                " ",
                strip=True
            )
            if location_element
            else ""
        )

        job_url = (
            link_element.get("href")
            if link_element
            else ""
        )

        description = (
            description_element.get_text(
                " ",
                strip=True
            )
            if description_element
            else ""
        )

        published_at = ""

        if date_element:

            published_at = (
                date_element.get("datetime")
                or date_element.get_text(
                    " ",
                    strip=True
                )
            )

        job = {

            "source": "linkedin",

            "source_id": "",

            "title": title,

            "description": description,

            "company": company,

            "location": location,

            "city": location,

            "department": "67",

            "contract": "",

            "contract_label": "",

            "published_at": published_at,

            "url": job_url,

        }

        if job_url:

            match = re.search(
                r"/jobs/view/[^/]+-(\d+)",
                job_url
            )

            if match:

                job["source_id"] = (
                    match.group(1)
                )

        if not job["source_id"]:

            print(
                f"    ↳ URL LinkedIn "
                f"non exploitable : "
                f"{title}"
            )

            continue

        if is_internship(job):

            print(
                f"    ↳ stage/alternance ignoré : "
                f"{title}"
            )

            continue

        if not is_bas_rhin(
            location
        ):

            print(
                f"    ↳ hors Bas-Rhin ignoré : "
                f"{title} — {location}"
            )

            continue

        if not is_linkedin_relevant(
            title,
            company,
            description
        ):

            print(
                f"    ↳ hors sujet ignoré : "
                f"{title}"
            )

            continue

        jobs.append(job)

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
# AJOUT / DEDUPLICATION
# ---------------------------------------------------------

def add_jobs_to_collection(
    all_jobs,
    jobs,
    search_name,
    keyword
):

    for job in jobs:

        job["_searches"] = [
            search_name
        ]

        job["_keywords"] = [
            keyword
        ]

        key = deduplication_key(
            job
        )

        if key in all_jobs:

            print(
                f"    ↳ doublon ignoré : "
                f"{job.get('title')}"
            )

            existing = all_jobs[key]

            existing["_searches"] = list(
                set(
                    existing.get(
                        "_searches",
                        []
                    )
                    + [search_name]
                )
            )

            existing["_keywords"] = list(
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

            add_jobs_to_collection(
                all_jobs,
                jobs,
                name,
                keyword
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

            add_jobs_to_collection(
                all_jobs,
                jobs,
                name,
                keyword
            )

    # -----------------------------------------------------
    # LINKEDIN
    # -----------------------------------------------------

    print(
        "\n=== LINKEDIN ==="
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

            jobs = search_linkedin(
                keyword
            )

            print(
                f"    → {len(jobs)} "
                f"offres pertinentes"
            )

            add_jobs_to_collection(
                all_jobs,
                jobs,
                name,
                keyword
            )

    # -----------------------------------------------------
    # SAUVEGARDE
    # -----------------------------------------------------

    print(
        f"\nOffres uniques : "
        f"{len(all_jobs)}"
    )

    import_timestamp = datetime.now(
        timezone.utc
    ).isoformat()

    db.collection(
        "system"
    ).document(
        "status"
    ).set(
        {
            "last_import_at": (
                import_timestamp
            )
        },
        merge=True
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
