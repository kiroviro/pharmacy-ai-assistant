"""
Response formatting and building for the ViaPharma pipeline.

Handles all response template generation, product card formatting,
safety blocks, triage defaults, and markdown formatting.

Extracted from orchestrator.py to improve code organization and testability.
"""

from src.logging_config import get_logger
from src.medical_model import MedicalReasoning
from src.pipeline.models import Product
from src.pipeline.product_ingredients import (
    INGREDIENT_BG_NAMES,
    build_ingredient_duplication_warning,
    extract_all_product_ingredients,
    extract_composition_summary,
    extract_contraindication_summary,
    extract_product_ingredient,
    is_combination_product,
)

logger = get_logger("viapharma.response_builder")


class ResponseBuilder:
    """
    Builds formatted responses for different query types.

    Handles:
    - Product card formatting (markdown)
    - Safety blocks and warnings
    - Triage recommendations
    - Template assembly (unified, catalog, comparison)
    """

    # Specialized medical conditions that require specific products
    _SPECIALIZED_DERMATOLOGY_TERMS = {
        "атопична": {
            "condition": "атопична кожа / атопичен дерматит",
            "explanation": "Атопичният дерматит е хронично състояние, което изисква специализирани продукти с церамиди, колоиден овес или други специфични съставки.",
            "recommendations": [
                "La Roche-Posay Lipikar Baume AP+M",
                "Eucerin AtopiControl",
                "Mustela Stelatopia",
                "Bioderma Atoderm Intensive",
            ],
            "fallback_advice": "Показаните продукти са за суха и чувствителна кожа, но за атопичен дерматит се препоръчват специализирани дерматологични продукти.",
        },
        "атопичен дерматит": {
            "condition": "атопичен дерматит",
            "explanation": "Атопичният дерматит изисква специализирани продукти, разработени за силно раздразнена и склонна към екзема кожа.",
            "recommendations": [
                "La Roche-Posay Lipikar Baume AP+M",
                "Eucerin AtopiControl",
                "Mustela Stelatopia",
            ],
            "fallback_advice": "За атопичен дерматит консултирайте дерматолог за най-подходящия продукт.",
        },
        "екзема": {
            "condition": "екзема",
            "explanation": "Екземата изисква специализирани продукти с противовъзпалителни и възстановяващи кожната бариера свойства.",
            "recommendations": [
                "La Roche-Posay Cicaplast Baume B5",
                "Eucerin AtopiControl",
                "Avène Cicalfate",
            ],
            "fallback_advice": "Показаните продукти могат да помогнат, но за екзема се препоръчват специализирани лечебни продукти.",
        },
        "псориазис": {
            "condition": "псориазис",
            "explanation": "Псориазисът е автоимунно заболяване, което изисква специализирани продукти с кератолитици (салицилова киселина, урея).",
            "recommendations": [
                "La Roche-Posay Iso-Urea",
                "Eucerin UreaRepair",
                "Препарати с каменовъглен катран",
            ],
            "fallback_advice": "За псориазис е необходима консултация с дерматолог. Показаните продукти не са специализирани за това състояние.",
        },
        "розацея": {
            "condition": "розацея",
            "explanation": "Розацеята изисква специални продукти за чувствителна кожа със склонност към зачервяване.",
            "recommendations": [
                "La Roche-Posay Rosaliac",
                "Avène Antirougeurs",
                "Bioderma Sensibio AR",
            ],
            "fallback_advice": "За розацея се препоръчват специализирани продукти с азелаинова киселина или ниацинамид.",
        },
    }

    def __init__(self):
        """Initialize the response builder."""
        pass

    def _detect_specialized_condition(self, query: str) -> dict:
        """
        Detect if query is for a specialized dermatological condition.

        Returns dict with condition info if specialized term detected, None otherwise.
        """
        query_lower = query.lower()

        for term, info in self._SPECIALIZED_DERMATOLOGY_TERMS.items():
            if term in query_lower:
                return info

        return None

    def _final_garbage_cleanup(self, response: str) -> str:
        """
        Final pass to remove any remaining garbage patterns from the complete response.

        This catches garbage that might appear in product descriptions or other
        sections that aren't filtered during formatting (Issue #17).
        """
        if not response:
            return response

        response_lower = response.lower()

        # Check for critical garbage patterns
        critical_patterns = [
            "зъбні протези",
            "зъбни протези",
            "грижа за зъбні протези",
            "защита на личните",
            "лични данни",
            "средство за защита",
            "репелент",
            "комар",
            "комари",
            "металокерамика",  # Dental materials hallucination
            "система за запаметяване",  # System for remembering (nonsense)
        ]

        has_garbage = any(p in response_lower for p in critical_patterns)
        if not has_garbage:
            return response

        # Remove sentences containing garbage
        lines = response.split("\n")
        cleaned_lines = []

        for line in lines:
            line_lower = line.lower()
            # Skip lines that contain garbage patterns
            if any(p in line_lower for p in critical_patterns):
                logger.warning(f"Removed line with garbage pattern: {line[:100]}")
                continue
            cleaned_lines.append(line)

        cleaned = "\n".join(cleaned_lines)

        # Clean up any double newlines
        while "\n\n\n" in cleaned:
            cleaned = cleaned.replace("\n\n\n", "\n\n")

        return cleaned

    def build_triage_defaults(
        self, medical_reasoning: MedicalReasoning, products: list, original_query: str
    ) -> list[str]:
        """Build triage items primarily from product contraindication data.

        Minimal hardcoding — reads actual product contraindications for warnings
        and adds only 2 generic fallbacks (duration, worsening).
        """
        items = []
        seen = set()

        query_lower = (original_query or "").lower()

        # 1. Scan product contraindications for serious condition mentions
        if products:
            all_contras = " ".join(
                (p.contraindications or "").lower()
                for p in products
                if hasattr(p, "contraindications") and p.contraindications
            )
            # High fever warning (from contraindication context)
            if any(kw in all_contras for kw in ["температур", "треска"]) or "температур" in query_lower:
                items.append("Температурата надвиши 39°C или продължава >3 дни")
                seen.add("температура")
            if "кървав" in all_contras:
                items.append("Появят се кървави изпражнения или повръщане")
            if "затруднено дишане" in all_contras:
                items.append("Имате затруднено дишане")
            if "алергичн" in all_contras or "обрив" in all_contras:
                items.append("Появи се обрив, подуване или алергична реакция")

        # 2. Child-specific (from query context, not hardcoded list)
        if any(kw in query_lower for kw in ["бебе", "дете", "месец"]):
            items.append("Бебето отказва храна или течности")
            if "температура" not in seen:
                items.append("Температурата надвиши 38.5°C при бебе")

        # 3. Always: duration + worsening (minimal generic fallbacks)
        if not any("дни" in item for item in items):
            items.append("Симптомите продължават повече от 3 дни")
        items.append("Появят се силни или нови симптоми")

        return items

    def build_safety_block(self, medical_reasoning: MedicalReasoning, products: list, original_query: str) -> str:
        """Build compact safety block before products.

        Uses product contraindication data + context-aware logic.
        Minimally hardcoded — derives warnings from actual product data.
        """
        lines = ["🛡️ **Преди да изберете продукт**"]

        query_lower = (original_query or "").lower()

        # 1. Ingredient duplication warning — derived from products
        seen_ingredients = set()
        has_duplication_risk = False
        for p in products or []:
            ings = extract_all_product_ingredients(p)
            for ing in ings:
                if ing in seen_ingredients:
                    has_duplication_risk = True
                seen_ingredients.add(ing)
        if has_duplication_risk or seen_ingredients:
            # Find the most common ingredient
            top_ing = next(iter(seen_ingredients), "")
            top_bg = INGREDIENT_BG_NAMES.get(top_ing, "")
            if top_bg:
                lines.append(f"• Не комбинирайте продукти със **{top_bg}** — риск от предозиране")
            else:
                lines.append("• Не комбинирайте продукти с еднаква активна съставка")

        # 2. Age-specific warning — from query context
        is_child = any(kw in query_lower for kw in ["бебе", "дете", "детето", "месец", "годин"])
        if is_child:
            lines.append("• Проверете възрастовите ограничения — не всички продукти са за деца")
        else:
            lines.append("• Проверете листовката за възрастови ограничения и дозировка")

        # 3. Contraindication-derived warning — scan actual product data
        if products:
            all_contras = " ".join(
                (p.contraindications or "").lower()
                for p in products
                if hasattr(p, "contraindications") and p.contraindications
            )
            if any(kw in all_contras for kw in ["язва", "стомашно кървене", "гастрит"]):
                lines.append("• Избягвайте при стомашни проблеми — проверете противопоказанията")
            elif any(kw in all_contras for kw in ["бъбрец", "бъбречн", "чернодроб"]):
                lines.append("• При чернодробни или бъбречни проблеми — консултирайте лекар")
            elif any(kw in query_lower for kw in ["хронич", "диабет", "кръвно", "астма"]):
                lines.append("• При хронични заболявания се консултирайте с лекар")

        # 4. Pregnancy/breastfeeding (from query)
        if any(kw in query_lower for kw in ["бременна", "бременност", "кърмя", "кърмене"]):
            lines.append("• Консултирайте се с лекар — не всички лекарства са безопасни")

        return "\n".join(lines)

    def format_product_card(
        self, product, index: int, treatment_type: str, medical_reasoning: MedicalReasoning
    ) -> str:
        """Format a single product card (gold standard format):

        ### Product Title
        ✔ Съдържа [ingredient] — data from product.composition
        ⚠️ [Safety warning] — data from product.contraindications
        (Combo note if single symptom + combination product)
        """
        lines = []

        # Product display (no numbering; ## title + image + price + desc + link from to_display_string)
        display = product.to_display_string() if isinstance(product, Product) else str(product)
        lines.append(display)

        # Extract ingredient and all ingredients (for combo detection)
        ingredient = extract_product_ingredient(product)
        all_ingredients = extract_all_product_ingredients(product)
        is_combo = len(all_ingredients) >= 2
        # Also treat cold/flu multi-symptom products as combo (title keywords only)
        # Narrowed to avoid false positives on simple paracetamol (Issue #18)
        if not is_combo:
            title_lower = (product.title or "").lower()
            # Require specific cold/flu combo terms in title (not just description)
            combo_markers = [
                "грип и настинка",
                "при грип",
                "грипни симптоми",
                "простуд",
                "простуда и грип",
                "мулти-симптом",
                "multi-symptom",
            ]
            # Product must have combo marker AND multiple symptom mentions to qualify
            if any(marker in title_lower for marker in combo_markers):
                symptom_count_in_title = sum(
                    1 for s in ["температур", "кашлица", "хрема", "болка в гърл"]
                    if s in title_lower
                )
                is_combo = symptom_count_in_title >= 2

        # ✔ Active ingredient line (from product's own Състав)
        ingredient_bg = INGREDIENT_BG_NAMES.get(ingredient, "") if ingredient else ""
        if ingredient_bg:
            lines.append(f"✔ Съдържа **{ingredient_bg}**")
        else:
            # Fallback: show composition summary from product's own data
            comp_summary = extract_composition_summary(product)
            if comp_summary:
                lines.append(f"✔ {comp_summary}")

        # Safety: short leaflet reminder or specific contra (no icon)
        contra_summary = extract_contraindication_summary(product)
        if contra_summary and len(contra_summary) < 120:
            lines.append(contra_summary)
        else:
            lines.append("Прочетете листовката преди употреба")

        # Ingredient duplication warning
        dup_warning = build_ingredient_duplication_warning(product, ingredient)
        if dup_warning:
            lines.append(dup_warning)

        # Combo product note for single-symptom queries
        symptom_count = len(medical_reasoning.symptoms) if medical_reasoning.symptoms else 1
        if is_combo and symptom_count <= 1:
            lines.append(
                f"ℹ️ Комбиниран продукт за симптоми на простуда. "
                f"Ако нямате допълнителни симптоми, по-подходящ е продукт само с {ingredient_bg or 'една съставка'}."
            )

        lines.append("")
        return "\n".join(lines)

    def format_catalog_response(self, search_term: str, products: list, original_query: str = "") -> str:
        """Format catalog response using VP template (safety, triage, footer).
        Aligns with e2e test expectations for 🛒 Подходящи продукти, ✔ Съдържа, ⚠️ Потърсете лекар, ℹ️.
        """
        parts = []
        empty_reasoning = MedicalReasoning(
            symptoms=[], likely_cause="", treatment_type="", warnings=[], see_doctor=False
        )

        # Check if this is a specialized dermatology query
        specialized_info = self._detect_specialized_condition(original_query or search_term)

        # ── SECTION 1: Symptom/query header ─────────────────────────────────
        parts.append(f"## 🔍 Информация при симптом: {search_term.title()}\n")

        # Add specialized condition notice if detected
        if specialized_info:
            parts.append(f"**Търсите продукти за: {specialized_info['condition']}**\n")
            parts.append(f"⚠️ *{specialized_info['explanation']}*\n")

            # Always show recommendations for specialized conditions (catalog gap)
            parts.append(f"\n💡 **Важно**: {specialized_info['fallback_advice']}\n")
            parts.append("\n**Препоръчани специализирани продукти:**")
            for rec in specialized_info["recommendations"]:
                parts.append(f"• {rec}")

            if products:
                parts.append("\n**Алтернативи в наличност** (за суха/чувствителна кожа):\n")
            else:
                parts.append("\n*В момента нямаме специализирани продукти за това състояние в каталога.*\n")
        else:
            parts.append(f'*Намерени продукти за „{search_term}"*.\n')

        # ── SECTION 2: Active ingredients (derived from products) ─────────────
        # ALWAYS show this section when products exist (Issue #18)
        parts.append("---")
        if products:
            seen_ingredients = set()
            for p in products[:5]:
                for ing in extract_all_product_ingredients(p):
                    seen_ingredients.add(ing)

            parts.append("## 💊 Подходящи активни съставки\n")
            if seen_ingredients:
                for ing in list(seen_ingredients)[:5]:
                    bg = INGREDIENT_BG_NAMES.get(ing, ing)
                    parts.append(f"• **{bg}**")
            else:
                # Fallback when ingredient extraction fails
                parts.append("*Проверете активните съставки и дозировката в листовката на продукта.*")
            parts.append("")

        # ── SECTION 3: Safety block ──────────────────────────────────────────
        parts.append("---")
        safety_block = self.build_safety_block(empty_reasoning, products, original_query)
        if safety_block:
            parts.append(safety_block)
            parts.append("")

        # ── SECTION 4: Products (VP format: ## title, ✔ Съдържа, ⚠️) ──────
        parts.append("---")
        parts.append("## 🛒 Подходящи продукти\n")
        if products:
            for i, product in enumerate(products[:5], 1):
                if i > 1:
                    parts.append("---")
                card = self.format_product_card(product, i, "", empty_reasoning)
                parts.append(card)
            parts.append("")
        else:
            parts.append(f'*Съжалявам, не намерих продукти за „{search_term}" в каталога.*')
            parts.append("\n*Опитайте с друга ключова дума или опишете за какво ви е нужен продуктът.*\n")

        # ── SECTION 5: Triage ───────────────────────────────────────────────
        parts.append("---")
        parts.append("## ⚠️ Потърсете лекар ако:\n")
        triage_items = self.build_triage_defaults(empty_reasoning, products, original_query)
        for item in triage_items:
            parts.append(f"• {item}")
        parts.append("")

        # ── SECTION 6: Footer ────────────────────────────────────────────────
        parts.append("---")
        parts.append("ℹ️ **Важна информация**")

        # Add specialized condition reminder if applicable
        if specialized_info:
            parts.append(f"⚠️ За {specialized_info['condition']} се препоръчва консултация с дерматолог.")
            if products:
                parts.append("Показаните продукти са общи алтернативи, но не са специализирани за това състояние.")

        parts.append("Информацията има общ характер и не замества консултация с лекар или фармацевт.")
        parts.append("Преди употреба прочетете листовката.")

        response = "\n".join(parts)
        # Final garbage cleanup pass (Issue #17)
        return self._final_garbage_cleanup(response)

    def format_comparison_response(self, drug_names: list[str], products_by_drug: dict) -> str:
        """Format the response for a medication comparison query."""
        # Drug info for common comparisons
        drug_info = {
            "ибупрофен": {
                "class": "НСПВС (нестероидно противовъзпалително)",
                "strength": "Средна сила",
                "uses": "болка, възпаление, температура",
                "caution": "Да се избягва при стомашни проблеми",
            },
            "диклофенак": {
                "class": "НСПВС (нестероидно противовъзпалително)",
                "strength": "По-силен от ибупрофен",
                "uses": "силна болка, възпаление, артрит",
                "caution": "По-висок риск от стомашни проблеми",
            },
            "парацетамол": {
                "class": "Аналгетик/антипиретик",
                "strength": "По-слаб от НСПВС",
                "uses": "болка, температура (без противовъзпалително)",
                "caution": "По-безопасен за стомаха",
            },
            "аспирин": {
                "class": "НСПВС",
                "strength": "Средна сила",
                "uses": "болка, температура, разреждане на кръвта",
                "caution": "Не за деца; риск от кървене",
            },
        }

        # Map input drug names to canonical names
        canonical_map = {
            "ibuprofen": "ибупрофен",
            "нурофен": "ибупрофен",
            "nurofen": "ибупрофен",
            "diclofenac": "диклофенак",
            "волтарен": "диклофенак",
            "voltaren": "диклофенак",
            "paracetamol": "парацетамол",
            "acetaminophen": "парацетамол",
            "панадол": "парацетамол",
            "aspirin": "аспирин",
        }

        lines = ["## 💊 Сравнение на лекарства\n"]

        # Add info for each drug
        for drug in drug_names:
            canonical = canonical_map.get(drug.lower(), drug.lower())
            display_name = drug.capitalize()

            lines.append(f"### {display_name}")

            if canonical in drug_info:
                info = drug_info[canonical]
                lines.append(f"- **Клас:** {info['class']}")
                lines.append(f"- **Сила:** {info['strength']}")
                lines.append(f"- **Употреба:** {info['uses']}")
                lines.append(f"- **Внимание:** {info['caution']}")
            else:
                lines.append("- Информация не е налична в базата данни")

            # Add products for this drug
            products = products_by_drug.get(drug, [])
            if products:
                lines.append(f"\n**Налични продукти с {display_name}:**")
                for i, p in enumerate(products[:2], 1):
                    price_str = f"{p.price_bgn:.2f} лв" if p.price_bgn else "N/A"
                    url = p.product_url or "#"
                    lines.append(f"{i}. [{p.title}]({url}) - {price_str}")
            else:
                lines.append(f"\n⚠️ *Няма налични продукти с {display_name} в каталога*")

            lines.append("")

        # Add active ingredients section (Issue #18 - template compliance)
        lines.append("---")
        lines.append("## 💊 Активни съставки\n")
        # Extract ingredients from all products
        all_products = []
        for products in products_by_drug.values():
            all_products.extend(products)

        if all_products:
            seen_ingredients = set()
            for p in all_products:
                for ing in extract_all_product_ingredients(p):
                    seen_ingredients.add(ing)

            if seen_ingredients:
                for ing in list(seen_ingredients)[:5]:
                    bg = INGREDIENT_BG_NAMES.get(ing, ing)
                    lines.append(f"• **{bg}**")
            else:
                lines.append("*Проверете активните съставки в листовката на всеки продукт.*")
            lines.append("")

        # Add recommendation
        lines.append("---")
        lines.append("**⚠️ Важно:** Изборът на лекарство зависи от конкретното състояние.")
        lines.append("Консултирайте се с фармацевт за персонална препоръка.")

        response = "\n".join(lines)
        # Final garbage cleanup pass (Issue #17)
        return self._final_garbage_cleanup(response)
