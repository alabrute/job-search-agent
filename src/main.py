import os
import requests


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


def main():
    print("Recherche France Travail...")

    token = get_token()
    data = search_jobs(token)

    jobs = data.get("resultats", [])

    print(f"Nombre d'offres trouvées : {len(jobs)}")

    for job in jobs[:10]:
        print(
            f"- {job.get('intitule')} | "
            f"{job.get('lieuTravail', {}).get('libelle')} | "
            f"{job.get('id')}"
        )


if __name__ == "__main__":
    main()
