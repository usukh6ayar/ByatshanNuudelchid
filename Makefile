.PHONY: up down build sh test lint fix migrate migrations superuser storage seed pdf-spike logs

up:            ## Start the stack
	docker compose up

down:
	docker compose down

build:
	docker compose build

sh:
	docker compose run --rm web bash

test:          ## Run the full suite (authorization tests are mandatory — CLAUDE.md §4.1)
	docker compose run --rm web pytest

test-perms:    ## Just the authorization tests (RFP §21.2-21.4)
	docker compose run --rm web pytest apps/core/tests/test_permissions.py -v

lint:
	docker compose run --rm web ruff check .

fix:
	docker compose run --rm web ruff check . --fix

migrations:    ## Generate migrations — then READ them (CLAUDE.md §3.4)
	docker compose run --rm web python manage.py makemigrations

migrate:
	docker compose run --rm web python manage.py migrate

superuser:
	docker compose run --rm web python manage.py createsuperuser

storage:       ## Create the MinIO bucket — needed before the first upload
	docker compose run --rm web python manage.py init_storage

seed:          ## Demo kindergarten, staff and children (development only, RFP §707)
	docker compose run --rm web python manage.py seed_demo

pdf-spike:     ## Render the Cyrillic sample PDF (spec section 13.1)
	docker compose run --rm web python manage.py pdf_spike --out /app/spike.pdf

logs:
	docker compose logs -f web worker
