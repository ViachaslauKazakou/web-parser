import hashlib
import html
import math
import re
from collections import Counter
from typing import Any

from app.schemas import AnalysisRequest, MessageInput

TOKEN_RE = re.compile(r"\w+", re.UNICODE)
HTML_RE = re.compile(r"<[^>]+>")
URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
SPACE_RE = re.compile(r"\s+")
STOPWORDS = frozenset(
    "а без более бы был была были было быть в во вот все всего да для до его ее если есть и из или им их как так к ко когда кто ли либо мне может мы на над но о об от по при про с со то у уже это я the a an and are as at be by for from has have he in is it its of on or that their this to was were will with you your".split()
)


def scoring_tokens(text: str) -> list[str]:
    tokens = TOKEN_RE.findall(text.lower().replace("_", " "))
    return [token for token in tokens if token not in STOPWORDS]


def normalize_text(text: str | None) -> tuple[str, list[str]]:
    decoded = html.unescape(text or "")
    without_markup = HTML_RE.sub(" ", decoded)
    without_urls = URL_RE.sub(" ", without_markup)
    normalized = SPACE_RE.sub(" ", without_urls).strip().lower()
    return normalized, TOKEN_RE.findall(normalized)


def vectorize_text(text: str, dimensions: int = 128) -> list[float]:
    vector = [0.0] * dimensions
    for token in scoring_tokens(text):
        bucket = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16) % dimensions
        vector[bucket] += 1.0
    norm = math.sqrt(sum(value * value for value in vector))
    return [value / norm for value in vector] if norm else vector


def cosine_similarity(left: list[float], right: list[float]) -> float:
    if len(left) != len(right) or not left or not right:
        return 0.0
    return sum(a * b for a, b in zip(left, right))


def lexical_overlap(topic_tokens: set[str], answer_tokens: set[str]) -> float:
    return len(topic_tokens & answer_tokens) / len(topic_tokens) if topic_tokens and answer_tokens else 0.0


def repeated_token_ratio(tokens: list[str]) -> float:
    if not tokens:
        return 0.0
    return sum(count - 1 for count in Counter(tokens).values() if count > 1) / len(tokens)


def _quality_score(count: int) -> float:
    return 0.08 if count >= 18 else 0.04 if count >= 10 else 0.01 if count >= 5 else 0.0


def _short_penalty(count: int) -> float:
    return 0.0 if count >= 5 else 0.03 if count == 4 else 0.07 if count == 3 else 0.12


def _label(score: float) -> str:
    if score >= 0.45:
        return "high"
    if score >= 0.25:
        return "medium"
    if score >= 0.15:
        return "low"
    return "offtopic"


def _explanation(features: dict[str, Any], score: float, has_first_message: bool) -> str:
    if score >= 0.55:
        return "Ответ хорошо отвечает на вопрос и тесно связан с темой обсуждения."
    if score >= 0.40:
        return "Ответ достаточно релевантен вопросу и теме."
    if has_first_message and features["similarity_first_message"] < 0.15:
        return "Ответ слабо связан с исходным вопросом темы."
    if features["lexical_overlap"] == 0 and features["similarity_title"] < 0.2:
        return "Ответ слабо связан с формулировкой темы и уходит от основного вопроса."
    if features["short_answer_penalty"] > 0:
        return "Ответ частично по теме, но слишком краткий для уверенной высокой оценки."
    return "Ответ связан с темой, но релевантность средняя из-за ограниченного совпадения по смыслу."


def _remove_quoted_fragments(answer: str, fragments: list[str]) -> str:
    result = answer
    for fragment in fragments:
        if fragment and (len(fragment.split()) >= 5 or len(fragment) >= 20):
            result = result.replace(fragment, " ")
    return SPACE_RE.sub(" ", result).strip()


def rank_messages(payload: AnalysisRequest) -> list[dict[str, Any]]:
    """Deterministic 128-bucket hashed-BOW relevance ranking from the source service."""
    title, _ = normalize_text(payload.topic.title)
    description, _ = normalize_text(payload.topic.description)
    first_message, _ = normalize_text(payload.topic.first_message_content)
    title_tokens = set(scoring_tokens(title))
    description_tokens = set(scoring_tokens(description))
    first_message_tokens = set(scoring_tokens(first_message))
    topic_tokens = title_tokens | description_tokens | first_message_tokens
    has_first_message = bool(first_message)
    use_community = payload.options.use_community_weight
    results: list[dict[str, Any]] = []

    for index, message in enumerate(payload.messages, start=1):
        answer, answer_tokens = normalize_text(message.content)
        answer = _remove_quoted_fragments(answer, [title, description, first_message])
        answer_tokens = TOKEN_RE.findall(answer)
        answer_signal_tokens = set(scoring_tokens(answer))

        # A compact hash vector can collide. Trust cosine values only when the
        # candidate shares at least one meaningful token with that context.
        title_similarity = (
            cosine_similarity(vectorize_text(title), vectorize_text(answer))
            if title_tokens & answer_signal_tokens
            else 0.0
        )
        description_similarity = (
            cosine_similarity(vectorize_text(description), vectorize_text(answer))
            if description_tokens & answer_signal_tokens
            else 0.0
        )
        first_similarity = (
            cosine_similarity(vectorize_text(first_message), vectorize_text(answer))
            if first_message and first_message_tokens & answer_signal_tokens
            else 0.0
        )
        overlap = lexical_overlap(topic_tokens, answer_signal_tokens)
        repeats = repeated_token_ratio(answer_tokens)
        count = len(answer_tokens)
        quality = _quality_score(count)
        short_penalty = _short_penalty(count)
        community = (max(min(float(message.rating or 0.0), 10.0), -10.0) / 10.0 * 0.1) if use_community else 0.0
        spam_penalty = min((repeats - 0.35) * 0.3, 0.15) if repeats >= 0.35 else 0.0

        features = {
            "similarity_title": round(title_similarity, 4),
            "similarity_description": round(description_similarity, 4),
            "similarity_first_message": round(first_similarity, 4),
            "lexical_overlap": round(overlap, 4),
            "quality_score": round(quality, 4),
            "community_score": round(community, 4),
            "short_answer_penalty": round(short_penalty, 4),
            "spam_penalty": round(spam_penalty, 4),
            "metadata": {
                "answer_token_count": count,
                "repeated_token_ratio": round(repeats, 4),
                "topic_token_count": len(topic_tokens),
            },
        }

        if has_first_message:
            base_score = (
                0.25 * title_similarity
                + 0.15 * description_similarity
                + 0.5 * first_similarity
                + 0.1 * overlap
            )
        else:
            base_score = 0.55 * title_similarity + 0.35 * description_similarity + 0.1 * overlap
        final_score = max(0.0, min(1.0, base_score + quality + community - short_penalty - spam_penalty))
        results.append(
            {
                "external_message_ref": message.external_id or str(index),
                "author": message.author,
                "content": message.content,
                "base_score": round(base_score, 4),
                "final_score": round(final_score, 4),
                "relevance_label": _label(final_score),
                "features": features,
                "explanation_short": _explanation(features, final_score, has_first_message),
            }
        )

    results.sort(key=lambda item: (item["final_score"], item["base_score"]), reverse=True)
    for rank_position, result in enumerate(results, start=1):
        result["rank_position"] = rank_position
    return results


def message_from_parser(item: dict[str, Any], index: int) -> MessageInput | None:
    content = (item.get("message") or item.get("content") or "").strip()
    if not content:
        return None
    return MessageInput(
        external_id=str(item.get("external_id") or item.get("url") or index),
        author=item.get("author") or None,
        content=content,
        rating=item.get("rating"),
        created_at=item.get("created_at") or item.get("date"),
    )
