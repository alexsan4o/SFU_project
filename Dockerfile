FROM python:3.12-slim

# Не пишем .pyc, не буферизуем вывод (логи сразу видны)
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# Сначала зависимости — лучше кешируется
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Затем код
COPY *.py ./

# Запуск от непривилегированного пользователя
RUN useradd --create-home --uid 10001 appuser
USER appuser

CMD ["python", "bot.py"]
