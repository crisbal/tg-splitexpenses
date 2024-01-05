FROM python:3.11-alpine
RUN apk add build-base
RUN mkdir /app && mkdir /config
WORKDIR /app
ADD pyproject.toml /app
ADD src /app/src
RUN python -m pip install .

ENV TG_SPLITEXPENSE_CONFIG_FILE="/config/config.yaml"
ENTRYPOINT ["python", "-m", "tgsplitexpenses"]
