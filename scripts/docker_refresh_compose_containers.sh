#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 1 ]]; then
  echo "usage: $0 <container-name> [<container-name> ...]" >&2
  exit 1
fi

for container in "$@"; do
  if ! docker inspect "$container" >/dev/null 2>&1; then
    echo "container not found: $container" >&2
    exit 1
  fi

  workdir="$(docker inspect "$container" --format '{{ index .Config.Labels "com.docker.compose.project.working_dir" }}')"
  config_files_csv="$(docker inspect "$container" --format '{{ index .Config.Labels "com.docker.compose.project.config_files" }}')"
  service="$(docker inspect "$container" --format '{{ index .Config.Labels "com.docker.compose.service" }}')"

  if [[ -z "$workdir" || -z "$config_files_csv" || -z "$service" ]]; then
    echo "container is not compose-managed or is missing compose labels: $container" >&2
    exit 1
  fi

  before_image_id="$(docker inspect "$container" --format '{{ .Image }}')"
  before_image_name="$(docker inspect "$container" --format '{{ .Config.Image }}')"

  compose_args=()
  IFS=',' read -r -a config_files <<<"$config_files_csv"
  for config_file in "${config_files[@]}"; do
    compose_args+=("-f" "$config_file")
  done

  echo "refreshing $container ($service) from $before_image_name"
  docker compose --project-directory "$workdir" "${compose_args[@]}" pull "$service"
  docker compose --project-directory "$workdir" "${compose_args[@]}" up -d "$service"

  after_image_id="$(docker inspect "$container" --format '{{ .Image }}')"
  status="$(docker inspect "$container" --format '{{ .State.Status }}')"

  echo "container=$container service=$service status=$status"
  echo "image_before=$before_image_id"
  echo "image_after=$after_image_id"
done

echo "pruning unused images"
docker image prune -af
