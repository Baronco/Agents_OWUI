# Makefile — publicacion de imagen Docker + workflow local con compose.
#
# No fija SHELL: las recetas usan solo `docker` y `echo`, y las validaciones
# se hacen a nivel de Make ($(error) e ifneq), por lo que funcionan igual en
# cmd.exe (Windows) y en /bin/sh (Linux/macOS).
#
# Uso rapido:
#   make release VERSION=v0.1.1              # build + push de la version
#   make release VERSION=v0.1.1 LATEST=true  # ademas taggea y publica :latest
#   make up                                  # levanta el stack local

IMAGE   ?= ghcr.io/baronco/owui_agents
VERSION ?=
LATEST  ?= false

.DEFAULT_GOAL := help
.PHONY: help release build up down logs ps restart \
        compose-up compose-down compose-logs compose-ps compose-restart

# ── Ayuda ────────────────────────────────────────────────────────────
help:
	@echo Targets disponibles:
	@echo   make release VERSION=v0.1.1 [LATEST=true]   Build + push de la imagen versionada (LATEST=true ademas publica :latest)
	@echo   make build VERSION=v0.1.1                   Solo docker build de la imagen versionada
	@echo   make up                                     Levanta el stack local (docker compose up -d --build)
	@echo   make down                                   Detiene y elimina el stack local
	@echo   make logs                                   Sigue los logs del stack
	@echo   make ps                                     Estado de los servicios
	@echo   make restart                                Reinicia el stack
	@echo ----------------------------------------------------------------------------------------------------
	@echo Variables: IMAGE=$(IMAGE)  VERSION=$(if $(strip $(VERSION)),$(VERSION),(sin definir))  LATEST=$(LATEST)

# ── Publicacion de imagen ────────────────────────────────────────────
# VERSION es obligatoria: sin ella el target aborta antes de ejecutar nada.
release:
	$(if $(strip $(VERSION)),@echo Publicando $(IMAGE):$(VERSION),$(error VERSION es obligatoria. Uso: make release VERSION=v0.1.1 [LATEST=true]))
	docker build . -t $(IMAGE):$(VERSION)
	docker push $(IMAGE):$(VERSION)
ifneq ($(filter true 1 yes,$(LATEST)),)
	@echo Taggeando y publicando $(IMAGE):latest
	docker tag $(IMAGE):$(VERSION) $(IMAGE):latest
	docker push $(IMAGE):latest
endif

build:
	$(if $(strip $(VERSION)),@echo Construyendo $(IMAGE):$(VERSION),$(error VERSION es obligatoria. Uso: make build VERSION=v0.1.1))
	docker build . -t $(IMAGE):$(VERSION)

# ── Compose local ────────────────────────────────────────────────────
up:  ## Levanta el stack local (build incluido)
	docker compose up -d --build

down:  ## Detiene y elimina el stack local
	docker compose down

logs:  ## Sigue los logs del stack
	docker compose logs -f

ps:  ## Estado de los servicios
	docker compose ps

restart:  ## Reinicia el stack
	docker compose restart

# Alias
compose-up: up
compose-down: down
compose-logs: logs
compose-ps: ps
compose-restart: restart
