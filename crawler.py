import json
import re
import time
from collections import Counter, deque
from urllib.parse import urlparse, urljoin, urldefrag

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.common.by import By


class DzenCrawler:
    def __init__(self, start_url="https://dzen.ru/", max_depth=1, max_pages=10):
        self.start_url = start_url
        self.max_depth = max_depth
        self.max_pages = max_pages

        self.visited = set()
        self.word_counter = Counter()

        self.stop_words = {
            # Общие русские стоп-слова
            "и", "в", "во", "не", "что", "он", "она", "оно", "они", "на", "я", "с", "со",
            "как", "а", "то", "все", "всё", "так", "его", "ее", "её", "но", "да", "ты",
            "к", "у", "же", "вы", "за", "бы", "по", "только", "мне", "было", "вот", "от",
            "меня", "еще", "ещё", "нет", "о", "об", "из", "ему", "теперь", "когда", "даже",
            "ну", "вдруг", "ли", "если", "уже", "или", "ни", "быть", "был", "была", "были",
            "него", "до", "вас", "нибудь", "опять", "уж", "вам", "ведь", "там", "потом",
            "себя", "ничего", "ей", "может", "тут", "где", "есть", "надо", "ней", "для",
            "мы", "тебя", "их", "чем", "сам", "сама", "сами", "чтоб", "чтобы", "без",
            "будто", "чего", "раз", "тоже", "себе", "под", "будет", "будут", "тогда",
            "кто", "этот", "эта", "это", "эти", "того", "потому", "этого", "какой", "какая",
            "какие", "какое", "совсем", "ним", "здесь", "этом", "один", "одна", "одно",
            "почти", "мой", "моя", "моё", "мои", "тем", "нее", "неё", "сейчас", "куда",
            "зачем", "всех", "никогда", "можно", "при", "наконец", "два", "две", "три",
            "другой", "другая", "другое", "другие", "хоть", "после", "над", "больше",
            "тот", "та", "те", "ту", "через", "нас", "про", "них", "много", "разве",
            "эту", "впрочем", "хорошо", "свою", "свой", "своя", "свои", "этой", "перед",
            "иногда", "лучше", "чуть", "том", "нельзя", "такой", "такая", "такие", "им",
            "более", "менее", "всегда", "конечно", "всю", "между", "которые", "который", "которая"

            # Служебные слова Дзена и интерфейса
            "dzen", "дзен", "яндекс", "yandex", "новости", "новость", "главная",
            "лента", "канал", "каналы", "статья", "статьи", "публикация", "публикации",
            "читать", "читайте", "прочитать", "подписаться", "подписка", "подписчики",
            "комментарии", "комментарий", "комментировать", "реклама", "рекламный",
            "показать", "скрыть", "открыть", "закрыть", "далее", "назад", "вперед",
            "вперёд", "еще", "ещё", "поделиться", "ссылка", "источник", "автор",
            "фото", "видео", "смотреть", "смотрели", "посмотреть", "просмотры",
            "просмотров", "читали", "прочитали", "лайк", "лайки", "дизлайк", "оценить",

            # Время, даты, счетчики
            "тыс", "млн", "млрд", "час", "часа", "часов", "мин", "минута",
            "минуты", "минут", "день", "дня", "дней", "неделя", "недели", "недель",
            "месяц", "месяца", "месяцев", "год", "года", "лет", "сегодня",
            "вчера", "завтра", "утром", "днем", "днём", "вечером", "ночью",
            "января", "февраля", "марта", "апреля", "мая", "июня", "июля",
            "августа", "сентября", "октября", "ноября", "декабря",

        }

        options = Options()
        options.add_argument("--window-size=1400,900")
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_argument("--disable-notifications")
        options.add_argument("--lang=ru-RU")

        # Браузер специально не скрыт, чтобы было видно, что сайт открылся.
        # Если нужно запускать без окна, раскомментируйте строку ниже:
        # options.add_argument("--headless=new")

        self.driver = webdriver.Chrome(options=options)

    def is_internal_link(self, url):
        parsed = urlparse(url)
        return parsed.netloc == "dzen.ru" or parsed.netloc.endswith(".dzen.ru")

    def normalize_url(self, base_url, href):
        if not href:
            return None

        href = href.strip()

        if href.startswith(("javascript:", "mailto:", "tel:")):
            return None

        absolute = urljoin(base_url, href)
        absolute, _ = urldefrag(absolute)

        parsed = urlparse(absolute)

        if parsed.scheme not in ("http", "https"):
            return None

        if not self.is_internal_link(absolute):
            return None

        return absolute

    def scroll_page(self):
        for _ in range(5):
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)

    def get_page_text_and_links(self, url):
        print(f"\n[OPEN] {url}")

        self.driver.get(url)
        time.sleep(7)

        self.scroll_page()

        try:
            body_text = self.driver.find_element(By.TAG_NAME, "body").text
        except Exception:
            body_text = ""

        html = self.driver.page_source
        soup = BeautifulSoup(html, "html.parser")

        links = []
        for a in soup.find_all("a", href=True):
            link = self.normalize_url(url, a["href"])
            if link:
                links.append(link)

        return body_text, links

    def tokenize(self, text):
        # Нормализация: "ё" -> "е", чтобы стоп-слова точно срабатывали.
        text = text.lower().replace("ё", "е")

        normalized_stop_words = {word.lower().replace("ё", "е") for word in self.stop_words}

        words = re.findall(r"[а-яa-z]{3,}", text)

        result = []

        for word in words:
            if word in normalized_stop_words:
                continue

            # Убираем технические слова, которые иногда попадают из HTML/CSS/JS.
            if word.startswith(("http", "www", "com", "ru")):
                continue

            result.append(word)

        return result

    def crawl(self):
        queue = deque()
        queue.append((self.start_url, 0))

        while queue and len(self.visited) < self.max_pages:
            url, depth = queue.popleft()

            if url in self.visited:
                continue

            try:
                text, links = self.get_page_text_and_links(url)
            except Exception as e:
                print(f"[ERROR] {url} -> {e}")
                continue

            self.visited.add(url)

            words = self.tokenize(text)
            self.word_counter.update(words)

            print(f"[INFO] depth: {depth}")
            print(f"[INFO] symbols in text: {len(text)}")
            print(f"[INFO] words found: {len(words)}")
            print(f"[INFO] unique words: {len(set(words))}")
            print(f"[INFO] links found: {len(links)}")

            if depth < self.max_depth:
                for link in links:
                    if link not in self.visited and len(self.visited) + len(queue) < self.max_pages:
                        queue.append((link, depth + 1))

    def save_results(self, filename="result.json"):
        top_words = self.word_counter.most_common(10)

        result = {
            "start_url": self.start_url,
            "pages_visited": len(self.visited),
            "top_words": [
                {
                    "word": word,
                    "count": count
                }
                for word, count in top_words
            ]
        }

        with open(filename, "w", encoding="utf-8") as file:
            json.dump(result, file, ensure_ascii=False, indent=4)

        return result

    def close(self):
        self.driver.quit()


def main():
    crawler = DzenCrawler(
        start_url="https://dzen.ru/",
        max_depth=1,
        max_pages=10
    )

    try:
        crawler.crawl()
        result = crawler.save_results("result.json")

        print("\nТоп 10 слов:")

        if not result["top_words"]:
            print("Слова не найдены.")
        else:
            for index, item in enumerate(result["top_words"], start=1):
                print(f"{index}. {item['word']} — {item['count']}")

        print("\nРезультат сохранён в result.json")

    finally:
        crawler.close()


if __name__ == "__main__":
    main()
