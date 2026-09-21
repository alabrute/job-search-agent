import os
import requests

import firebase_admin
from firebase_admin import credentials
from firebase_admin import firestore


TOKEN_URL = "https://entreprise.francetravail.fr/connexion/oauth2/access_token?realm=/partenaire"
SEARCH_URL = "https://api.francetravail.io/partenaire/offresdemploi/v2/offres/search"


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


def search_jobs(token):
    response = requests.get(
        SEARCH_URL,
        headers={
            "Authorization": f"Bearer {token}"
        },
        params={
            "motsCles": "Supply Chain",
            "departement": "67",
            "range": "0-49"
        }
    )

    response.raise_for_status()
    return response.json()


def initialize_firebase():
    service_account = os.environ["FIREBASE_SERVICE_ACCOUNT"]

    if not firebase_admin._apps:
        cred = credentials.Certificate(
            __import__("json").loads(service_account)
        )
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

        print(f"Enregistrée : {job.get('intitule')}")


def main():
    print("Recherche France Travail...")

    token = get_token()
    data = search_jobs(token)

    jobs = data.get("resultats", [])

    print(f"Nombre d'offres trouvées : {len(jobs)}")

    db = initialize_firebase()
    save_jobs(db, jobs)

    print("Import Firebase terminé.")


if __name__ == "__main__":
    main()
