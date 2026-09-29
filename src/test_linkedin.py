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


def main():

    print("Connexion à LinkedIn...")

    response = requests.get(
        URL,
        headers=HEADERS,
        timeout=30
    )

    print(
        f"HTTP {response.status_code}"
    )

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

    # Les résultats LinkedIn utilisent généralement
    # la classe base-search-card.
    cards = soup.select(
        "div.base-card"
    )

    print(
        f"\nCartes trouvées : {len(cards)}"
    )

    for index, card in enumerate(
        cards[:10],
        start=1
    ):

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

        print(
            f"\n--- Offre {index} ---"
        )

        print(
            f"Titre      : {title}"
        )

        print(
            f"Entreprise : {company}"
        )

        print(
            f"Lieu       : {location}"
        )

        print(
            f"URL        : {url}"
        )


if __name__ == "__main__":
    main()
