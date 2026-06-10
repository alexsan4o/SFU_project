"""Форматирование ответа API в безопасный HTML для Telegram.

Важно: используем parse_mode=HTML и экранируем ВСЕ динамические данные,
иначе спецсимволы в названиях/описаниях (_, *, <, & и т.п.) ломают разбор
сообщения, и Telegram отказывается его отправлять.
"""
import html

DISCLAIMER = (
    "\n\n⚠️ <i>Внимание: не собирайте и не употребляйте грибы, "
    "опираясь только на результат бота. При сомнениях проконсультируйтесь "
    "с опытным грибником или микологом.</i>"
)

NOT_RECOGNIZED = (
    "😕 Не удалось распознать гриб. Попробуйте сделать более чёткое фото "
    "при хорошем освещении, чтобы в кадр попали шляпка, ножка и пластинки."
)


def esc(value) -> str:
    """Безопасно экранирует значение для HTML Telegram."""
    return html.escape(str(value), quote=False)


def _edibility_icon(edibility: str, toxicity: str) -> str:
    text = f"{edibility} {toxicity}".lower()
    # ☠️ — только для реально опасных (ядовитых/токсичных) видов
    if any(w in text for w in ("poison", "toxic", "deadly", "ядовит", "токсич")):
        return "☠️"
    # ⛔ — несъедобный, но не обязательно ядовитый (проверяем ДО «съедоб»,
    # т.к. «несъедоб»/«inedible» содержат подстроку «съедоб»/«edible»)
    if any(w in text for w in ("inedible", "not edible", "несъедоб")):
        return "⛔"
    if "edible" in text or "съедоб" in text:
        return "✅"
    return "❓"


def _is_dangerous(edibility: str, toxicity: str) -> bool:
    text = f"{edibility} {toxicity}".lower()
    return any(w in text for w in ("poison", "toxic", "deadly", "ядовит", "токсич"))


def format_identification(data: dict, confidence_threshold: float = 0.80) -> str:
    """Превращает JSON-ответ API в готовое HTML-сообщение.

    Устойчиво к отсутствующим/None полям и нестандартной структуре —
    в худшем случае вернёт понятное сообщение, но не упадёт.
    """
    if not isinstance(data, dict):
        return NOT_RECOGNIZED

    result = data.get("result") or {}
    classification = result.get("classification") or {}
    suggestions = classification.get("suggestions") or []

    # Иногда API сразу отвечает is_mushroom=false
    is_mushroom = result.get("is_mushroom")
    if isinstance(is_mushroom, dict):
        prob = is_mushroom.get("probability")
        if isinstance(prob, (int, float)) and prob < 0.5:
            return (
                "🤔 На фото, похоже, нет гриба или он плохо различим. "
                "Пришлите снимок гриба крупным планом."
            )

    if not suggestions:
        return NOT_RECOGNIZED

    top = suggestions[0] or {}
    name = top.get("name") or "Неизвестный вид"
    raw_prob = top.get("probability")
    probability = raw_prob if isinstance(raw_prob, (int, float)) else 0.0
    prob_pct = round(probability * 100, 1)

    details = top.get("details") or {}
    common_names = details.get("common_names") or []
    if not isinstance(common_names, list):
        common_names = []
    edibility = details.get("edibility") or ""
    toxicity = details.get("toxicity") or ""
    desc_obj = details.get("description")
    description = ""
    if isinstance(desc_obj, dict):
        description = desc_obj.get("value") or ""
    elif isinstance(desc_obj, str):
        description = desc_obj

    icon = _edibility_icon(edibility, toxicity)

    lines = ["🍄 <b>Результат распознавания</b>", "", f"<b>Вид:</b> {esc(name)}"]

    if common_names:
        names = ", ".join(esc(n) for n in common_names[:3] if n)
        if names:
            lines.append(f"<b>Народные названия:</b> {names}")

    lines.append(f"<b>Уверенность:</b> {prob_pct}%")

    # Порог уверенности — снижаем риск ложного вердикта
    if probability < confidence_threshold:
        lines.append(
            "⚠️ <b>Низкая уверенность.</b> Результат ненадёжен — "
            "не принимайте его как точное определение."
        )

    if edibility:
        lines.append(f"<b>Съедобность:</b> {icon} {esc(edibility)}")
    if toxicity:
        lines.append(f"<b>Токсичность:</b> {esc(toxicity)}")

    if _is_dangerous(edibility, toxicity):
        lines.append("\n☠️ <b>ОПАСНО:</b> вид может быть ядовитым. Не употребляйте в пищу!")

    if description:
        short = description[:350] + "…" if len(description) > 350 else description
        lines.append(f"\n📝 <b>Описание:</b>\n{esc(short)}")

    # Альтернативные варианты (важно для безопасности — двойники)
    alts = [s for s in suggestions[1:4] if isinstance(s, dict)]
    if alts:
        lines.append("\n🔍 <b>Другие возможные варианты:</b>")
        for s in alts:
            alt_name = s.get("name") or "?"
            alt_raw = s.get("probability")
            alt_prob = round((alt_raw if isinstance(alt_raw, (int, float)) else 0.0) * 100, 1)
            lines.append(f"• {esc(alt_name)} — {alt_prob}%")

    return "\n".join(lines) + DISCLAIMER
