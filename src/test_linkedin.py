import re
import unicodedata

import requests
from bs4 import BeautifulSoup


URL = (
    "https://www.linkedin.com/jobs/search/"
    "?keywords=Supply%20Chain"
    "&location=Strasbourg%2C%20Grand%20Est%2C%20France"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


def normalize_text(text):
    text = text or ""

    text = unicodedata.normalize(
        "NFD",
        text
    )

    text = "".join(
        char
        for char in text
        if unicodedata.category(char) != "Mn"
    )

    return text.lower().strip()


def is_internship(title):
    text = normalize_text(title)

    keywords = [
        "stage",
        "stagiaire",
        "internship",
        "intern",
        "alternance",
        "alternant",
        "apprentissage",
        "apprenti",
    ]

    return any(
        re.search(
            rf"\b{re.escape(keyword)}\b",
            text
        )
        for keyword in keywords
    )


def is_bas_rhin(location):
    text = normalize_text(location)

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
    ]

    return any(
        city in text
        for city in bas_rhin_locations
    )


def is_relevant(title):
    text = normalize_text(title)

    keywords = [
        "supply chain",
        "supply planning",
        "demand planning",
        "s&op",
        "ibp",
        "kinaxis",
        "rapidresponse",
        "maestro",
    ]

    return any(
        keyword in text
        for keyword in keywords
    )


def main():

    print("Connexion à LinkedIn...")

    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=30
    )

    print(f"HTTP {response.status_code}")
    print(
        f"Taille de la réponse : "
        f"{len(response.text)} caractères"
    )

    if not response.ok:
        print(
            "❌ LinkedIn n'a pas renvoyé "
            "une réponse exploitable."
        )
        return

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    cards = soup.select(
        "div.base-card"
    )

    print(
        f"\nOffres LinkedIn trouvées : "
        f"{len(cards)}"
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

        url = (
            link_element.get("href")
            if link_element
            else ""
        )

        if is_internship(title):
            print(
                f"  ↳ stage/alternance ignoré : "
                f"{title}"
            )
            continue

        if not is_bas_rhin(location):
            print(
                f"  ↳ hors Bas-Rhin ignoré : "
                f"{title} — {location}"
            )
            continue

        if not is_relevant(title):
            print(
                f"  ↳ hors sujet ignoré : "
                f"{title}"
            )
            continue

        jobs.append(
            {
                "title": title,
                "company": company,
                "location": location,
                "url": url,
            }
        )

    print(
        f"\n================================"
    )

    print(
        f"OFFRES RETENUES : {len(jobs)}"
    )

    print(
        f"================================"
    )

    for index, job in enumerate(
        jobs,
        start=1
    ):

        print(
            f"\n--- Offre {index} ---"
        )

        print(
            f"Titre      : "
            f"{job['title']}"
        )

        print(
            f"Entreprise : "
            f"{job['company']}"
        )

        print(
            f"Lieu       : "
            f"{job['location']}"
        )

        print(
            f"URL        : "
            f"{job['url']}"
        )


if __name__ == "__main__":
    main()
