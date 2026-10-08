import json
import re
import unicodedata
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


LEBONCOIN_URLS = {
    "location": "https://www.leboncoin.fr/cl/locations/cp_strasbourg",
    "vente": "https://www.leboncoin.fr/cl/ventes_immobilieres/cp_strasbourg",
}

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/153.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8",
}


def normalize_text(text):
    if not text:
        return ""

    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )

    return re.sub(r"\s+", " ", text).strip()


def extract_number(text):
    if not text:
        return None

    match = re.search(
        r"(\d[\d\s.,]*)",
        text.replace("\xa0", " ")
    )

    if not match:
        return None

    value = match.group(1)
    value = value.replace(" ", "").replace("\xa0", "")
    value = value.replace(".", "").replace(",", ".")

    try:
        return float(value)
    except ValueError:
        return None


def extract_image(card):
    image = card.find("img")

    if not image:
        return None

    return (
        image.get("src")
        or image.get("data-src")
        or image.get("data-lazy-src")
    )


def extract_url(card):
    link = card.find("a", href=True)

    if not link:
        return None

    return urljoin(
        "https://www.leboncoin.fr",
        link["href"]
    )


def parse_card(card, search_type):
    text = normalize_text(card.get_text(" ", strip=True))

    if not text:
        return None

    # Prix
    price_match = re.search(
        r"([\d\s\u00a0]+)\s*€",
        text
    )

    price = None

    if price_match:
        price = extract_number(price_match.group(1))

    # Surface
    surface_match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*m²",
        text
    )

    surface = None

    if surface_match:
        surface = float(
            surface_match.group(1).replace(",", ".")
        )

    # Nombre de pièces
    rooms_match = re.search(
        r"(\d+)\s*pièces?",
        text,
        re.IGNORECASE
    )

    rooms = None

    if rooms_match:
        rooms = int(rooms_match.group(1))

    # DPE
    dpe_match = re.search(
        r"Classe énergie\s*([A-G])",
        text,
        re.IGNORECASE
    )

    dpe = None

    if dpe_match:
        dpe = dpe_match.group(1).upper()

    # Type de bien
    property_type = None

    if re.search(r"\bMaison\b", text, re.IGNORECASE):
        property_type = "Maison"
    elif re.search(r"\bAppartement\b", text, re.IGNORECASE):
        property_type = "Appartement"

    # Localisation : on cherche un code postal + texte
    location_match = re.search(
        r"\b(67\d{3})\s+(.+?)(?=\s+(?:aujourd'hui|hier|\d{1,2}/\d{1,2}/\d{4})|$)",
        text,
        re.IGNORECASE
    )

    location = None

    if location_match:
        location = (
            f"{location_match.group(1)} "
            f"{location_match.group(2)}"
        )

    return {
        "type": search_type,
        "title": f"{property_type or 'Bien'}"
                 f"{f' · {rooms} pièces' if rooms else ''}"
                 f"{f' · {surface:g}m²' if surface else ''}",
        "price": price,
        "surface": surface,
        "rooms": rooms,
        "dpe": dpe,
        "property_type": property_type,
        "location": location,
        "image_url": extract_image(card),
        "url": extract_url(card),
        "raw_text": text,
    }


def search_leboncoin(search_type):
    url = LEBONCOIN_URLS[search_type]

    print()
    print("=" * 80)
    print(f"Recherche : {search_type.upper()}")
    print("=" * 80)
    print(url)

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    print(f"HTTP {response.status_code}")
    print(f"Taille de la réponse : {len(response.text)} caractères")

    response.raise_for_status()

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    # Les annonces Leboncoin utilisent actuellement des cartes
    # avec des liens vers /ad/
    cards = []

    for link in soup.find_all("a", href=True):
        href = link.get("href", "")

        if "/ad/" in href:
            card = link

            # On remonte jusqu'à un conteneur raisonnable
            for _ in range(5):
                if card.parent:
                    card = card.parent

            cards.append(card)

    print(f"Éléments d'annonces détectés : {len(cards)}")

    results = []

    seen_urls = set()

    for card in cards:
        job = parse_card(
            card,
            search_type
        )

        if not job:
            continue

        if not job["url"]:
            continue

        if job["url"] in seen_urls:
            continue

        seen_urls.add(job["url"])

        # Premier filtre
        if job["price"] is not None:
            if search_type == "location" and job["price"] > 2000:
                continue

            if search_type == "vente" and job["price"] > 500000:
                continue

        if job["rooms"] is not None and job["rooms"] < 4:
            continue

        if job["surface"] is not None and job["surface"] < 90:
            continue

        if job["dpe"] and job["dpe"] > "E":
            continue

        results.append(job)

    print(
        f"Annonces après filtrage : {len(results)}"
    )

    return results


def main():
    all_results = []

    for search_type in LEBONCOIN_URLS:
        results = search_leboncoin(search_type)
        all_results.extend(results)

    print()
    print("=" * 80)
    print("RÉSULTATS")
    print("=" * 80)

    for index, property_data in enumerate(
        all_results,
        start=1
    ):
        print()
        print(f"--- {index} ---")
        print(
            f"Type        : {property_data['type']}"
        )
        print(
            f"Type bien   : {property_data['property_type']}"
        )
        print(
            f"Prix        : {property_data['price']}"
        )
        print(
            f"Surface     : {property_data['surface']} m²"
        )
        print(
            f"Pièces      : {property_data['rooms']}"
        )
        print(
            f"DPE         : {property_data['dpe']}"
        )
        print(
            f"Localisation: {property_data['location']}"
        )
        print(
            f"Image       : {property_data['image_url']}"
        )
        print(
            f"URL         : {property_data['url']}"
        )

    with open(
        "leboncoin_test.json",
        "w",
        encoding="utf-8"
    ) as file:
        json.dump(
            all_results,
            file,
            ensure_ascii=False,
            indent=2
        )

    print()
    print("Résultats enregistrés dans leboncoin_test.json")


if __name__ == "__main__":
    main()
