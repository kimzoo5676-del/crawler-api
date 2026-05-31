import requests
from bs4 import BeautifulSoup

URL = "https://realpython.github.io/fake-jobs/"


def fetch_html(url):
    response = requests.get(url)
    response.raise_for_status()
    return response.text


def parse_jobs(html):
    soup = BeautifulSoup(html, "html.parser")
    cards = soup.select("div.card-content")
    print(f"찾은 카드 수: {len(cards)}")
    return cards


def extract_one(card):
    title = card.select_one("h2.title").get_text(strip=True)
    company = card.select_one("h3.company").get_text(strip=True)
    location = card.select_one("p.location").get_text(strip=True)
    links = card.select("footer.card-footer a")
    url = links[1]["href"]
    return {
        "title": title,
        "company": company,
        "location": location,
        "url": url,
        "source": "fake-jobs",
    }


def crawl():
    html = fetch_html(URL)
    cards = parse_jobs(html)
    return [extract_one(card) for card in cards]


if __name__ == "__main__":
    jobs = crawl()
    print(f"총 {len(jobs)}개 수집")
    print(jobs[0])
