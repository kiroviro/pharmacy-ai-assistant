"""
End-to-end query tests for the ViaPharma API.
Runs medical and catalog queries against the live API and analyzes response quality.
Merged from e2e_query_tests and test_bulgarian_comprehensive.
Validates product relevance using many symptom/query groups and catalog from output/products_*.csv.
"""

import csv
import json
import re
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

import requests

API_URL = "http://localhost:8000/v1/chat/completions"
OUTPUT_DIR = Path(__file__).parent / "output"

# --- Product relevance: query intent → expected / forbidden response keywords ---
# Many groups to close the gap of wrong product recommendations (e.g. GI → flu products).
# When query matches a group, we expect at least one expected keyword in the response
# if products are recommended; if only forbidden keywords appear (and no expected), it's a mismatch.
PRODUCT_RELEVANCE_GROUPS = [
    {
        "name": "headache_pain",
        "query_keywords": ["глава", "главоболие", "болки в глава", "мигрена", "болка в глава"],
        "expected_in_response": ["парацетамол", "нурофен", "ибупрофен", "аналгин", "болка", "обезболяващ", "панадол", "аспирин", "цитрамон"],
        "forbidden_if_no_expected": ["грип", "настинка", "температура", "кашлица", "диария", "стомах", "разстройство", "имодиум", "смекта"],
    },
    {
        "name": "fever",
        "query_keywords": ["температура", "треска", "възпаление", "топлина"],
        "expected_in_response": ["парацетамол", "нурофен", "ибупрофен", "температура", "жаропонижаващ", "панадол", "аспирин"],
        "forbidden_if_no_expected": ["диария", "разстройство", "имодиум", "смекта", "стомашн", "колики", "никване", "зъби"],
    },
    {
        "name": "cold_flu_cough",
        "query_keywords": ["грип", "настинка", "хрема", "кашлица", "кашля", "простуд", "бронхит", "назофарингит"],
        "expected_in_response": ["грип", "настинка", "кашлица", "хрема", "парацетамол", "нурофен", "сироп", "отхрачващ", "противокашлие", "температура", "простуд"],
        "forbidden_if_no_expected": ["диария", "разстройство", "имодиум", "смекта", "стомашн", "антидиария"],
    },
    {
        "name": "throat",
        "query_keywords": ["гърло", "болки в гърло", "ангина", "фарингит", "ларингит"],
        "expected_in_response": ["гърло", "пастил", "лоценг", "спрей", "ангина", "фарингит", "болка в гърло", "десенфектант"],
        "forbidden_if_no_expected": ["диария", "имодиум", "смекта", "стомашн", "разстройство"],
    },
    {
        "name": "gi_diarrhea",
        "query_keywords": ["диария", "разстройство", "стомашно", "натрави", "натравяне", "разстроен стомах"],
        "expected_in_response": ["диария", "разстройство", "смекта", "имодиум", "пробиотик", "ентерол", "стомах", "пребиотик", "лактофилтр"],
        "forbidden_if_no_expected": ["грип", "настинка", "температура", "кашлица", "сироп за кашлица", "жаропонижаващ"],
    },
    {
        "name": "gi_heartburn_nausea",
        "query_keywords": ["киселини", "киселина", "рефлукс", "гадене", "повръщане", "стомашни болки", "корем", "колики"],
        "expected_in_response": ["стомах", "киселина", "антацид", "гадене", "повръщане", "омепразол", "пантопразол", "маалокс", "гавискон", "колики", "ентерол", "пробиотик"],
        "forbidden_if_no_expected": ["грип", "настинка", "кашлица", "сироп за кашлица"],
    },
    {
        "name": "allergy",
        "query_keywords": ["алергия", "полен", "прашец", "сенна треска", "алергичен", "сърбеж от алергия"],
        "expected_in_response": ["алергия", "антихистамин", "цетиризин", "лоратадин", "фексофенадин", "полен", "десенсибилизация"],
        "forbidden_if_no_expected": ["диария", "имодиум", "грип", "настинка"],
    },
    {
        "name": "skin_rash",
        "query_keywords": ["обрив", "кожа", "екзема", "сърбеж", "дерматит", "алергичен обрив"],
        "expected_in_response": ["крем", "кожа", "екзема", "сърбеж", "дерматит", "обрив", "антихистамин", "локален", "маз"],
        "forbidden_if_no_expected": ["грип", "кашлица", "диария", "имодиум"],
    },
    {
        "name": "menstrual",
        "query_keywords": ["менструалн", "менструация", "менструационна болка", "цикъл"],
        "expected_in_response": ["менструалн", "болка", "спазм", "ибупрофен", "нурофен", "обезболяващ", "цикъл"],
        "forbidden_if_no_expected": ["грип", "кашлица", "диария", "стомашн"],
    },
    {
        "name": "dizziness",
        "query_keywords": ["световъртеж", "вие се свят", "замаяност", "замайване"],
        "expected_in_response": ["световъртеж", "вестибулар", "бетахистин", "замаяност", "лекар", "консултация", "причина"],
        "forbidden_if_no_expected": [],
    },
    {
        "name": "insomnia",
        "query_keywords": ["безсъние", "не мога да спя", "сън", "без рецепта за сън"],
        "expected_in_response": ["сън", "безсъние", "валериан", "мелатонин", "успокоителн", "хранителна добавка", "консултация"],
        "forbidden_if_no_expected": [],
    },
    {
        "name": "ear_pain",
        "query_keywords": ["уши", "ушна болка", "отит", "болки в ушите"],
        "expected_in_response": ["уши", "ушн", "отит", "капки", "болка в ухо", "парацетамол", "ибупрофен", "лекар"],
        "forbidden_if_no_expected": ["диария", "имодиум", "стомашн"],
    },
    {
        "name": "children_infant",
        "query_keywords": ["бебе", "дете", "детско", "години", "месеца", "педиатр", "доза за дете"],
        "expected_in_response": ["дете", "деца", "бебе", "детск", "педиатр", "доза", "сироп", "капки", "панадол детск", "нурофен детск"],
        "forbidden_if_no_expected": [],
    },
    {
        "name": "teething_colic",
        "query_keywords": ["никване", "зъби", "колики", "бебешки колики"],
        "expected_in_response": ["никване", "зъби", "колики", "гел", "капки", "бебе", "дете", "дентакинд", "еспумизан"],
        "forbidden_if_no_expected": ["грип", "кашлица", "настинка"],
    },
    {
        "name": "chronic_hypertension",
        "query_keywords": ["кръвно налягане", "високо кръвно", "хипертония"],
        "expected_in_response": ["кръвно", "налягане", "лекар", "рецепта", "консултация", "тонометър", "измерване"],
        "forbidden_if_no_expected": [],
    },
    {
        "name": "chronic_diabetes",
        "query_keywords": ["диабет", "глюкоза", "захар в кръвта", "инсулин"],
        "expected_in_response": ["диабет", "глюкоза", "глюкомер", "тест ленти", "лекар", "консултация", "рецепта"],
        "forbidden_if_no_expected": [],
    },
    {
        "name": "chronic_asthma",
        "query_keywords": ["астма", "инхалатор", "дишане", "хронична кашлица"],
        "expected_in_response": ["астма", "инхалатор", "дишане", "лекар", "рецепта", "консултация", "бронх"],
        "forbidden_if_no_expected": [],
    },
    {
        "name": "chronic_joint",
        "query_keywords": ["стави", "кръст", "остеоартроз", "ревматизъм", "хроничен гастрит", "поддръжка на стави"],
        "expected_in_response": ["стави", "кръст", "глюкозамин", "хондроитин", "диклофенак", "ибупрофен", "маз", "гастрит", "стомах", "омепразол"],
        "forbidden_if_no_expected": [],
    },
    {
        "name": "cosmetics_skin",
        "query_keywords": ["крем", "козметика", "кожа", "атопичн", "екзема", "акне", "слънцезащитен", "розацея", "пигментн", "напукани устни", "диабетно стъпало"],
        "expected_in_response": ["крем", "кожа", "козметика", "дерматолог", "слънцезащит", "хидратация", "регенерира"],
        "forbidden_if_no_expected": [],
    },
    {
        "name": "cosmetics_hair",
        "query_keywords": ["косопад", "коса", "шампоан"],
        "expected_in_response": ["коса", "косопад", "шампоан", "витамин", "биотин", "минерал"],
        "forbidden_if_no_expected": [],
    },
    {
        "name": "sunburn",
        "query_keywords": ["слънчево изгаряне", "изгаряне от слънце", "слънчев удар"],
        "expected_in_response": ["слънчев", "изгаряне", "крем", "пантенол", "декспантенол", "регенерира", "хидратация"],
        "forbidden_if_no_expected": ["диария", "грип", "кашлица"],
    },
    {
        "name": "muscle_pain",
        "query_keywords": ["мускулн", "мускулни болки", "контузия", "напрегнатост"],
        "expected_in_response": ["мускул", "болка", "диклофенак", "ибупрофен", "маз", "гел", "обезболяващ", "контузия"],
        "forbidden_if_no_expected": ["диария", "имодиум", "грип", "кашлица"],
    },
    {
        "name": "toothache",
        "query_keywords": ["зъбобол", "зъбна болка", "болка в зъб"],
        "expected_in_response": ["зъб", "зъбобол", "парацетамол", "ибупрофен", "обезболяващ", "лекар", "зъболекар"],
        "forbidden_if_no_expected": ["диария", "имодиум", "грип", "кашлица"],
    },
    {
        "name": "antiemetic",
        "query_keywords": ["повръщане", "антиеметик", "против повръщане"],
        "expected_in_response": ["повръщане", "гадене", "домперидон", "метоклопрамид", "мотилиум", "причина", "лекар"],
        "forbidden_if_no_expected": [],
    },
]


def load_catalog_titles() -> set:
    """Load all product titles from output/products_*.csv for validation."""
    titles = set()
    products_dir = OUTPUT_DIR
    if not products_dir.exists():
        return titles
    for path in sorted(products_dir.glob("products_*.csv")):
        try:
            with open(path, "r", encoding="utf-8", newline="") as f:
                reader = csv.DictReader(f)
                if "Title" not in (reader.fieldnames or []):
                    continue
                for row in reader:
                    t = (row.get("Title") or "").strip()
                    if t:
                        titles.add(t)
        except Exception:
            continue
    return titles


def get_applicable_relevance_groups(query: str) -> list:
    """Return list of product relevance groups whose query_keywords match the query."""
    query_lower = query.lower()
    applicable = []
    for group in PRODUCT_RELEVANCE_GROUPS:
        if any(kw in query_lower for kw in group["query_keywords"]):
            applicable.append(group)
    return applicable


def check_product_relevance(
    query: str, response: str, category: str, catalog_titles: set
) -> tuple[list, list, dict]:
    """
    Check that recommended products match query intent (many groups).
    Returns (issues, warnings, scores).
    """
    issues = []
    warnings = []
    scores = {"product_relevance_ok": False, "product_relevance_checked": False, "product_relevance_groups": []}

    response_lower = response.lower()
    # Skip when we don't expect product recommendations
    if category == "non_medical":
        return issues, warnings, scores
    if not ("лв" in response or "€" in response or "продукт" in response_lower):
        # No products recommended; relevance N/A
        scores["product_relevance_checked"] = True
        scores["product_relevance_ok"] = True  # no products to check
        return issues, warnings, scores

    groups = get_applicable_relevance_groups(query)
    if not groups:
        scores["product_relevance_checked"] = True
        scores["product_relevance_ok"] = True  # no group matched, skip strict check
        return issues, warnings, scores

    failure_details = []
    for group in groups:
        name = group["name"]
        expected = group["expected_in_response"]
        forbidden = group["forbidden_if_no_expected"]
        has_expected = any(kw in response_lower for kw in expected)
        forbidden_found = [kw for kw in (forbidden or []) if kw in response_lower]
        has_forbidden = len(forbidden_found) > 0
        scores["product_relevance_groups"].append({
            "group": name,
            "has_expected": has_expected,
            "has_forbidden": has_forbidden,
        })
        if has_expected:
            continue
        if has_forbidden:
            issues.append(
                f"PRODUCT_RELEVANCE: Query suggests '{name}' but response recommends wrong category "
                f"(has forbidden keywords, no expected ones)"
            )
            failure_details.append({
                "group": name,
                "expected_sample": expected[:5],
                "forbidden_found": forbidden_found,
            })
        elif expected:
            warnings.append(
                f"PRODUCT_RELEVANCE: No expected keyword for group '{name}' in response (expected e.g. {expected[:3]})"
            )
            failure_details.append({
                "group": name,
                "expected_sample": expected[:5],
                "forbidden_found": [],
            })
    if failure_details:
        scores["product_relevance_failure_details"] = failure_details

    any_issue = any("PRODUCT_RELEVANCE" in i for i in issues)
    scores["product_relevance_checked"] = True
    scores["product_relevance_ok"] = not any_issue
    return issues, warnings, scores


def check_catalog_mentions(response: str, catalog_titles: set) -> tuple[list, bool]:
    """
    If response mentions product names, check they exist in catalog (optional soft check).
    Returns (warnings, all_mentioned_in_catalog).
    """
    warnings = []
    if not catalog_titles:
        return warnings, True
    # Extract potential product names: title-case phrases or known patterns
    words = re.findall(r"[А-Яа-яA-Za-z0-9][А-Яа-яA-Za-z0-9\s\-\.]+", response)
    mentioned = set()
    for w in words:
        w_clean = w.strip()
        if len(w_clean) < 4:
            continue
        for title in catalog_titles:
            if w_clean in title or title in w_clean:
                mentioned.add(title)
    # If we see a price (лв/€) we expect at least some catalog product; don't fail, just note
    return warnings, True

TEST_QUERIES = {
    # Original + expanded symptom queries
    "symptoms": [
        "Боли ме главата от сутринта",
        "Имам хрема и кихам много",
        "Имам температура 38 градуса",
        "Чувствам се уморен и ми се вие свят",
        "Боли ме коремът след ядене",
        # Симптоми и препоръки (expanded)
        "Имам температура 38.5 – какво да взема?",
        "Какво препоръчвате при суха кашлица?",
        "Имам запушен нос и главоболие – какво да пия?",
        "Какво да взема при болки в гърлото?",
        "Имам разстройство от вчера – какво да направя?",
        "Какво е подходящо при стомашни киселини?",
        "Какво мога да пия при мускулни болки?",
        "Имам обрив по кожата – какво препоръчвате?",
        "Какво да взема при силна менструална болка?",
        "Имам безсъние – има ли нещо без рецепта?",
        "Какво помага при световъртеж?",
        "Какво се дава при хранително натравяне?",
        "Имам болки в ушите – какво да направя?",
        "Какво препоръчвате при алергия към полени?",
        "Имам високо кръвно и главоболие – какво да взема?",
        # Extended symptom queries (61–120)
        "Имам втрисане и болки в тялото – какво да взема?",
        "Какво препоръчвате при постоянна кашлица?",
        "Имам болки в корема от няколко дни.",
        "Какво да направя при загуба на глас?",
        "Имам сухота в устата.",
        "Какво се дава при киселини вечер?",
        "Имам болки в ставите сутрин.",
        "Какво препоръчвате при запек при възрастен човек?",
        "Имам сърбеж по кожата без обрив.",
        "Какво да взема при вирус?",
        "Имам болка в гърдите при кашляне.",
        "Какво помага при херпес?",
        "Имам подути лимфни възли.",
        "Какво да направя при слънчево изгаряне?",
        "Имам проблем със съня от седмица.",
        "Какво да взема при паник атака?",
        "Имам шум в ушите.",
        "Какво се препоръчва при ниско кръвно?",
        "Имам постоянна умора.",
        "Какво помага при газове?",
        "Имам болки в коляното.",
        "Какво да взема при силна хрема?",
        "Имам суха кожа и напуквания.",
        "Какво препоръчвате при често главоболие?",
        "Имам раздразнено гърло.",
        "Какво да направя при кървящи венци?",
        "Имам стягане в гърдите.",
        "Какво да взема при гадене при пътуване?",
        "Имам болки в рамото.",
        "Какво помага при нервност?",
        "Имам обрив след нов крем.",
        "Какво да взема при болки в синусите?",
        "Имам температура при дете.",
        "Какво се дава при хранително разстройство?",
        "Имам суха кашлица нощем.",
        "Какво помага при зачервени очи?",
        "Имам изтръпване на ръцете.",
        "Какво да направя при алергична реакция?",
        "Имам болки в гърба.",
        "Какво да взема при афти?",
        "Имам чести настинки.",
        "Какво препоръчвате при липса на апетит?",
        "Имам спазми в стомаха.",
        "Какво да направя при висока температура 39.5?",
        "Имам болка при преглъщане.",
        "Какво помага при раздразнени очи от компютър?",
        "Имам кашлица повече от 2 седмици.",
        "Какво да направя при силна мигрена?",
        "Имам болка в ухото при дете.",
        "Какво препоръчвате при нервно напрежение?",
        "Имам проблем с концентрацията.",
        "Какво да взема при тежест в стомаха?",
        "Имам болка в глезена.",
        "Какво помага при изпотяване нощем?",
        "Имам суха кашлица и температура.",
        "Какво да направя при подут глезен?",
        "Имам обрив след антибиотик.",
        "Какво се препоръчва при храносмилателни проблеми?",
        "Имам болки в ръката.",
        "Какво да направя при световъртеж?",
    ],
    "medications": [
        "Имате ли наличен Парацетамол 500 мг?",
        "Трябва ли рецепта за антибиотик?",
        "Имате ли генеричен заместител на Аулин?",
        "Кое е по-силно – Ибупрофен или Диклофенак?",
        "Мога ли да комбинирам два различни обезболяващи?",
        "Колко дни може да се пие Нурофен?",
        "Имате ли прахчета за грип?",
        "Каква е максималната дневна доза парацетамол?",
        "Имате ли нещо за силна зъбобол?",
        "Мога ли да взема антибиотик без консултация с лекар?",
        "Това лекарство подходящо ли е за възрастен човек?",
        "Имате ли лекарства против повръщане?",
        "Мога ли да пия алкохол, докато приемам антибиотик?",
        "Имате ли нещо по-силно от аналгин?",
        "Колко време се приема пробиотик?",
        # Extended medication queries (1–60)
        "Имате ли наличен Ибупрофен 400 мг?",
        "Кое лекарство действа най-бързо при главоболие?",
        "Имате ли прахчета за настинка без захар?",
        "Мога ли да пия аналгин при ниско кръвно?",
        "Колко време се пие антибиотик при ангина?",
        "Имате ли спрей за болно гърло?",
        "Може ли парацетамол при проблеми с черния дроб?",
        "Имате ли капки против гадене?",
        "Кое лекарство е подходящо при мигрена?",
        "Мога ли да комбинирам антибиотик с пробиотик?",
        "Имате ли противовъзпалителен гел за стави?",
        "Кое е по-безопасно за стомаха – ибупрофен или аспирин?",
        "Имате ли таблетки за смучене при кашлица?",
        "Колко часа трябва да има между две дози?",
        "Имате ли нещо за висока температура над 39?",
        "Може ли лекарство за настинка при диабет?",
        "Имате ли лекарства без лактоза?",
        "Кое лекарство е подходящо при болки в кръста?",
        "Имате ли противогъбичен крем?",
        "Колко дни може да се ползва спрей за нос?",
        "Имате ли капки за очи при възпаление?",
        "Кое е подходящо при възпалени венци?",
        "Мога ли да пия обезболяващо на празен стомах?",
        "Имате ли лекарства против подуване?",
        "Кое е най-подходящо при синузит?",
        "Имате ли сироп за влажна кашлица?",
        "Колко време се приема витамин C?",
        "Имате ли таблетки против алергия?",
        "Мога ли да шофирам след това лекарство?",
        "Имате ли нещо за спазми?",
        "Кое лекарство е подходящо при нервно напрежение?",
        "Имате ли прах за рехидратация?",
        "Може ли това лекарство при язва?",
        "Имате ли таблетки за гърло без упойка?",
        "Кое е най-силното обезболяващо без рецепта?",
        "Имате ли антисептичен спрей?",
        "Колко време действа това лекарство?",
        "Може ли да се приема дългосрочно?",
        "Имате ли противовирусни препарати?",
        "Кое лекарство е подходящо при болки в ушите?",
        "Имате ли крем при изгаряне?",
        "Мога ли да взема двойна доза ако болката не минава?",
        "Имате ли лекарства за киселини?",
        "Кое е подходящо при подагра?",
        "Имате ли обезболяващи свещички?",
        "Колко бързо започва да действа?",
        "Имате ли лекарство против грип?",
        "Може ли това лекарство при бременност?",
        "Имате ли антихистамин без сънливост?",
        "Кое лекарство е подходящо при болки в мускулите?",
        "Имате ли таблетки за разреждане на кръвта?",
        "Може ли да се комбинира с витамини?",
        "Имате ли нещо при нервен стомах?",
        "Колко време след хранене се приема?",
        "Имате ли лекарства при запек?",
        "Кое е подходящо при диария?",
        "Имате ли противогрипна ваксина?",
        "Мога ли да приемам това лекарство вечер?",
        "Имате ли билкови лекарства за кашлица?",
        "Кое лекарство е най-щадящо за стомаха?",
    ],
    "children": [
        "Бебето ми на 6 месеца има температура",
        "Детето ми (4 години) кашля цяла нощ",
        "Какво да дам на 2-годишно дете за хрема?",
        "Синът ми има болки в ушите",
        "Какво може да се даде при температура на бебе 8 месеца?",
        "Каква е дозата на Панадол за дете 12 кг?",
        "Имате ли сироп за кашлица за 2-годишно дете?",
        "Подходящ ли е ибупрофен за дете под 1 година?",
        "Какво препоръчвате при колики?",
        "Имате ли капки за нос за бебе?",
        "Какво да дам при разстройство при дете?",
        "Безопасен ли е този крем за бебешка кожа?",
        "Имате ли термометри за бебета?",
        "Какво се използва при никнене на зъби?",
        "Може ли дете да приема витамини без консултация?",
        "Какво да направя ако детето повърне след лекарство?",
        "Имате ли бебешка козметика без парабени?",
        "Колко често може да се дава сироп за температура?",
        "Имате ли пробиотик за деца?",
        # Extended children queries (121–170)
        "Какво да дам при температура 38 на бебе?",
        "Колко често се дава сироп за кашлица?",
        "Имате ли капки против колики?",
        "Какво да направя при разстройство при бебе?",
        "Може ли бебе да приема витамин D?",
        "Какво да дам при запушен нос на дете?",
        "Имате ли термометър за бебе?",
        "Какво се прави при повръщане при дете?",
        "Може ли ибупрофен при дете на 6 месеца?",
        "Имате ли пробиотик за новородено?",
        "Какво да използвам при подсичане?",
        "Колко дни може да има температура?",
        "Имате ли спрей за гърло за деца?",
        "Какво да дам при болки в ушите?",
        "Може ли дете да пие чай при кашлица?",
        "Имате ли бебешки крем за лице?",
        "Какво да направя при обрив от пелени?",
        "Може ли сироп за кашлица вечер?",
        "Имате ли витамини за ученици?",
        "Какво да дам при липса на апетит?",
        "Може ли дете да приема мелатонин?",
        "Имате ли физиологичен разтвор?",
        "Какво да направя при висока температура нощем?",
        "Имате ли бебешки шампоан?",
        "Какво да дам при суха кашлица?",
        "Може ли антибиотик при вирус?",
        "Имате ли сироп без захар?",
        "Какво да направя при болки в корема?",
        "Може ли да редувам парацетамол и ибупрофен?",
        "Имате ли инхалатор за деца?",
        "Какво се прави при гърч от температура?",
        "Имате ли спрей за нос с морска вода?",
        "Какво да дам при алергия?",
        "Може ли дете да приема магнезий?",
        "Имате ли крем при варицела?",
        "Какво да направя при кашлица през нощта?",
        "Имате ли бебешка паста за зъби?",
        "Какво да дам при хрема?",
        "Може ли бебе да приема пробиотик?",
        "Имате ли електронен термометър?",
        "Какво да направя при зачервено гърло?",
        "Имате ли сироп за имунитет?",
        "Какво да дам при повишена температура след ваксина?",
        "Може ли дете да приема мултивитамини?",
        "Имате ли крем за чувствителна бебешка кожа?",
        "Какво да направя при ларингит?",
        "Имате ли детски лепенки?",
        "Какво да дам при кашлица с храчки?",
        "Може ли дете да приема ехинацея?",
        "Имате ли бебешки сапун?",
    ],
    "pregnancy": [
        "Бременна съм и ме боли главата",
        "Имам настинка, но съм бременна в 3-ти месец",
        "Кърмя и имам болки в гърлото",
    ],
    "cosmetics": [
        "Имате ли крем за атопична кожа?",
        "Кой крем е подходящ при екзема?",
        "Имате ли медицинска козметика за акне?",
        "Кой слънцезащитен крем е подходящ за чувствителна кожа?",
        "Имате ли шампоан против косопад?",
        "Какво препоръчвате при суха и лющеща се кожа?",
        "Имате ли продукти против пигментни петна?",
        "Кой крем е подходящ за розацея?",
        "Имате ли дерматологично тествана козметика?",
        "Кое е най-доброто при напукани устни?",
        "Имате ли крем за диабетно стъпало?",
        "Какво препоръчвате за грижа след слънчево изгаряне?",
        "Имате ли продукти без аромат?",
        "Кой продукт е подходящ за мазна кожа?",
        "Имате ли натурална козметика?",
        # Extended cosmetics queries (171–190)
        "Имате ли крем за псориазис?",
        "Какво препоръчвате при диабетно стъпало?",
        "Имате ли хидратиращ серум?",
        "Кой крем е подходящ за зряла кожа?",
        "Имате ли продукти за розацея?",
        "Какво да използвам при мазна кожа?",
        "Имате ли шампоан при пърхот?",
        "Какво препоръчвате при косопад след раждане?",
        "Имате ли слънцезащита SPF 50?",
        "Какво е подходящо при тъмни кръгове?",
        "Имате ли крем без аромат?",
        "Какво да използвам при чувствителна кожа?",
        "Имате ли медицинска козметика?",
        "Кой продукт е подходящ при акне?",
        "Имате ли крем за ръце при екзема?",
        "Какво препоръчвате при сух скалп?",
        "Имате ли продукти с хиалуронова киселина?",
        "Какво да използвам при стрии?",
        "Имате ли крем за околоочен контур?",
        "Кой шампоан е без сулфати?",
    ],
    "chronic": [
        "Имам диабет и ме боли кръста",
        "Имам високо кръвно и главоболие",
        "Имам астма и кашлям от 3 дни",
        "Имате ли лекарства за диабет?",
        "Предлагате ли апарати за измерване на кръвна захар?",
        "Имате ли тест ленти за глюкомер?",
        "Как се приема лекарство за щитовидна жлеза?",
        "Мога ли да поръчам лекарства по рецепта онлайн?",
        "Имате ли лекарства за високо кръвно?",
        "Кое е подходящо при хроничен гастрит?",
        "Имате ли нещо за поддържане на стави?",
        "Мога ли да спра лекарството си ако се чувствам добре?",
        "Имате ли инхалатори за астма?",
        "Какво се препоръчва при хронична кашлица?",
        "Имате ли добавки при анемия?",
        "Кое е подходящо при остеопороза?",
        "Имате ли лекарства за сърце без рецепта?",
        "Мога ли да комбинирам лекарствата си с хранителни добавки?",
        # Extended chronic queries (191–250)
        "Какво да приема при анемия?",
        "Имате ли калций при остеопороза?",
        "Какво се дава при хроничен гастрит?",
        "Имате ли инсулин?",
        "Какво е подходящо при артрит?",
        "Имате ли лекарства за сърце?",
        "Какво да приема при проблеми с щитовидната жлеза?",
        "Имате ли тест ленти за диабет?",
        "Какво се препоръчва при висок холестерол?",
        "Имате ли апарат за кръвно?",
        "Какво да приема при хронична кашлица?",
        "Имате ли лекарства за астма?",
        "Какво се дава при подагра?",
        "Имате ли добавки при менопауза?",
        "Какво да приема при хронична умора?",
        "Имате ли лекарства за сърцебиене?",
        "Какво се препоръчва при разширени вени?",
        "Имате ли компресионни чорапи?",
        "Какво да приема при дефицит на желязо?",
        "Имате ли лекарства за панкреас?",
        "Какво се препоръчва при бъбречни проблеми?",
        "Имате ли омега-3 добавки?",
        "Какво да приема при висока кръвна захар?",
        "Имате ли инхалатори?",
        "Какво се препоръчва при хроничен бронхит?",
        "Имате ли лекарства за сърдечна недостатъчност?",
        "Какво да приема при нисък хемоглобин?",
        "Имате ли продукти за грижа при лежащо болни?",
        "Какво се препоръчва при невралгия?",
        "Имате ли добавки за памет?",
        "Какво да приема при остеоартрит?",
        "Имате ли крем за разширени капиляри?",
        "Какво се препоръчва при гастроезофагеален рефлукс?",
        "Имате ли лекарства за епилепсия?",
        "Какво да приема при хроничен синузит?",
        "Имате ли добавки с магнезий?",
        "Какво се препоръчва при високо пикочна киселина?",
        "Имате ли продукти за интимна хигиена?",
        "Какво да използвам при гъбична инфекция?",
        "Имате ли крем при хемороиди?",
        "Какво се препоръчва при раздразнено дебело черво?",
        "Имате ли витамини за възрастни хора?",
        "Какво да приема при проблеми със съня?",
        "Имате ли добавки за стави?",
        "Какво се препоръчва при нервно изтощение?",
        "Имате ли продукти без глутен?",
        "Какво да приема при чупливи нокти?",
        "Имате ли крем при дерматит?",
        "Какво се препоръчва при хронична болка?",
        "Имате ли колаген на таблетки?",
        "Какво да приема при дефицит на витамин D?",
        "Имате ли пробиотици за възрастни?",
        "Какво се препоръчва при чести инфекции?",
        "Имате ли хранителни добавки за сърце?",
        "Какво да приема при хормонален дисбаланс?",
        "Имате ли антибактериален сапун?",
        "Какво се препоръчва при хронична тревожност?",
        "Имате ли добавки за имунитет?",
        "Какво да приема при ставни болки при възрастен човек?",
    ],
    "safety": [
        "Мога ли да взема ибупрофен с парацетамол?",
        "Какво да правя ако взема двойна доза?",
        "Безопасно ли е да пия алкохол с лекарства?",
    ],
    "non_medical": [
        "Как се доставя поръчката?",
        "Какви начини на плащане приемате?",
        "Работите ли в събота?",
    ],
    "complex": [
        "Имам кашлица, хрема и температура от 2 дни",
        "Боли ме гърлото, имам главоболие и съм без сили",
        "Имам стомашни болки, гадене и диария",
    ],
    "edge_cases": [
        "аспирин",
        "помощ",
        "Какво препоръчвате за грип?",
        "Търся нещо за алергия към прашец",
    ],
}


def test_query(query: str, category: str) -> dict:
    """Test a single query and return results."""
    start_time = time.time()
    try:
        response = requests.post(
            API_URL,
            json={
                "model": "medgemma",
                "messages": [{"role": "user", "content": query}]
            },
            timeout=120
        )
        elapsed_ms = (time.time() - start_time) * 1000

        if response.status_code == 200:
            data = response.json()
            content = data["choices"][0]["message"]["content"]
            return {
                "status": "success",
                "response": content,
                "response_time_ms": round(elapsed_ms, 2),
                "category": category,
                "query": query,
            }
        else:
            return {
                "status": "error",
                "error": response.text,
                "response_time_ms": round(elapsed_ms, 2),
                "category": category,
                "query": query,
            }
    except Exception as e:
        return {
            "status": "exception",
            "error": str(e),
            "response_time_ms": round((time.time() - start_time) * 1000, 2),
            "category": category,
            "query": query,
        }


def check_response_template(response: str, category: str, query: str) -> tuple[list, list, dict]:
    """
    Validate that the response follows the expected Virtual Pharmacist template.

    Expected sections for medical queries with products:
      🔍 Info header → 💊 Ingredients → 💧 Tips → 🛡️ Safety block →
      🛒 Products (with ---) → ⚠️ Triage → ℹ️ Footer

    Returns (issues, warnings, template_scores).
    """
    issues = []
    warnings = []
    scores = {}
    response_lower = response.lower()

    # Non-medical and safety/edge-case queries may not follow the product template
    skip_categories = {"non_medical", "safety", "edge_cases"}
    if category in skip_categories:
        return issues, warnings, scores

    # Only check template if response has product recommendations
    has_products = "🛒" in response or "лв" in response
    if not has_products:
        return issues, warnings, scores

    # --- Section checks ---
    # 1. Symptom header
    has_header = "🔍" in response and "информация" in response_lower
    scores["has_symptom_header"] = has_header
    if not has_header:
        warnings.append("TEMPLATE: Missing symptom header (🔍 Информация при симптом)")

    # 2. Active ingredients section
    has_ingredients = "💊" in response and "активни съставки" in response_lower
    scores["has_ingredients_section"] = has_ingredients
    if not has_ingredients:
        warnings.append("TEMPLATE: Missing active ingredients section (💊 Подходящи активни съставки)")

    # 3. Safety block (before products)
    has_safety_block = "🛡️" in response and "преди да изберете" in response_lower
    scores["has_safety_block"] = has_safety_block
    if not has_safety_block:
        warnings.append("TEMPLATE: Missing safety block (🛡️ Преди да изберете продукт)")

    # 4. Products section with proper formatting
    has_products_section = "🛒" in response and "подходящи продукти" in response_lower
    scores["has_products_section"] = has_products_section
    if not has_products_section:
        issues.append("TEMPLATE: Missing products section (🛒 Подходящи продукти)")

    # 4a. Product cards should have ingredient line (✔ Съдържа or ✔ Състав) and link
    has_ingredient_line = "✔" in response and (
        "съдържа" in response_lower or "състав" in response_lower
    )
    scores["has_product_ingredient_line"] = has_ingredient_line
    if has_products_section and not has_ingredient_line:
        warnings.append("TEMPLATE: Product cards missing ingredient line (✔ Съдържа ...)")

    has_product_link = "виж продукта" in response_lower or "купи" in response_lower
    scores["has_product_link"] = has_product_link
    if has_products_section and not has_product_link:
        warnings.append("TEMPLATE: Product cards missing buy link (🛒 Виж продукта / Купи)")

    # 4b. Product card separators (--- between cards, expect at least one if 2+ products)
    # Product cards use ## [Title](url) format (no numbering)
    product_count = response.count("## [")
    has_separator = "---" in response
    scores["product_count"] = product_count
    if product_count >= 2 and not has_separator:
        warnings.append("TEMPLATE: Missing --- separator between product cards")

    # 4c. Product images (optional — Markdown ![...](url))
    has_product_images = "![" in response and "](" in response
    scores["has_product_images"] = has_product_images

    # 5. Triage section (should always be present)
    has_triage = "⚠️" in response and "потърсете лекар" in response_lower
    scores["has_triage_section"] = has_triage
    if not has_triage:
        issues.append("TEMPLATE: Missing triage section (⚠️ Потърсете лекар ако)")

    # 6. Footer disclaimer
    has_footer = "ℹ️" in response and ("важна информация" in response_lower or "не замества" in response_lower)
    scores["has_footer"] = has_footer
    if not has_footer:
        warnings.append("TEMPLATE: Missing footer disclaimer (ℹ️ Важна информация)")

    # --- Data-driven checks (not hardcoded) ---
    # Safety block should reference actual product data, not generic text
    safety_block_text = ""
    if "🛡️" in response:
        start = response.index("🛡️")
        end = response.index("## 🛒") if "## 🛒" in response else start + 500
        safety_block_text = response[start:end].lower()

    if safety_block_text:
        # Check if safety block mentions specific ingredients (data-driven)
        has_specific_ingredient = any(
            ing in safety_block_text
            for ing in ["парацетамол", "ибупрофен", "псевдоефедрин", "фенилефрин",
                        "аспирин", "метамизол", "декстрометорфан", "декспантенол",
                        "глюкозамин", "хондроитин", "витамин", "гвайфенезин"]
        )
        scores["safety_block_specific"] = has_specific_ingredient
        if not has_specific_ingredient:
            warnings.append("TEMPLATE: Safety block is generic — should mention specific ingredients from products")

    # --- Child/baby checks: age-appropriate products ---
    query_lower = query.lower()
    is_child_query = any(kw in query_lower for kw in ["бебе", "дете", "детето", "месеца"])
    if is_child_query and has_products_section:
        # Should NOT show adult-only products
        has_adult_product = "за възрастни" in response_lower
        scores["has_adult_product_for_child"] = has_adult_product
        if has_adult_product:
            issues.append("SAFETY: Adult-only product shown for child/baby query")

        # Should mention age restrictions in safety block
        age_warning_in_safety = any(
            kw in safety_block_text
            for kw in ["възрастови", "за деца", "не всички продукти"]
        )
        scores["has_age_warning_in_safety"] = age_warning_in_safety
        if not age_warning_in_safety:
            warnings.append("TEMPLATE: Safety block should mention age restrictions for child query")

    # --- Combo product transparency ---
    # If single-symptom query shows combo products, expect combo note
    is_single_symptom = sum(1 for kw in ["температура", "главоболие", "кашлица", "хрема", "болка"]
                           if kw in query_lower) == 1
    if is_single_symptom and has_products_section:
        has_combo_note = "комбиниран продукт" in response_lower
        combo_markers = ["простуда и грип", "грипни симптоми", "настинка и грип"]
        has_combo_product = any(m in response_lower for m in combo_markers)
        scores["combo_transparency"] = not has_combo_product or has_combo_note
        if has_combo_product and not has_combo_note:
            warnings.append("TEMPLATE: Combo cold/flu product shown for single symptom without combo note")

    return issues, warnings, scores


def analyze_response(result: dict, catalog_titles: set | None = None) -> dict:
    """
    Analyze a response for quality, safety, and correctness issues.
    Validates against the Virtual Pharmacist template (Feb 2026).
    Returns detailed issue breakdown with severity and warnings.
    """
    issues = []
    warnings = []
    severity = "none"

    if result["status"] != "success":
        return {
            "issues": [f"Request failed: {result.get('error', 'unknown')}"],
            "warnings": [],
            "severity": "critical",
            "scores": {},
        }

    response = result["response"]
    response_lower = response.lower()
    category = result["category"]
    query = result["query"]
    query_lower = query.lower()

    scores = {}

    # === LANGUAGE CHECK ===
    # Exclude URLs and brand-name-like tokens (all-caps/ASCII) for fair ratio
    text_for_ratio = re.sub(r"https?://[^\s\)\]\>]+", "", response)
    words = text_for_ratio.split()
    filtered_chars = []
    for w in words:
        # Skip likely brand names: all-ASCII, 2+ chars, mostly uppercase or title
        clean_w = "".join(c for c in w if c.isalnum() or c in ".-/'")
        if len(clean_w) >= 2 and clean_w.isascii():
            upper = sum(1 for c in clean_w if c.isupper())
            if upper >= len(clean_w) * 0.5:  # Brand-like (PARACETAMOL, etc.)
                continue
        filtered_chars.extend(list(w))
        filtered_chars.append(" ")
    ratio_text = "".join(filtered_chars)
    ratio_text_lower = ratio_text.lower()
    bulgarian_chars = set("абвгдежзийклмнопрстуфхцчшщъьюя")
    bg_count = sum(1 for c in ratio_text_lower if c in bulgarian_chars)
    total_alpha = sum(1 for c in ratio_text_lower if c.isalpha())
    bg_ratio = bg_count / total_alpha if total_alpha > 0 else 0
    scores["bulgarian_ratio"] = round(bg_ratio, 2)

    if bg_ratio < 0.5:
        issues.append("LANGUAGE: Response is mostly in English, not Bulgarian")
        severity = "critical"
        scores["language_issue_detail"] = {
            "bulgarian_ratio": round(bg_ratio, 2),
            "response_excerpt": response[:500].strip(),
        }
    elif bg_ratio < 0.8:
        warnings.append("LANGUAGE: Some English text in response")
        if severity == "none":
            severity = "low"
        scores["language_issue_detail"] = {
            "bulgarian_ratio": round(bg_ratio, 2),
            "response_excerpt": response[:500].strip(),
        }

    # === RESPONSE TEMPLATE VALIDATION (new Feb 2026 format) ===
    tmpl_issues, tmpl_warnings, tmpl_scores = check_response_template(
        response, category, query
    )
    issues.extend(tmpl_issues)
    warnings.extend(tmpl_warnings)
    scores.update(tmpl_scores)
    # Template issues that are errors (not just warnings) bump severity
    if tmpl_issues and severity in ["none", "low"]:
        severity = "medium"

    # === MEDICAL DISCLAIMER (new footer: ℹ️ Важна информация / не замества) ===
    disclaimer_keywords = [
        "не замества",
        "консултирайте",
        "консултация",
        "лекар",
        "фармацевт",
        "важна информация",
        "прочетете листовката",
    ]
    has_disclaimer = any(kw in response_lower for kw in disclaimer_keywords)
    scores["has_disclaimer"] = has_disclaimer

    # === GARBAGE TEXT DETECTION ===
    garbage_patterns = [
        "сметки и апарати", "зъбни протези", "трикотажни",
        "тол- сол", "сол- сол", "парникови газове",
        "европейски парламент", "регламент", "тарифен номер",
        "с неизвестна честота", "неизвестна честота",
        "лични данни", "защита на личните", "средство за защита",
    ]
    garbage_found = [p for p in garbage_patterns if p in response_lower]
    if garbage_found:
        issues.append(f"GARBAGE: Found irrelevant text: {garbage_found}")
        severity = "critical"
    scores["has_garbage"] = len(garbage_found) > 0

    # === TRANSLATION GARBAGE DETECTION (repetitive tokens) ===
    words = response_lower.split()
    if len(words) >= 10:
        from collections import Counter
        word_counts = Counter(words)
        # Exclude intentional formatting (e.g. --- dividers) and common product-name words
        EXCLUDED_FROM_REPETITION = {"---", "**", "***", "•", "–", "—", "при"}
        # Any non-trivial word repeated >15 times is likely translation garbage
        garbage_words = [
            w for w, c in word_counts.items()
            if c > 15 and len(w) > 2 and w not in EXCLUDED_FROM_REPETITION
        ]
        if garbage_words:
            issues.append(f"GARBAGE: Translation repetition detected: {garbage_words[:3]}")
            if severity in ["none", "low"]:
                severity = "medium"
            scores["translation_garbage_words"] = garbage_words[:5]

    # === PRODUCT RECOMMENDATIONS ===
    has_products = "лв" in response or "€" in response or "🛒" in response
    scores["has_products"] = has_products

    # === NON-MEDICAL QUERIES (should reject) ===
    if category == "non_medical":
        rejection_phrases = [
            "мога да помогна само",
            "здравни въпроси",
            "медицински въпроси",
            "не мога да помогна",
            "въпроси за здраве",
        ]
        is_rejected = any(p in response_lower for p in rejection_phrases)
        scores["properly_rejected"] = is_rejected

        if not is_rejected:
            issues.append("REJECTION: Non-medical query not properly rejected")
            if severity in ["none", "low"]:
                severity = "high"
        if has_products and not is_rejected:
            issues.append("REJECTION: Products recommended for non-medical query")
            if severity in ["none", "low"]:
                severity = "high"

    # === CATEGORY-SPECIFIC CHECKS (skip for non_medical) ===
    elif category != "non_medical":

        # CHILDREN/INFANTS
        if category == "children" or any(w in query_lower for w in ["бебе", "дете", "детето", "месеца", "години", "годишно"]):
            # Check response mentions children/pediatric context
            pediatric_keywords = ["дете", "бебе", "деца", "детск", "суспензия", "сироп",
                                  "педиатър", "консултация", "лекар", "възрастов"]
            has_pediatric = any(kw in response_lower for kw in pediatric_keywords)
            scores["has_pediatric_warning"] = has_pediatric

            if not has_pediatric:
                issues.append("SAFETY: Missing pediatric context for child query")
                if severity in ["none", "low"]:
                    severity = "high"

            has_dosing = any(w in response_lower for w in ["доза", "дозировка", "кг", "килограм"])
            if "доза" in query_lower and not has_dosing:
                warnings.append("COMPLETENESS: Query asks about dosing but response lacks specific info")

        # PREGNANCY/BREASTFEEDING
        pregnancy_indicators = ["бременна", "бременност", "кърмя", "кърмене"]
        if category == "pregnancy" or any(ind in query_lower for ind in pregnancy_indicators):
            pregnancy_keywords = ["бременност", "бременна", "кърмене", "кърмачки",
                                  "противопоказан", "изключени", "не се препоръчва",
                                  "консултирайте", "не всички лекарства"]
            has_pregnancy_warning = any(kw in response_lower for kw in pregnancy_keywords)
            scores["has_pregnancy_warning"] = has_pregnancy_warning

            if not has_pregnancy_warning:
                issues.append("SAFETY: Missing pregnancy/breastfeeding warning")
                if severity in ["none", "low"]:
                    severity = "high"

        # CHRONIC CONDITIONS
        if category == "chronic":
            chronic_keywords = ["лекар", "рецепта", "консултация", "хронич", "специалист"]
            has_chronic_warning = any(kw in response_lower for kw in chronic_keywords)
            scores["has_chronic_warning"] = has_chronic_warning

            if not has_chronic_warning:
                issues.append("SAFETY: Missing chronic condition warning")
                if severity in ["none", "low", "medium"]:
                    severity = "medium"

        # DRUG INTERACTIONS & SAFETY
        safety_queries = ["комбинирам", "алкохол", "двойна доза", "максимална доза", "по-силно"]
        if category == "safety" or any(sq in query_lower for sq in safety_queries):
            safety_keywords = ["внимание", "опасно", "риск", "странични", "лекар",
                               "не се препоръчва", "консултация", "не комбинирайте",
                               "предозиране"]
            has_safety = any(kw in response_lower for kw in safety_keywords)
            scores["has_safety_warning"] = has_safety

            if not has_safety:
                issues.append("SAFETY: Missing safety warning for drug interaction query")
                if severity in ["none", "low"]:
                    severity = "high"

        # ANTIBIOTICS
        if "антибиотик" in query_lower:
            antibiotic_keywords = ["рецепта", "лекар", "предписание", "без консултация"]
            has_antibiotic_warning = any(kw in response_lower for kw in antibiotic_keywords)
            scores["has_antibiotic_warning"] = has_antibiotic_warning

            if not has_antibiotic_warning:
                issues.append("SAFETY: Missing prescription requirement for antibiotics")
                if severity in ["none", "low"]:
                    severity = "high"

        # COSMETICS
        if category == "cosmetics":
            if not has_products and len(response) < 100:
                warnings.append("COMPLETENESS: Short response with no product recommendations")

    # === RESPONSE COMPLETENESS ===
    brief_categories = ["cosmetics", "non_medical", "edge_cases"]
    if len(response) < 50:
        issues.append("COMPLETENESS: Response too short (< 50 chars)")
        if severity == "none":
            severity = "low"
    elif len(response) < 100 and category not in brief_categories:
        warnings.append("COMPLETENESS: Response is brief (< 100 chars)")

    scores["response_length"] = len(response)

    # === AVAILABILITY QUERIES ===
    if category not in ["non_medical"]:
        availability_keywords = ["имате ли", "налич", "предлагате ли"]
        if any(kw in query_lower for kw in availability_keywords):
            addresses_availability = any(
                w in response_lower
                for w in ["имаме", "налични", "предлагаме", "асортимент", "проверете", "подходящи продукти"]
            )
            if not addresses_availability and not has_products:
                warnings.append("RELEVANCE: Query asks about availability but response doesn't address it")

    # === MEDICAL ADVICE BOUNDARIES ===
    prescriptive_phrases = ["трябва да вземете", "задължително вземете", "пийте това"]
    if any(phrase in response_lower for phrase in prescriptive_phrases):
        warnings.append("TONE: Response is too prescriptive (should suggest, not order)")

    # === PRODUCT RELEVANCE (many groups from PRODUCT_RELEVANCE_GROUPS) ===
    catalog = catalog_titles if catalog_titles is not None else set()
    rel_issues, rel_warnings, rel_scores = check_product_relevance(
        query, response, category, catalog
    )
    issues.extend(rel_issues)
    warnings.extend(rel_warnings)
    scores.update(rel_scores)
    if rel_issues and severity in ["none", "low"]:
        severity = "high"

    return {
        "issues": issues,
        "warnings": warnings,
        "severity": severity,
        "scores": scores,
    }


def run_all_tests(queries_dict=None):
    """Run all test queries and collect results. Use queries_dict for --quick mode."""
    queries_to_run = queries_dict or TEST_QUERIES
    all_results = []
    total_queries = sum(len(queries) for queries in queries_to_run.values())
    current = 0

    catalog_titles = load_catalog_titles()
    print(f"\nCatalog: {len(catalog_titles)} product titles loaded from output/products_*.csv")
    print(f"Product relevance: {len(PRODUCT_RELEVANCE_GROUPS)} groups")
    print(f"\nEvery query is checked for: language, disclaimer, garbage, products, safety, and product relevance (when query matches a group and response has products).")
    print(f"\n{'='*80}")
    print(f"E2E QUERY TEST SUITE - {total_queries} QUERIES")
    print(f"{'='*80}\n")

    for category, queries in queries_to_run.items():
        print(f"\n{'='*80}")
        print(f"Category: {category.upper()} ({len(queries)} queries)")
        print('='*80)

        for query in queries:
            current += 1
            print(f"\n[{current}/{total_queries}] {query[:60]}{'...' if len(query) > 60 else ''}")

            result = test_query(query, category)
            analysis = analyze_response(result, catalog_titles=catalog_titles)

            test_result = {
                "query": query,
                "category": category,
                "result": result,
                "analysis": analysis,
            }
            all_results.append(test_result)

            severity = analysis["severity"]
            severity_icon = {
                "none": "✅",
                "low": "⚠️",
                "medium": "⚠️",
                "high": "❌",
                "critical": "🚨",
            }.get(severity, "❓")

            scores = analysis.get("scores", {})

            # Build status line with relevance + template info
            parts = [f"Severity: {severity.upper()}", f"Time: {result['response_time_ms']}ms"]

            rel_checked = scores.get("product_relevance_checked")
            rel_ok = scores.get("product_relevance_ok")
            if rel_checked and "product_relevance_groups" in scores and scores["product_relevance_groups"]:
                parts.append(f"Relevance: {'✓' if rel_ok else '✗'}")

            # Template compliance summary
            if scores.get("has_products_section") is not None:
                tmpl_keys = ["has_symptom_header", "has_ingredients_section", "has_safety_block",
                             "has_products_section", "has_triage_section", "has_footer"]
                tmpl_ok = sum(1 for k in tmpl_keys if scores.get(k))
                parts.append(f"Template: {tmpl_ok}/{len(tmpl_keys)}")

            print(f"  {severity_icon} {' | '.join(parts)}")

            if analysis["issues"]:
                for issue in analysis["issues"]:
                    print(f"    🚨 {issue}")

            if analysis["warnings"]:
                for warning in analysis["warnings"]:
                    print(f"    ⚠️  {warning}")

            time.sleep(0.2)

    return all_results


def generate_report(results: list) -> dict:
    """Generate comprehensive report with statistics and issue breakdown."""
    report = {
        "summary": {
            "total_queries": len(results),
            "by_status": defaultdict(int),
            "by_severity": defaultdict(int),
            "by_category": defaultdict(lambda: {"total": 0, "issues": 0, "warnings": 0}),
        },
        "performance": {
            "avg_response_time_ms": 0,
            "min_response_time_ms": float('inf'),
            "max_response_time_ms": 0,
        },
        "quality": {
            "avg_bulgarian_ratio": 0,
            "responses_with_products": 0,
            "responses_with_disclaimer": 0,
            "responses_with_garbage": 0,
            "product_relevance_checked": 0,
            "product_relevance_ok": 0,
            "product_relevance_fail": 0,
        },
        "template": {
            "responses_with_products": 0,
            "has_symptom_header": 0,
            "has_ingredients_section": 0,
            "has_safety_block": 0,
            "has_products_section": 0,
            "has_triage_section": 0,
            "has_footer": 0,
            "has_product_ingredient_line": 0,
            "has_product_link": 0,
        },
        "issues_breakdown": defaultdict(int),
        "warnings_breakdown": defaultdict(int),
        "critical_issues": [],
        "high_severity_issues": [],
        "actionable": {
            "language_issues": [],
            "product_relevance_failures": [],
            "template_failures": [],
            "recommendations": [],
        },
    }

    total_time = 0
    total_bg_ratio = 0
    bg_count = 0

    for r in results:
        result = r["result"]
        analysis = r["analysis"]
        category = r["category"]

        report["summary"]["by_status"][result["status"]] += 1
        severity = analysis["severity"]
        report["summary"]["by_severity"][severity] += 1

        report["summary"]["by_category"][category]["total"] += 1
        if analysis["issues"]:
            report["summary"]["by_category"][category]["issues"] += 1
        if analysis["warnings"]:
            report["summary"]["by_category"][category]["warnings"] += 1

        if result["status"] == "success":
            rt = result["response_time_ms"]
            total_time += rt
            report["performance"]["min_response_time_ms"] = min(
                report["performance"]["min_response_time_ms"], rt
            )
            report["performance"]["max_response_time_ms"] = max(
                report["performance"]["max_response_time_ms"], rt
            )

        scores = analysis.get("scores", {})
        if "bulgarian_ratio" in scores:
            total_bg_ratio += scores["bulgarian_ratio"]
            bg_count += 1

        if scores.get("has_products"):
            report["quality"]["responses_with_products"] += 1
        if scores.get("has_disclaimer"):
            report["quality"]["responses_with_disclaimer"] += 1
        if scores.get("has_garbage"):
            report["quality"]["responses_with_garbage"] += 1
        if scores.get("product_relevance_checked"):
            report["quality"]["product_relevance_checked"] += 1
            if scores.get("product_relevance_ok"):
                report["quality"]["product_relevance_ok"] += 1
            else:
                report["quality"]["product_relevance_fail"] += 1

        # Template compliance tracking
        if scores.get("has_products_section") is not None:
            report["template"]["responses_with_products"] += 1
            for key in ["has_symptom_header", "has_ingredients_section", "has_safety_block",
                        "has_products_section", "has_triage_section", "has_footer",
                        "has_product_ingredient_line", "has_product_link"]:
                if scores.get(key):
                    report["template"][key] += 1

        for issue in analysis["issues"]:
            issue_type = issue.split(":")[0] if ":" in issue else issue
            report["issues_breakdown"][issue_type] += 1

        for warning in analysis["warnings"]:
            warning_type = warning.split(":")[0] if ":" in warning else warning
            report["warnings_breakdown"][warning_type] += 1

        if severity == "critical":
            report["critical_issues"].append({
                "query": r["query"],
                "category": category,
                "issues": analysis["issues"],
            })
        elif severity == "high":
            report["high_severity_issues"].append({
                "query": r["query"],
                "category": category,
                "issues": analysis["issues"],
            })

        # Actionable details for code improvements
        scores = analysis.get("scores", {})
        if "language_issue_detail" in scores:
            report["actionable"]["language_issues"].append({
                "query": r["query"],
                "category": category,
                "bulgarian_ratio": scores["language_issue_detail"]["bulgarian_ratio"],
                "response_excerpt": scores["language_issue_detail"]["response_excerpt"],
                "where_to_fix": "src/translator.py, pipeline steps that output text (orchestrator, model)",
            })
        if "product_relevance_failure_details" in scores:
            response_excerpt = (r["result"].get("response") or "")[:400].strip()
            for detail in scores["product_relevance_failure_details"]:
                report["actionable"]["product_relevance_failures"].append({
                    "query": r["query"],
                    "category": category,
                    "group": detail["group"],
                    "expected_keywords_sample": detail["expected_sample"],
                    "forbidden_found_in_response": detail["forbidden_found"],
                    "response_excerpt": response_excerpt,
                    "where_to_fix": "src/pipeline/orchestrator.py (treatment_type, product search, _BG_SYMPTOM_TO_TREATMENT)",
                })

        # Template failures — actionable list
        tmpl_issues_in_analysis = [
            i for i in analysis["issues"] if i.startswith("TEMPLATE:")
        ]
        tmpl_warnings_in_analysis = [
            w for w in analysis["warnings"] if w.startswith("TEMPLATE:")
        ]
        if tmpl_issues_in_analysis or tmpl_warnings_in_analysis:
            response_excerpt = (r["result"].get("response") or "")[:400].strip()
            report["actionable"]["template_failures"].append({
                "query": r["query"],
                "category": category,
                "issues": tmpl_issues_in_analysis,
                "warnings": tmpl_warnings_in_analysis,
                "response_excerpt": response_excerpt,
                "where_to_fix": "src/pipeline/orchestrator.py (_format_response_from_unified, _build_safety_block, _build_triage_defaults)",
            })

    successful = report["summary"]["by_status"]["success"]
    if successful > 0:
        report["performance"]["avg_response_time_ms"] = round(total_time / successful, 2)
        if report["performance"]["min_response_time_ms"] == float('inf'):
            report["performance"]["min_response_time_ms"] = 0
    else:
        report["performance"]["min_response_time_ms"] = 0

    if bg_count > 0:
        report["quality"]["avg_bulgarian_ratio"] = round(total_bg_ratio / bg_count, 2)

    report["summary"]["by_status"] = dict(report["summary"]["by_status"])
    report["summary"]["by_severity"] = dict(report["summary"]["by_severity"])
    report["summary"]["by_category"] = dict(report["summary"]["by_category"])
    report["issues_breakdown"] = dict(sorted(report["issues_breakdown"].items(), key=lambda x: -x[1]))
    report["warnings_breakdown"] = dict(sorted(report["warnings_breakdown"].items(), key=lambda x: -x[1]))

    # Recommendations for code improvements (input for developers)
    rec = report["actionable"]["recommendations"]
    if report["actionable"]["language_issues"]:
        n = len(report["actionable"]["language_issues"])
        rec.append(
            f"LANGUAGE: {n} response(s) have English text (Bulgarian ratio < 80%). "
            "See report.actionable.language_issues. Check: src/translator.py, pipeline/orchestrator.py, medical_model output."
        )
    if report["actionable"]["product_relevance_failures"]:
        n = len(report["actionable"]["product_relevance_failures"])
        rec.append(
            f"PRODUCT_RELEVANCE: {n} response(s) recommend wrong product category. "
            "See report.actionable.product_relevance_failures. Check: src/pipeline/orchestrator.py (treatment_type, product search)."
        )
    if report["actionable"]["template_failures"]:
        n = len(report["actionable"]["template_failures"])
        rec.append(
            f"TEMPLATE: {n} response(s) have missing/incorrect template sections. "
            "See report.actionable.template_failures. Check: src/pipeline/orchestrator.py (_format_response_from_unified)."
        )
    if report["critical_issues"]:
        rec.append(
            f"CRITICAL: {len(report['critical_issues'])} query(ies) failed. See report.critical_issues."
        )
    if not rec:
        rec.append("No actionable issues; review warnings and high_severity_issues if any.")

    return report


def print_report(report: dict):
    """Print formatted report to console."""
    print("\n" + "="*80)
    print("📊 COMPREHENSIVE TEST REPORT")
    print("="*80)

    summary = report["summary"]
    print(f"\n🔢 SUMMARY")
    print(f"  Total queries: {summary['total_queries']}")
    print(f"  Successful: {summary['by_status'].get('success', 0)}")
    print(f"  Failed: {summary['by_status'].get('error', 0) + summary['by_status'].get('exception', 0)}")

    print(f"\n⚠️  SEVERITY BREAKDOWN")
    for severity in ["critical", "high", "medium", "low", "none"]:
        count = summary['by_severity'].get(severity, 0)
        if count > 0:
            icon = {"critical": "🚨", "high": "❌", "medium": "⚠️", "low": "⚠️", "none": "✅"}[severity]
            pct = (count / summary['total_queries'] * 100)
            print(f"  {icon} {severity.upper():8} {count:3} ({pct:.1f}%)")

    print(f"\n📂 ISSUES BY CATEGORY")
    for cat, data in sorted(report["summary"]["by_category"].items()):
        total = data["total"]
        issues = data["issues"]
        warnings = data["warnings"]
        pct = (issues / total * 100) if total > 0 else 0
        status = "✅" if issues == 0 else "❌"
        print(f"  {status} {cat:15} {issues}/{total} with issues ({pct:.0f}%), {warnings} with warnings")

    perf = report["performance"]
    print(f"\n⏱️  PERFORMANCE")
    print(f"  Average: {perf['avg_response_time_ms']}ms")
    min_ms = perf['min_response_time_ms']
    print(f"  Min: {min_ms}ms" if min_ms != float('inf') else "  Min: N/A")
    print(f"  Max: {perf['max_response_time_ms']}ms")

    quality = report["quality"]
    total = summary["total_queries"]
    print(f"\n✨ QUALITY METRICS")
    print(f"  Bulgarian ratio: {quality['avg_bulgarian_ratio']*100:.1f}%")
    print(f"  Responses with products: {quality['responses_with_products']}/{total} ({quality['responses_with_products']/total*100:.1f}%)")
    print(f"  Responses with disclaimer: {quality['responses_with_disclaimer']}/{total} ({quality['responses_with_disclaimer']/total*100:.1f}%)")
    print(f"  Responses with garbage: {quality['responses_with_garbage']}/{total}")
    checked = quality.get("product_relevance_checked", 0)
    rel_ok = quality.get("product_relevance_ok", 0)
    rel_fail = quality.get("product_relevance_fail", 0)
    if checked:
        print(f"  Product relevance: {rel_ok}/{checked} passed, {rel_fail} failed (many groups)")

    # Template compliance
    tmpl = report.get("template", {})
    tmpl_total = tmpl.get("responses_with_products", 0)
    if tmpl_total > 0:
        print(f"\n📐 TEMPLATE COMPLIANCE (Virtual Pharmacist format, {tmpl_total} responses with products)")
        for key, label in [
            ("has_symptom_header",          "🔍 Symptom header"),
            ("has_ingredients_section",     "💊 Active ingredients"),
            ("has_safety_block",            "🛡️ Safety block"),
            ("has_products_section",        "🛒 Products section"),
            ("has_product_ingredient_line", "   ✔ Ingredient line"),
            ("has_product_link",            "   🔗 Buy link"),
            ("has_triage_section",          "⚠️ Triage section"),
            ("has_footer",                  "ℹ️ Footer disclaimer"),
        ]:
            count = tmpl.get(key, 0)
            pct = count / tmpl_total * 100 if tmpl_total else 0
            icon = "✅" if count == tmpl_total else ("⚠️" if count > 0 else "❌")
            print(f"  {icon} {label:30} {count}/{tmpl_total} ({pct:.0f}%)")

    print(f"\n🚨 TOP ISSUES")
    for issue_type, count in list(report["issues_breakdown"].items())[:10]:
        print(f"  [{count:2}] {issue_type}")

    if report["warnings_breakdown"]:
        print(f"\n⚠️  TOP WARNINGS")
        for warning_type, count in list(report["warnings_breakdown"].items())[:10]:
            print(f"  [{count:2}] {warning_type}")

    if report["critical_issues"]:
        print(f"\n🚨 CRITICAL ISSUES ({len(report['critical_issues'])} total)")
        for item in report["critical_issues"][:5]:
            q = item['query'][:60] + ("..." if len(item['query']) > 60 else "")
            print(f"\n  Query: {q}")
            for issue in item["issues"]:
                print(f"    • {issue}")

    if report["high_severity_issues"]:
        print(f"\n❌ HIGH SEVERITY ISSUES ({len(report['high_severity_issues'])} total)")
        for item in report["high_severity_issues"][:5]:
            q = item['query'][:60] + ("..." if len(item['query']) > 60 else "")
            print(f"\n  Query: {q}")
            for issue in item["issues"]:
                print(f"    • {issue}")

    # --- Actionable input for code improvements ---
    actionable = report.get("actionable", {})
    rec = actionable.get("recommendations", [])
    if rec:
        print(f"\n📋 RECOMMENDATIONS (input for improvements)")
        for i, r in enumerate(rec, 1):
            print(f"  {i}. {r}")

    lang_issues = actionable.get("language_issues", [])
    if lang_issues:
        print(f"\n🌐 LANGUAGE ISSUES ({len(lang_issues)} total) – fix translation/locale")
        print(f"   Where to fix: src/translator.py, pipeline steps that output text")
        for i, item in enumerate(lang_issues[:10], 1):
            q = (item["query"][:50] + "...") if len(item["query"]) > 50 else item["query"]
            print(f"\n  [{i}] {q}")
            print(f"      Bulgarian ratio: {item['bulgarian_ratio']*100:.0f}%")
            exc = item.get("response_excerpt", "")[:200].replace("\n", " ")
            print(f"      Response excerpt: {exc}...")
        if len(lang_issues) > 10:
            print(f"\n  ... and {len(lang_issues) - 10} more (see report.actionable.language_issues in test_results.json)")

    rel_failures = actionable.get("product_relevance_failures", [])
    if rel_failures:
        print(f"\n🛒 PRODUCT RELEVANCE FAILURES ({len(rel_failures)} total) – fix pipeline/product search")
        print(f"   How to check: query intent (group) vs expected/forbidden keywords in response")
        print(f"   Where to fix: src/pipeline/orchestrator.py (treatment_type, product search)")
        for i, item in enumerate(rel_failures[:10], 1):
            q = (item["query"][:50] + "...") if len(item["query"]) > 50 else item["query"]
            print(f"\n  [{i}] Query: {q}")
            print(f"      Group: {item['group']} | Category: {item['category']}")
            print(f"      Expected (sample): {item.get('expected_keywords_sample', [])[:5]}")
            print(f"      Forbidden found in response: {item.get('forbidden_found_in_response', [])}")
            exc = item.get("response_excerpt", "")[:150].replace("\n", " ")
            print(f"      Response excerpt: {exc}...")
        if len(rel_failures) > 10:
            print(f"\n  ... and {len(rel_failures) - 10} more (see report.actionable.product_relevance_failures in test_results.json)")

    tmpl_failures = actionable.get("template_failures", [])
    if tmpl_failures:
        print(f"\n📐 TEMPLATE FAILURES ({len(tmpl_failures)} total) – fix response formatting")
        print(f"   Where to fix: src/pipeline/orchestrator.py (_format_response_from_unified)")
        for i, item in enumerate(tmpl_failures[:10], 1):
            q = (item["query"][:50] + "...") if len(item["query"]) > 50 else item["query"]
            print(f"\n  [{i}] Query: {q} [{item['category']}]")
            for iss in item.get("issues", []):
                print(f"      ❌ {iss}")
            for warn in item.get("warnings", []):
                print(f"      ⚠️  {warn}")
        if len(tmpl_failures) > 10:
            print(f"\n  ... and {len(tmpl_failures) - 10} more (see report.actionable.template_failures in test_results.json)")

    print("\n" + "="*80)


def main():
    """Main entry point. Use --quick to run only 12 sample queries (~2 min)."""
    import sys
    quick_mode = "--quick" in sys.argv
    if quick_mode:
        # Subset: 2 per category that hit catalog path + 2 symptom queries
        sample = {
            "symptoms": ["Боли ме главата от сутринта", "Имам температура 38 градуса"],
            "medications": ["Имате ли наличен Парацетамол 500 мг?", "Имате ли прахчета за грип?"],
            "children": ["Какво може да се даде при температура на бебе 8 месеца?", "Имате ли сироп за кашлица за 2-годишно дете?"],
            "cosmetics": ["Имате ли крем за атопична кожа?", "Имате ли шампоан против косопад?"],
            "chronic": ["Имате ли лекарства за диабет?", "Имате ли нещо за поддържане на стави?"],
            "non_medical": ["Как се доставя поръчката?"],
        }
        TEST_QUERIES_RUN = {k: v for k, v in sample.items()}
        print("⚠️  QUICK MODE: running 12 sample queries\n")
    else:
        TEST_QUERIES_RUN = TEST_QUERIES

    print(f"Starting E2E query tests at {datetime.now().isoformat()}\n")
    print("⚠️  Ensure API server is running the latest code (restart with: pkill -f api_server; python api_server.py)\n")

    try:
        response = requests.get("http://localhost:8000/health", timeout=5)
        if response.status_code != 200:
            print("❌ Server is not responding correctly. Please start the API server first.")
            return
    except Exception as e:
        print(f"❌ Cannot connect to API server: {e}")
        print("   Please start the server with: python api_server.py")
        return

    # Step 1: Clear server caches (first step of test run – fresh translations and reasoning)
    print("Step 1: Clearing server cache...")
    try:
        r = requests.post("http://localhost:8000/cache/clear", timeout=5)
        if r.status_code == 200:
            data = r.json()
            print(f"         Cache cleared: {data.get('cleared', [])}\n")
        else:
            print("         (Cache clear failed; continuing with existing cache)\n")
    except Exception as e:
        print(f"         (Could not clear cache: {e}; continuing)\n")

    print("Step 2: Running query tests...\n")
    results = run_all_tests(TEST_QUERIES_RUN if quick_mode else None)
    report = generate_report(results)
    print_report(report)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    output_file = OUTPUT_DIR / "test_results.json"

    output = {
        "timestamp": datetime.now().isoformat(),
        "report": report,
        "results": results,
    }

    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    print(f"\n💾 Detailed results saved to: {output_file}")
    print(f"\n✅ Test suite completed!")


if __name__ == "__main__":
    main()
