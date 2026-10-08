import re
import json
from playwright.sync_api import sync_playwright


URLS = {
    "location": "https://www.leboncoin.fr/cl/locations/cp_strasbourg",
    "vente": "https://www.leboncoin.fr/cl/ventes_immobilieres/cp_strasbourg",
}


def clean(text):
    if not text:
        return ""
    return re.sub(r"\s+", " ", text).strip()


def parse_price(text):
    match = re.search(r"([\d\s]+)\s*€", text)

    if not match:
        return None

    return int(
        match.group(1)
        .replace(" ", "")
        .replace("\xa0", "")
    )


def parse_surface(text):
    match = re.search(
        r"(\d+(?:[.,]\d+)?)\s*m²",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    return float(
        match.group(1).replace(",", ".")
    )


def parse_rooms(text):
    match = re.search(
        r"(\d+)\s*pièces?",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    return int(match.group(1))


def parse_dpe(text):
    match = re.search(
        r"(?:DPE|Classe énergie|énergie).*?\b([A-G])\b",
        text,
        re.IGNORECASE
    )

    if not match:
        return None

    return match.group(1).upper()


def parse_property_type(text):
    if re.search(r"\bmaison\b", text, re.IGNORECASE):
        return "Maison"

    if re.search(r"\bappartement\b", text, re.IGNORECASE):
        return "Appartement"

    return None


def extract_card_data(card, search_type):
    text = clean(
        card.inner_text(timeout=3000)
    )

    if not text:
        return None

    links = card.locator("a")

    url = None

    for i in range(min(links.count(), 10)):
        href = links.nth(i).get_attribute("href")

        if href and "/ad/" in href:
            if href.startswith("/"):
                url = "https://www.leboncoin.fr" + href
            else:
                url = href
            break

    if not url:
        return None

    image_url = None

    images = card.locator("img")

    if images.count() > 0:
        image_url = (
            images.nth(0).get_attribute("src")
            or images.nth(0).get_attribute("data-src")
        )

    return {
        "type": search_type,
        "price": parse_price(text),
        "surface": parse_surface(text),
        "rooms": parse_rooms(text),
        "dpe": parse_dpe(text),
        "property_type": parse_property_type(text),
        "image_url": image_url,
        "url": url,
        "raw_text": text,
    }


def search(search_type, url, page):

    print()
    print("=" * 80)
    print(f"RECHERCHE : {search_type.upper()}")
    print("=" * 80)

    print(f"URL : {url}")

    response = page.goto(
        url,
        wait_until="domcontentloaded",
        timeout=60000
    )

    print(f"HTTP : {response.status if response else 'inconnu'}")

    page.wait_for_timeout(5000)

    print(
        f"Titre page : {page.title()}"
    )

    print(
        f"URL finale : {page.url}"
    )

    # Sauvegarde de la page pour diagnostic
    page.screenshot(
        path=f"leboncoin_{search_type}.png",
        full_page=True
    )

    # Recherche de liens vers les annonces
    ad_links = page.locator(
        'a[href*="/ad/"]'
    )

    count = ad_links.count()

    print(
        f"Liens d'annonces détectés : {count}"
    )

    results = []
    seen = set()

    for i in range(count):

        link = ad_links.nth(i)

        try:
            href = link.get_attribute("href")
        except Exception:
            continue

        if not href:
            continue

        if href.startswith("/"):
            href = "https://www.leboncoin.fr" + href

        if href in seen:
            continue

        seen.add(href)

        # On remonte dans l'arbre DOM pour récupérer
        # le conteneur de l'annonce.
        card = link

        for _ in range(6):
            try:
                parent = card.locator("..")

                if parent.count() == 0:
                    break

                card = parent

            except Exception:
                break

        try:
            data = extract_card_data(
                card,
                search_type
            )
        except Exception:
            continue

        if not data:
            continue

        # Filtres
        if data["price"] is not None:

            if search_type == "location":
                if data["price"] > 2000:
                    continue

            if search_type == "vente":
                if data["price"] > 500000:
                    continue

        if (
            data["rooms"] is not None
            and data["rooms"] < 4
        ):
            continue

        if (
            data["surface"] is not None
            and data["surface"] < 90
        ):
            continue

        if (
            data["dpe"]
            and data["dpe"] > "E"
        ):
            continue

        if any(item["url"] == data["url"] for item in results):
            continue

    results.append(data)

    return results


def main():

    all_results = []

    with sync_playwright() as p:

        browser = p.chromium.launch(
            headless=False
        )

        page = browser.new_page(
            viewport={
                "width": 1920,
                "height": 1080
            },
            locale="fr-FR"
        )

        for search_type, url in URLS.items():

            try:
                results = search(
                    search_type,
                    url,
                    page
                )

                print(
                    f"Annonces retenues : {len(results)}"
                )

                all_results.extend(results)

            except Exception as error:

                print()
                print(
                    f"ERREUR {search_type} : {error}"
                )

        browser.close()

    print()
    print("=" * 80)
    print("RÉSULTATS")
    print("=" * 80)

    for i, item in enumerate(
        all_results,
        start=1
    ):

        print()
        print(f"--- ANNONCE {i} ---")
        print(
            f"Type       : {item['type']}"
        )
        print(
            f"Bien       : {item['property_type']}"
        )
        print(
            f"Prix       : {item['price']} €"
        )
        print(
            f"Surface    : {item['surface']} m²"
        )
        print(
            f"Pièces     : {item['rooms']}"
        )
        print(
            f"DPE        : {item['dpe']}"
        )
        print(
            f"Image      : {item['image_url']}"
        )
        print(
            f"URL        : {item['url']}"
        )

        print(
            f"Texte      : "
            f"{item['raw_text'][:300]}"
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
    print(
        f"Total : {len(all_results)} annonces"
    )

    print(
        "Résultats enregistrés dans "
        "leboncoin_test.json"
    )


if __name__ == "__main__":
    main()
