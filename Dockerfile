FROM python:3.13-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

# System libraries WeasyPrint needs (RFP §10.3).
# libmagic — detecting the real file type from content (RFP §684).
RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        libcairo2 \
        libpango-1.0-0 \
        libpangocairo-1.0-0 \
        libgdk-pixbuf-2.0-0 \
        libffi-dev \
        shared-mime-info \
        libmagic1 \
        fonts-dejavu-core \
        poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# poppler-utils is for reading the output back, not for producing it.
# `pdftoppm` renders a generated portfolio to images so the printed page can
# be looked at (RFP §10.3). Parsing a PDF proves the text is there; only
# looking at it catches what else is — a header comment that was never a
# comment printed on page one of every portfolio for eight days before
# anyone rendered one.

# Cyrillic fonts — RFP §10.3, §627.
# Installed into the image rather than relying on host or system fonts.
COPY assets/fonts/ /usr/share/fonts/truetype/kinder/
RUN fc-cache -f

WORKDIR /app

# WhiteNoise warns on every request if this is missing.
RUN mkdir -p /app/staticfiles

COPY requirements/ requirements/
ARG REQUIREMENTS=requirements/dev.txt
RUN pip install --upgrade pip && pip install -r ${REQUIREMENTS}

COPY . .

CMD ["python", "manage.py", "runserver", "0.0.0.0:8000"]
