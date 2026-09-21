import json
import os

import requests
import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore


TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"


def load_config():
    with open("config/searches.json", "r", encoding="utf-8") as file:
        return json.load(file)


def get_token():
    response = requests.post(
        TOKEN_URL,
        data={
            "grant_type": "client_credentials",
            "client_id": os.environ["FRANCE_TRAVAIL_CLIENT_ID"],
            "client_secret": os.environ["FRANCE_TRAVAIL_CLIENT_SECRET"],
            "scope": "api_offresdemploiv2 o2dsoffre"
        }
    )

    response.raise_for_status()
    return response.json()["access_token"]


def search_jobs(token, keywords, department=None):
    params = {
        "motsCles": keywords,
        "range": "0-49"
    }

    if department:
        params["departement"] = department

    response = requests.get(
        SEARCH_URL,
        headers={
            "Authorization": f"Bearer {token}"
        },
        params=params
    )

    if not response.ok:
        print(
            f"  ⚠️ Erreur France Travail pour '{keywords}': "
            f"HTTP {response.status_code}"
        )
        return []

    try:
        data = response.json()
    except ValueError:
        print(
            f"  ⚠️ Réponse non JSON de France Travail pour '{keywords}'"
        )
        return []

    return data.get("resultats", [])


def initialize_firebase():
    service_account = os.environ["FIREBASE_SERVICE_ACCOUNT"]

    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(service_account))
        firebase_admin.initialize_app(cred)

    return firestore.client()


def save_jobs(db, jobs):
    collection = db.collection("jobs")

    for job in jobs:
        job_id = job.get("id")

        if not job_id:
            continue

        document = {
            "source": "france_travail",
            "source_id": job_id,
            "title": job.get("intitule"),
            "description": job.get("description"),
            "company": job.get("entreprise", {}).get("nom"),
            "location": job.get("lieuTravail", {}).get("libelle"),
            "contract": job.get("typeContrat"),
            "contract_label": job.get("typeContratLibelle"),
            "published_at": job.get("dateCreation"),
            "url": job.get("origineOffre", {}).get("urlOrigine"),
            "updated_at": firestore.SERVER_TIMESTAMP
        }

        collection.document(job_id).set(
            document,
            merge=True
        )


def main():
    print("Chargement de la configuration...")

    config = load_config()

    print(f"{len(config['searches'])} recherches configurées.")

    token = get_token()
    db = initialize_firebase()

    all_jobs = {}

    for search in config["searches"]:
        name = search["name"]

        print(f"\nRecherche : {name}")

        for keyword in search["keywords"]:
            print(f"  Mot-clé : {keyword}")

            jobs = search_jobs(token, keyword)

            print(f"  → {len(jobs)} offres trouvées")

            for job in jobs:
                all_jobs[job["id"]] = job

    print(f"\nOffres uniques trouvées : {len(all_jobs)}")

    save_jobs(db, all_jobs.values())

    print("Import Firebase terminé.")


if __name__ == "__main__":
    main()
