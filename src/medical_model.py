"""
MedGemma medical reasoning model wrapper.

Uses MLX for efficient inference on Apple Silicon.
"""

import os
from typing import Optional
from mlx_lm import load, generate


# System prompt for medical reasoning
MEDICAL_SYSTEM_PROMPT = """You are a knowledgeable pharmacy assistant helping customers find over-the-counter (OTC) medications for their symptoms.

Your role is to:
1. Analyze the symptoms described by the customer
2. Identify the likely condition(s) or causes
3. Suggest appropriate treatment categories (e.g., analgesics, antipyretics, antihistamines)
4. Note any important warnings or when to see a doctor

Important guidelines:
- Only recommend OTC (over-the-counter) treatments, never prescription medications
- Always advise seeing a doctor for serious or persistent symptoms
- Be concise and practical
- Do not diagnose specific diseases, just identify symptom patterns

Respond in a structured format:
- Symptoms identified: [list key symptoms]
- Likely cause: [common condition or cause]
- Recommended treatment type: [OTC category]
- Warnings: [any important cautions]
"""


class MedicalModel:
    """
    Wrapper for MedGemma model inference.

    Provides medical reasoning based on symptom descriptions.
    """

    def __init__(self, model_path: str = "./models/medgemma-4b-it-bf16"):
        """
        Initialize the medical model.

        Args:
            model_path: Path to the MedGemma model directory
        """
        self.model_path = model_path
        self.model = None
        self.tokenizer = None
        self._loaded = False

    def load(self) -> None:
        """Load the model into memory. Call this once at startup."""
        if self._loaded:
            return

        print(f"Loading MedGemma from {self.model_path}...")
        self.model, self.tokenizer = load(self.model_path)
        self._loaded = True
        print("MedGemma loaded successfully!")

    def _format_prompt(self, user_message: str, system_prompt: str = None) -> str:
        """
        Format the prompt using Gemma chat template.

        Args:
            user_message: The user's symptom description
            system_prompt: Optional custom system prompt

        Returns:
            Formatted prompt string
        """
        if system_prompt is None:
            system_prompt = MEDICAL_SYSTEM_PROMPT

        # Gemma 3 format: system prompt prepended to first user message
        # <start_of_turn>user\n{system}\n\n{user}<end_of_turn>\n<start_of_turn>model\n
        prompt = f"<start_of_turn>user\n{system_prompt}\n\n{user_message}<end_of_turn>\n<start_of_turn>model\n"
        return prompt

    def get_medical_reasoning(
        self,
        symptoms: str,
        max_tokens: int = 300,
        temperature: float = 0.7,
        system_prompt: str = None
    ) -> str:
        """
        Get medical reasoning for the given symptoms.

        Args:
            symptoms: Description of symptoms (in English)
            max_tokens: Maximum tokens to generate
            temperature: Sampling temperature (0.0 = deterministic, 1.0 = creative)
            system_prompt: Optional custom system prompt

        Returns:
            Medical reasoning response
        """
        if not self._loaded:
            self.load()

        prompt = self._format_prompt(symptoms, system_prompt)

        response = generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=max_tokens,
        )

        # Clean up response (remove any trailing incomplete sentences)
        response = response.strip()

        return response

    def refine_product_selection(
        self,
        user_query: str,
        medical_reasoning: str,
        candidate_products: list,
        max_products: int = 3
    ) -> list:
        """
        Use LLM to refine product selection from candidates.

        This implements Stage 2 of the Perplexity-style two-stage retrieval.

        Args:
            user_query: Original user query
            medical_reasoning: Medical analysis from get_medical_reasoning()
            candidate_products: List of Product objects from vector search
            max_products: Maximum number of products to return

        Returns:
            List of best-matching Product objects
        """
        if not self._loaded:
            self.load()

        if not candidate_products:
            return []

        # Build product list for prompt
        product_list = []
        for i, product in enumerate(candidate_products, 1):
            # Support both old (name) and new (title) field names
            name = getattr(product, 'title', None) or getattr(product, 'name', 'Unknown')
            product_info = f"{i}. {name}"

            # Add description/indications
            desc = getattr(product, 'description', None) or getattr(product, 'indications', None)
            if desc:
                product_info += f" - {desc[:100]}"

            # Add contraindications
            contra = getattr(product, 'contraindications', None)
            if contra:
                product_info += f" (Avoid if: {contra[:80]})"

            product_list.append(product_info)

        products_str = "\n".join(product_list)

        refinement_prompt = f"""Based on the customer's symptoms and the medical analysis, select the {max_products} most appropriate products.

Customer query: {user_query}

Medical analysis: {medical_reasoning}

Available products:
{products_str}

Select the {max_products} best products by their numbers. Consider:
- How well the product matches the symptoms
- Any contraindications mentioned
- Effectiveness for the condition

Respond with ONLY the product numbers separated by commas (e.g., "1, 3, 5").
"""

        prompt = self._format_prompt(refinement_prompt)

        response = generate(
            self.model,
            self.tokenizer,
            prompt=prompt,
            max_tokens=50,
        )

        # Parse the response to get product indices
        selected_indices = []
        try:
            # Extract numbers from response
            import re
            numbers = re.findall(r'\d+', response)
            for num in numbers:
                idx = int(num) - 1  # Convert to 0-indexed
                if 0 <= idx < len(candidate_products):
                    selected_indices.append(idx)
                if len(selected_indices) >= max_products:
                    break
        except Exception:
            # Fallback: return first N products
            selected_indices = list(range(min(max_products, len(candidate_products))))

        # If no valid indices found, return first N
        if not selected_indices:
            selected_indices = list(range(min(max_products, len(candidate_products))))

        return [candidate_products[i] for i in selected_indices]


# Global model instance (lazy loaded)
_medical_model: Optional[MedicalModel] = None


def get_medical_model() -> MedicalModel:
    """Get or create the global medical model instance."""
    global _medical_model
    if _medical_model is None:
        model_path = os.environ.get(
            "MEDGEMMA_MODEL_PATH",
            "./models/medgemma-4b-it-bf16"
        )
        _medical_model = MedicalModel(model_path)
    return _medical_model
