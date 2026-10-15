# Kummo operations
# Recipe lines must begin with TAB characters.

DOCKER ?= docker

.PHONY: local image-build prod-check prod-up prod-logs prod-stop prod-down prod-status

local:
	./start-kummo.sh local

image-build:
	$(DOCKER) build -t kummo:preflight .

prod-check:
	$(DOCKER) compose config --quiet

prod-up: prod-check
	$(DOCKER) compose up --build -d

prod-logs:
	$(DOCKER) compose logs -f

prod-status:
	$(DOCKER) compose ps

# Normal shutdown. Containers and volumes remain available.
prod-stop:
	$(DOCKER) compose stop

# Remove containers/networks but PRESERVE named volumes.
prod-down:
	$(DOCKER) compose down

# Deliberately NO target for:
# docker compose down -v
# docker volume prune

