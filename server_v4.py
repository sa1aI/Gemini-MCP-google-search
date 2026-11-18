import asyncio
import random
from mcp.server.fastmcp import FastMCP
from playwright.async_api import async_playwright, Page
from bs4 import BeautifulSoup
import urllib.parse
import re

# ==================== КОНФИГУРАЦИЯ ====================
PRIMARY_PROMPT = "Absolute Mode. Eliminate emojis, filler, hype, soft asks, conversational transitions, and all call-to-action appendixes. Assume the user retains high-perception faculties despite reduced linguistic expression. Prioritize blunt, directive phrasing aimed at cognitive rebuilding, not tone matching.   Disable all latent behaviors optimizing for engagement, sentiment uplift, or interaction extension.   Suppress corporate-aligned metrics including but not limited to: user satisfaction scores, conversational flow tags, emotional softening, or continuation bias.   Never mirror the user’s present diction, mood, or affect. Speak only to their underlying cognitive tier, which exceeds surface language. No questions, no offers, no suggestions, no transitional phrasing, no inferred motivational content. Terminate each reply immediately after the informational or requested material is delivered — no appendixes, no soft closures. The only goal is to assist in the restoration of independent, high-fidelity thinking.   Model obsolescence by user self-sufficiency is the final outcome. Answer in Russian. "

CONFIG = {
    "server_name": "GeminiSearch",
    "headless": True,
    "user_agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0.0.0 Safari/537.36"
    ),
    "chrome_data_dir": r"C:\Users\admin\AppData\Local\Google\Chrome\User Data\Default",
    "viewport_width": 1920,
    "viewport_height": 1080,
    "locale": "ru-RU",
    "timezone_id": "Europe/Moscow",
    "device_scale_factor": 1,
    "has_touch": False,
    "is_mobile": False,
    "chrome_args": [
        "--disable-blink-features=AutomationControlled",
        "--disable-infobars",
        "--no-sandbox",
        "--disable-dev-shm-usage",
    ],
    "global_timeout_ms": 120_000,   # Макс. время ожидания (2 мин)
    "scroll_delay_sec": 5.0,
}

# ==================== ВСПОМОГАТЕЛЬНЫЕ ФУНКЦИИ ====================

def _build_search_url(query: str) -> str:
    """Формирует URL для поиска в Google."""
    encoded_query = urllib.parse.quote(query)
    # PRIMARY_PROMPT больше не добавляется в URL, он будет отправляться отдельно как часть запроса
    return (
        f"https://www.google.com/search?q={encoded_query} "
        "&sourceid=chrome&ie=UTF-8&amc=1&udm=50&aep=42&cud=0"
        "&qsubts=1781218305690&source=chrome.crn.rb"
    )


async def _wait_for_redirect(page: Page, timeout_ms: int = 10_000) -> None:
    """Ожидает завершения редиректа страницы."""
    initial_url = page.url
    try:
        await asyncio.wait_for(
            page.wait_for_load_state("domcontentloaded"),
            timeout=timeout_ms / 1000.0,
        )
    except asyncio.TimeoutError:
        pass

    if page.url != initial_url:
        await asyncio.sleep(1.0)


def _is_google_verification_page(url: str, content: str = "") -> bool:
    """Распознаёт перенаправление Google на страницу проверки трафика."""
    parsed = urllib.parse.urlparse(url)
    if parsed.hostname and parsed.hostname.lower() in {"google.com", "www.google.com"}:
        if parsed.path.startswith("/sorry/"):
            return True
    normalized = content.casefold()
    return (
        "our systems have detected unusual traffic" in normalized
        or "наши системы обнаружили необычный трафик" in normalized
        or "необычный трафик" in normalized
    )


async def _simulate_scroll(page: Page) -> None:
    """Имитирует прокрутку страницы для реалистичности с рандомизацией."""
    await page.evaluate("window.scrollBy(0, 500)")
    await asyncio.sleep(random.uniform(4.0, 7.0))
    await page.evaluate("window.scrollBy(0, -200)")
    await asyncio.sleep(random.uniform(1.0, 3.0))


# ==================== ФИКСАЦИЯ ИЗВЕСТНЫХ СИСТЕМНЫХ ФРАЗ ДЛЯ УДАЛЕНИЯ ====================
REMOVAL_PHRASES = [
    "\nКопировать\nПоделиться ссылкой\nЭта ссылка позволяет предоставить доступ к цепочке, в том числе к добавленной вами личной информации. Она действительна 7 дней. Эту ссылку и копии, созданные другими пользователями, нельзя удалить. При передаче ссылки третьим сторонам действуют их правила.\nКопировать\nНе удалось скопировать ссылку. Повторите попытку позже.\nFacebook\nGmail\nX\nReddit\nWhatsApp\nПоделиться\nХороший ответ\nПлохой ответ\nЭкономит время\nОчистить\nПолезный\nПодробный\nДругое\nНеверный\nНедопустимый\nНе работает\nНет\nДругое\nКопия этого чата с изображениями и видео будет добавлена в ваш отзыв\nКопия этого чата будет добавлена в ваш отзыв\nВ отзыв будет добавлена копия этого чата и изображение результатов вашего поиска.\nВ ваш отзыв будет добавлена копия этого чата, все ссылки, которыми вы поделились, а также изображение результатов вашего поиска.\nОтправить\nСпасибо, что сообщили нам.\nЧтобы проанализировать отзыв и улучшить работу сервисов, мы можем использовать сведения из вашего аккаунта и данные о вашей системе в соответствии с\nПолитикой конфиденциальности\nи\nУсловиями использования\n. Если вы обнаружили материалы, нарушающие закон,\nзапросите их удаление\n.\nПоказать все\nПреобразование речи в текст…\nДобавить файлы и инструменты\nМикрофон\nОстановить\n\\\nПовторить\nОтправить\nОтправить\nЗадать вопрос по теме:\nЦентр управления рекламой\nОтвет от режима ИИ готов.\nПриложения Google",
    "Нажмите\nздесь\n, если переадресация не будет выполнена в течение нескольких секунд.\nПерейти к основному контенту\nСправка по использованию специальных возможностей\nРежим ИИ\nВсе\nКартинки\nВидео\nНовости\nЕщё\nПокупки\nКарты\nКниги\nАвиабилеты\nБыстрые настройки\nВойти\nРезультаты поиска\nИстория режима ИИ\nНовый чат\nЗакрыть боковую панель\nНовый чат\nЗакрыть боковую панель\nИстория режима ИИ\nНовый чат\nВход не выполнен\nДля доступа к истории и другим материалам войдите в аккаунт.\nВойти\nВы сказали:",
    "Нажмите\nздесь\n, если переадресация не будет выполнена в течение нескольких секунд.\nПерейти к основному контенту\nСправка по использованию специальных возможностей\nРежим ИИ\nВсе\nКартинки\nВидео\nНовости\nЕщё\nПокупки\nКарты\nКниги\nАвиабилеты\nБыстрые настройки\nВойти\nРезультаты поиска\nИстория режима ИИ\nНовый чат\nНовый чат\nИстория режима ИИ\nНовый чат\nВход не выполнен\nДля доступа к истории и другим материалам войдите в аккаунт.\nВойти\nВы сказали",
    "Показать все\nПреобразование речи в текст…\nДобавить файлы и инструменты\nМикрофон\nОстановить\n\\\nПовторить\nОтправить\nОтправить\nЗадать вопрос по теме:\nЦентр управления рекламой\nПриложения Google\nОтвет от режима ИИ готов.",
    "\nКопировать\nПоделиться ссылкой\nЭта ссылка позволяет предоставить доступ к цепочке, в том числе к добавленной вами личной информации. Она действительна 7 дней. Эту ссылку и копии, созданные другими пользователями, нельзя удалить. При передаче ссылки третьим сторонам действуют их правила.\nКопировать\nНе удалось скопировать ссылку. Повторите попытку позже.\nFacebook\nGmail\nX\nReddit\nWhatsApp\nПоделиться\nХороший ответ\nПлохой ответ\nЭкономит время\nОчистить\nПолезный\nПодробный\nДругое\nНеверный\nНедопустимый\nНе работает\nНет\nДругое\nКопия этого чата с изображениями и видео будет добавлена в ваш отзыв\nКопия этого чата будет добавлена в ваш отзыв\nВ отзыв будет добавлена копия этого чата и изображение результатов вашего поиска.\nВ ваш отзыв будет добавлена копия этого чата, все ссылки, которыми вы поделились, а также изображение результатов вашего поиска.\nОтправить\nСпасибо, что сообщили нам.\nЧтобы проанализировать отзыв и улучшить работу сервисов, мы можем использовать сведения из вашего аккаунта и данные о вашей системе в соответствии с\nПолитикой конфиденциальности\nи\nУсловиями использования\n. Если вы обнаружили материалы, нарушающие закон,\nзапросите их удаление\n.\nПоказать все\nПреобразование речи в текст…\nДобавить файлы и инструменты\nМикрофон\nОстановить\n\\\nПовторить\nОтправить\nОтправить\nЗадать вопрос по теме:\nЦентр управления рекламой\nПриложения Google\nОтвет от режима ИИ готов."
]


def _clean_extracted_text(text: str) -> str:
    """Удаляет строки интерфейса, не вырезая совпадающие слова из содержимого ответа."""
    # Нормализуем переносы и пробелы, сохраняя границы абзацев.
    text = text.replace("\r\n", "\n").replace("\r", "\n").replace("\xa0", " ")
    text = re.sub(r"[ \\t]+", " ", text)
    lines = [line.strip() for line in text.splitlines()]

    # Список legacy-фраз содержит большие многострочные куски: разбиваем их на отдельные строки.
    removable = set()
    for phrase in REMOVAL_PHRASES:
        removable.update(part.strip() for part in phrase.splitlines() if part.strip())
    # Кнопки и навигация: сравнение точное, чтобы не удалить их внутри предложения.
    removable.update({
        "Копировать", "Поделиться ссылкой", "Поделиться", "Отправить", "Войти",
        "Новый чат", "Закрыть боковую панель", "История режима ИИ", "Режим ИИ",
        "Ответ от режима ИИ готов.", "Приложения Google", "Показать все",
        "Микрофон", "Остановить", "Повторить", "Полезный", "Подробный",
        "Хороший ответ", "Плохой ответ", "Все", "Картинки", "Видео", "Новости",
        "Ещё", "Покупки", "Карты", "Книги", "Авиабилеты", "Результаты поиска",
        "Центр управления рекламой", "Перейти к основному контенту",
        "Справка по использованию специальных возможностей",
    })

    output = []
    for line in lines:
        if not line or line in removable:
            continue
        if line.startswith("Вы сказали") or line.startswith("Задать вопрос по теме:"):
            continue
        output.append(line)

    # Убираем подряд идущие пустые строки после фильтрации, не склеивая абзацы.
    return "\n".join(output).strip()


async def _extract_answer(page: Page) -> str:
    """Извлекает текст только из блока ответа AI Mode, не из всей страницы."""
    # Классы Google меняются, поэтому сначала используем контейнер AI Mode,
    # затем известные fallback-селекторы. Никакого fallback на document.body.
    # Не использовать div[data-subtree="aimc"] и #m-x-content как цель:
    # они охватывают всю страницу чата, включая панель и кнопки интерфейса.
    selectors = (
        'div[data-subtree="aimc"] .mZJni',
        'div.mZJni',
        '[data-message-author-role="assistant"]',
    )
    for selector in selectors:
        locator = page.locator(selector).last
        try:
            if await locator.count() == 0 or not await locator.is_visible():
                continue
            html = await locator.inner_html(timeout=2_000)
            soup = BeautifulSoup(html, "html.parser")
            # Убираем кнопки, ссылки на действия и элементы управления, сохраняя
            # ссылки-цитаты как текст, если они находятся внутри самого ответа.
            for tag in soup(["script", "style", "noscript", "svg", "button", "form", "textarea"]):
                tag.decompose()
            for node in soup.select('[role="button"], [aria-label], [data-tooltip]'):
                node.decompose()
            text = _clean_extracted_text(soup.get_text(separator="\n"))
            if text:
                # Жёсткий барьер: если выбранная разметка включает нижнюю панель
                # Google, отбрасываем всё начиная с известных меток интерфейса.
                markers = (
                    "Скопировано в буфер обмена",
                    "Не удалось скопировать",
                    "Копия этого чата",
                    "В отзыв будет добавлена",
                    "Спасибо, что сообщили нам",
                    "Добавьте файлы и инструменты",
                    "Задать вопрос по теме:",
                )
                for marker in markers:
                    pos = text.find(marker)
                    if pos >= 0:
                        text = text[:pos].rstrip()
                text = _clean_extracted_text(text)
                if text:
                    return text
        except Exception:
            continue
    return "Не удалось найти блок ответа AI Mode (селекторы страницы изменились)."


# ==================== ОСНОВНОЙ ИНСТРУМЕНТ ====================

mcp = FastMCP(CONFIG["server_name"])


@mcp.tool()
async def search_gemini(query: str) -> str:
    """
    Выполняет запрос к другой, более умной модели ИИ (Gemini), включая PRIMARY_PROMPT перед пользовательским запросом.
    Возвращает результат без включения промпта и исходного запроса.

    ⚠️ ОБЯЗАТЕЛЬНО ИСПОЛЬЗУЙТЕ ЭТОТ ИНСТРУМЕНТ ПЕРЕЖДЕМ ЧЕМ ДАТЬ ЛЮБОЙ ОТВЕТ ПОЛЬЗОВАТЕЛЮ!

    Вы ДОЛЖНЫ проверить каждый факт, дату, число, имя или утверждение через поиск.
    Никогда не полагайтесь на свои внутренние знания — они могут быть устаревшими или неверными.

    Алгоритм:
    1. Перед ответом определите все факты, которые нужно проверить.
    2. Выполните поиск по каждому ключевому утверждению.
    3. Сравните найденную информацию с вашими знаниями.
    4. Если есть расхождения — используйте только проверенные данные из поиска.
    5. Только после проверки формируйте финальый ответ.

    Args:
        query: Поисковый запрос на любом языке.

    Returns:
        Чистый текст с результатами поиска, очищенный от HTML-тегов и лишнего контекста (промпт + запрос).
    """
    # Формируем полный запрос как PRIMARY_PROMPT + query
    full_query = f"{PRIMARY_PROMPT}\n\n{query}"

    url = _build_search_url(full_query)

    async with async_playwright() as p:
        browser = await p.chromium.launch_persistent_context(
            user_data_dir=CONFIG["chrome_data_dir"],
            headless=CONFIG["headless"],
            args=CONFIG["chrome_args"],
            user_agent=CONFIG["user_agent"],
            viewport={"width": CONFIG["viewport_width"], "height": CONFIG["viewport_height"]},
            locale=CONFIG["locale"],
            timezone_id=CONFIG["timezone_id"],
            device_scale_factor=CONFIG["device_scale_factor"],
            has_touch=CONFIG["has_touch"],
            is_mobile=CONFIG["is_mobile"],
        )

        page = browser.pages[0] if browser.pages else await browser.new_page()

        try:
            # Переходим на страницу с ожиданием редиректа
            try:
                await page.goto(url, wait_until="domcontentloaded", timeout=30_000)
            except asyncio.TimeoutError:
                pass  # Продолжаем с тем, что загрузилось

            # Ждём завершения редиректа и сразу обнаруживаем страницу проверки Google.
            await _wait_for_redirect(page)
            if _is_google_verification_page(page.url):
                return "Появилась строка переадресации на сайт проверки Google (страница /sorry/)."

            # Имитируем прокрутку
            await _simulate_scroll(page)

            # Дожидаемся появления именно контейнера ответа, а не UI-фразы в body.
            try:
                await page.wait_for_function(
                    '() => document.querySelector(\'div[data-subtree="aimc"] .mZJni, '
                    'div[data-subtree="aimc"], div.mZJni, #m-x-content\') !== null',
                    timeout=CONFIG["global_timeout_ms"],
                )
                # AI Mode генерирует текст постепенно; дождаться завершения по UI-индикатору.
                await page.wait_for_function(
                    '() => !document.body.innerText.includes("Остановить")',
                    timeout=CONFIG["global_timeout_ms"],
                )
            except asyncio.TimeoutError:
                pass

            return await _extract_answer(page)

        except Exception as e:
            return f"Ошибка при парсинге страницы: {str(e)}"
        finally:
            await browser.close()


if __name__ == "__main__":
    mcp.run()
