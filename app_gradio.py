"""
ViaPharma OTC Chatbot - Gradio Interface

A Bulgarian-language medical chatbot that recommends OTC products
based on customer symptoms.
"""

import gradio as gr
from src.pipeline import get_pipeline


def chat(message: str, history: list) -> str:
    """
    Process a chat message through the pipeline.

    Args:
        message: User's input message
        history: List of previous (user, assistant) message tuples

    Returns:
        Assistant's response
    """
    pipeline = get_pipeline()
    result = pipeline.process(message)
    return result.response


def create_app() -> gr.Blocks:
    """Create and configure the Gradio application."""

    with gr.Blocks(title="ViaPharma - Аптечен Асистент") as app:

        # Header
        gr.Markdown(
            """
            # ViaPharma - Аптечен Асистент

            Здравейте! Аз съм вашият виртуален аптечен асистент.
            Опишете вашите симптоми и ще ви препоръчам подходящи продукти без рецепта.

            **Примерни въпроси:**
            - Имам силно главоболие, какво да взема?
            - Болки в гърлото и хрема от два дни
            - Какво помага при стомашни болки?
            """
        )

        # Chat interface
        gr.ChatInterface(fn=chat)

        # Footer with disclaimer
        gr.Markdown(
            """
            ---
            **Важно:** Този асистент предоставя само информационни услуги и не замества
            консултацията с лекар или фармацевт. При сериозни симптоми, моля потърсете
            медицинска помощ.

            *ViaPharma.us - Вашата онлайн аптека*
            """
        )

    return app


if __name__ == "__main__":
    app = create_app()
    app.launch(
        server_name="0.0.0.0",
        server_port=7860,
        share=False,
    )
