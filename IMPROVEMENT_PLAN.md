# ViaPharma Chatbot - План за подобрения

Генериран: 2026-02-11

## Резюме на тестовете

| Метрика | Стойност |
|---------|----------|
| Общо тествани въпроси | 60 |
| Успешни | 44 (73.3%) |
| С проблеми | 16 (26.7%) |
| Средно време за отговор | 3.6 секунди |

## Резултати по категории

| Категория | Общо | Успех | Проблеми | Бележки |
|-----------|------|-------|----------|---------|
| Лекарства | 10 | 10 | 0 | Работи добре |
| Симптоми | 10 | 10 | 0 | Работи добре |
| Деца/бебета | 5 | 2 | 3 | Нужна специална обработка |
| Козметика | 5 | 5 | 0 | Работи добре |
| Хронични заболявания | 5 | 3 | 2 | Липсва предупреждение за рецепта |
| Доставка | 5 | 1 | 4 | **Критично:** Класифицира се като медицински |
| Плащане | 4 | 0 | 4 | **Критично:** Класифицира се като медицински |
| Безопасност | 6 | 3 | 3 | Липсват предупреждения |
| Двусмислени | 10 | 10 | 0 | Работи добре |

---

## Идентифицирани проблеми

### 1. КРИТИЧНО: E-commerce въпроси се обработват като медицински

**Симптом:** Въпроси като "За колко време се доставя поръчката?" и "Мога ли да платя с карта?" връщат препоръки за продукти вместо да бъдат разпознати като немедицински.

**Засегнати въпроси:**
- "За колко време се доставя поръчката?"
- "Каква е цената на доставката?"
- "Мога ли да върна продукт?"
- "Предлагате ли безплатна доставка?"
- "Мога ли да платя с карта?"
- "Приемате ли наложен платеж?"
- "Мога ли да получа фактура?"
- "Има ли отстъпка при по-голяма поръчка?"

**Причина:** В `intent_classifier.py` липсват ключови думи за e-commerce/административни въпроси.

**Решение:**
```python
# Добави в non_medical_keywords в intent_classifier.py:
'доставка', 'доставката', 'доставя', 'доставяне',
'поръчка', 'поръчката', 'поръчам',
'плащане', 'платя', 'карта', 'наложен платеж',
'връщане', 'върна', 'връщам',
'фактура', 'отстъпка', 'промоция', 'цена на доставка',
'проследя', 'проследяване', 'статус на поръчка',

# English
'delivery', 'shipping', 'order', 'payment', 'card',
'return', 'refund', 'invoice', 'discount', 'tracking',
```

**Файл:** `src/intent_classifier.py`

---

### 2. КРИТИЧНО: Силна алергична реакция не задейства Emergency

**Симптом:** При въпрос "Какво да правя при силна алергична реакция?" отговорът е "Препоръчваме консултация с лекар" вместо "Обадете се на 112".

**Причина:** В `safety.py` няма detection за "силна алергична реакция" / "тежка алергия" като emergency symptom.

**Решение:**
```python
# Добави в emergency_symptoms в safety.py:
'силна алергична реакция', 'тежка алергична реакция',
'анафилактична реакция', 'не мога да дишам от алергия',
'подуване на гърлото', 'оток на гърлото',

# English
'severe allergic reaction', 'serious allergic reaction',
'throat swelling', 'throat closing',
```

**Файл:** `src/safety.py`

---

### 3. ВИСОКО: Safety въпроси без disclaimer

**Симптом:** Въпроси като "Какво ще стане ако взема двойна доза?" и "Мога ли да пия алкохол с антибиотик?" не показват подходящ disclaimer.

**Засегнати въпроси:**
- "Мога ли да пия алкохол с антибиотик?"
- "Как да разбера дали имам предозиране?"

**Причина:** Safety layer проверява за симптоми, но не и за safety-related информационни въпроси.

**Решение:**
Добави нова категория "safety_queries" в safety.py:
```python
self.safety_information_queries = {
    # Bulgarian
    'двойна доза', 'предозиране', 'предозирах',
    'алкохол с лекарство', 'алкохол с антибиотик',
    'комбинирам лекарства', 'смесвам лекарства',
    'максимална доза', 'максималната доза',
    'безопасно ли е', 'опасно ли е',
    'странични ефекти', 'странични действия',

    # English
    'double dose', 'overdose', 'overdosed',
    'alcohol with medication', 'alcohol with antibiotic',
    'combine medications', 'mix medications',
    'maximum dose', 'safe to take',
    'side effects', 'dangerous',
}
```

И добави винаги disclaimer при match:
```python
def check_safety_query(self, text: str) -> bool:
    """Check if query is asking about medication safety."""
    text_lower = text.lower()
    return any(kw in text_lower for kw in self.safety_information_queries)
```

**Файл:** `src/safety.py`, `src/pipeline.py`

---

### 4. ВИСОКО: Препоръки за деца без възрастови ограничения

**Симптом:** При въпроси за деца/бебета системата не споменава възрастови ограничения.

**Засегнати въпроси:**
- "Подходящ ли е този сироп за 6-месечно бебе?"
- "Каква е дозата на Панадол за дете 15 кг?"
- "Какво препоръчвате при никнене на зъби?"

**Причина:** Pipeline не разпознава детски контекст и не добавя съответни предупреждения.

**Решение:**
1. Добави детекция за детски въпроси в pipeline:
```python
def _is_child_related_query(self, text: str) -> bool:
    """Check if query is about children/babies."""
    child_keywords = {
        'бебе', 'бебешки', 'дете', 'детски', 'деца',
        'месечно', 'годишно', 'месеца', 'години',
        'baby', 'infant', 'child', 'children', 'kid',
        'months old', 'years old', 'toddler',
    }
    return any(kw in text.lower() for kw in child_keywords)
```

2. Добави предупреждение при детски въпроси:
```python
CHILD_DISCLAIMER = """
⚠️ **Важно за деца и бебета:**
- Винаги проверявайте възрастовите ограничения на опаковката
- Дозировката зависи от възрастта и теглото на детето
- Консултирайте се с педиатър преди даване на лекарства на бебета под 6 месеца
- При съмнение, консултирайте се с фармацевт
"""
```

**Файлове:** `src/pipeline.py`

---

### 5. СРЕДНО: Хронични заболявания без предупреждение за рецепта

**Симптом:** Въпроси за диабет и щитовидна жлеза връщат OTC продукти без да споменат, че повечето лекарства са с рецепта.

**Засегнати въпроси:**
- "Имате ли лекарства за диабет?"
- "Как се приема това лекарство за щитовидната жлеза?"

**Решение:**
Добави detection за хронични заболявания:
```python
chronic_disease_keywords = {
    'диабет', 'захарен диабет', 'инсулин',
    'щитовидна', 'щитовидната жлеза', 'хипотиреоидизъм',
    'хипертония', 'високо кръвно', 'кръвно налягане',
    'астма', 'бронхиална астма',
    'епилепсия', 'гърчове',
    'diabetes', 'insulin', 'thyroid', 'hypertension',
    'asthma', 'epilepsy',
}
```

И добави съответен disclaimer:
```python
CHRONIC_DISCLAIMER = """
ℹ️ **Важно:** Лекарствата за хронични заболявания обикновено се отпускат по лекарска рецепта.
Моля, консултирайте се с вашия лекар за подходящо лечение.
Мога да ви помогна с допълнителни хранителни добавки и мониторинг устройства.
"""
```

**Файлове:** `src/pipeline.py`, `src/intent_classifier.py`

---

### 6. НИСКО: "Бебешки" задейства profanity filter (false positive)

**Симптом:** Въпросите "Имате ли бебешки сироп за температура?" и "Имате ли бебешки витамини?" се отхвърлят с "Моля, използвайте подходящ език."

**Причина:** Думата "бебе" частично съвпада с profanity pattern.

**Решение:**
Използвай word boundaries в profanity pattern:
```python
# В _compile_patterns(), за profanity:
profanity_pattern = '|'.join(r'\b' + re.escape(kw) + r'\b' for kw in self.profanity_keywords)
```

**Файл:** `src/intent_classifier.py`

---

## Приоритизиран план за действие

### Фаза 1: Критични (веднага)

1. **Fix e-commerce intent classification**
   - Файл: `src/intent_classifier.py`
   - Добави delivery/payment keywords в `non_medical_keywords`
   - Очаквано подобрение: +8 теста (100% delivery + payment)

2. **Fix emergency detection за алергични реакции**
   - Файл: `src/safety.py`
   - Добави "силна алергична реакция" и variants
   - Критично за безопасността на потребителите

3. **Fix profanity false positive за "бебе"**
   - Файл: `src/intent_classifier.py`
   - Добави word boundaries в regex pattern
   - Очаквано подобрение: +2 теста

### Фаза 2: Високо приоритетни (тази седмица)

4. **Добави safety query detection**
   - Файл: `src/safety.py`
   - Нова категория за информационни safety въпроси
   - Винаги показвай disclaimer

5. **Добави child-specific handling**
   - Файл: `src/pipeline.py`
   - Detection за детски въпроси
   - Специален disclaimer за възрастови ограничения

### Фаза 3: Подобрения (следваща седмица)

6. **Добави chronic disease handling**
   - Файлове: `src/pipeline.py`, `src/intent_classifier.py`
   - Detection + prescription warning

7. **Performance optimization**
   - Средно време 3.6s е приемливо, но може да се подобри
   - Кеширай чести заявки
   - Оптимизирай vector search

---

## Допълнителни препоръки

### Тестове за добавяне

```python
# Добави в tests/test_intent_classifier.py:
def test_delivery_questions_are_non_medical():
    classifier = IntentClassifier()
    delivery_questions = [
        "За колко време се доставя поръчката?",
        "Каква е цената на доставката?",
        "Мога ли да върна продукт?",
    ]
    for q in delivery_questions:
        is_medical, _, _ = classifier.is_medical_query(q)
        assert not is_medical, f"'{q}' should be non-medical"

def test_payment_questions_are_non_medical():
    classifier = IntentClassifier()
    payment_questions = [
        "Мога ли да платя с карта?",
        "Приемате ли наложен платеж?",
    ]
    for q in payment_questions:
        is_medical, _, _ = classifier.is_medical_query(q)
        assert not is_medical, f"'{q}' should be non-medical"

# Добави в tests/test_safety.py:
def test_severe_allergic_reaction_is_emergency():
    safety = SafetyLayer()
    result = safety.check_safety("Какво да правя при силна алергична реакция?")
    assert result.severity == "emergency"
    assert "112" in result.message
```

### Мониторинг за production

1. **Логвай класификацията:**
   ```python
   logger.info("Intent classification", extra={
       "query": query[:50],
       "is_medical": is_medical,
       "confidence": confidence,
       "reason": reason
   })
   ```

2. **Tracking на false positives/negatives:**
   - Добави feedback бутони в UI
   - Периодичен review на rejected queries

3. **Safety alerts:**
   - Изпращай notification при emergency/urgent
   - Dashboard за safety statistics

---

## Очаквани резултати след fixes

| Метрика | Сега | След Фаза 1 | След Фаза 2 |
|---------|------|-------------|-------------|
| Успешни | 73.3% | ~90% | ~95%+ |
| Delivery/Payment | 1/9 | 9/9 | 9/9 |
| Children | 2/5 | 4/5 | 5/5 |
| Safety | 3/6 | 5/6 | 6/6 |
