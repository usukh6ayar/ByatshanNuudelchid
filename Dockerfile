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
    && rm -rf /var/lib/apt/lists/*

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
