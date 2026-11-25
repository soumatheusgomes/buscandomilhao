from __future__ import annotations

from .models import NewsItem


def news_script(item: NewsItem) -> str:
    return (
        "Você viu isso sobre a reforma tributária? "
        f"{item.title.rstrip('.')}. "
        "Isso pode afetar empresas e contribuintes, mas a situação deve ser confirmada "
        "pela norma oficial. Conteúdo informativo: consulte seu contador. "
        f"Fonte: {item.source}. {item.url}"
    )


def education_script(topic: str) -> str:
    return (
        f"{topic}\n"
        "Não é promessa de retorno: primeiro entendemos o conceito, depois avaliamos riscos "
        "e objetivos. Conteúdo educacional, não recomendação de investimento."
    )
