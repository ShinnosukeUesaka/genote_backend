FROM python:3.11

ENV PYTHONUNBUFFERED True \
    APP_HOME /app \
    POETRY_VIRTUALENVS_CREATE false



RUN apt-get update && apt-get install -y curl poppler-utils git openssh-client

WORKDIR $APP_HOME

ENV PATH="/root/.local/bin:$PATH"
RUN curl -sSL https://install.python-poetry.org | python3 -  && poetry config virtualenvs.create false

COPY pyproject.toml ./

#RUN poetry install --without dev
RUN poetry install --no-root

COPY ./genote_llm ./genote_llm

CMD exec gunicorn --bind :$PORT --workers 1 --threads 8 --timeout 0 genote_llm.main:app -k uvicorn.workers.UvicornWorker --timeout 1800
