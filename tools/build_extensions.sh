#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SOURCE_ROOT="$ROOT_DIR/_Taiyo_Blender_Extensions_Repo"
OUTPUT_DIR="$ROOT_DIR/docs/extensions"

if [[ -z "${BLENDER_BIN:-}" ]]; then
  blender_candidates=(
    "/Applications/Blender.app/Contents/MacOS/Blender"
    "C:/Program Files/Blender Foundation/Blender 4.5/blender.exe"
    "C:/Program Files/Blender Foundation/Blender 4.4/blender.exe"
    "C:/Program Files/Blender Foundation/Blender 4.3/blender.exe"
    "C:/Program Files/Blender Foundation/Blender 4.2/blender.exe"
  )
  for candidate in "${blender_candidates[@]}"; do
    if [[ -x "$candidate" ]]; then
      BLENDER_BIN="$candidate"
      break
    fi
  done
fi
BLENDER_BIN="${BLENDER_BIN:-/Applications/Blender.app/Contents/MacOS/Blender}"

packages=(
  "attribute_csv_exporter"
  "blend_reference_graph"
  "collection_linked_mesh_replacer"
  "collection_number_to_mesh_name"
  "collection_mesh_merge_fbx_exporter"
  "custom_properties_batch_editor"
  "export_selected_names_csv"
  "gn_parameter_csv_exporter"
  "instance_name_fixer"
  "map_link_tools"
  "modular_asset_renamer"
  "move_selected_to_own_collections"
  "overlap_selector"
  "proportional_dimensions"
  "rb_instance_helper"
  "replace_selected_with_active"
  "taiyo_extension_manager"
  "uv_channel_placement_tool"
  "unreal_bridge_tools"
  "vertex_color_material_painter"
  "viewport_export_selected_meshes"
)

if [[ ! -x "$BLENDER_BIN" ]]; then
  echo "Blender executable not found: $BLENDER_BIN" >&2
  echo "Set BLENDER_BIN=/path/to/blender and rerun." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
find "$OUTPUT_DIR" -maxdepth 1 -type f \( -name '*.zip' -o -name 'index.json' -o -name 'index.html' \) -delete
find "$SOURCE_ROOT" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$SOURCE_ROOT" -name '.DS_Store' -type f -delete

for package in "${packages[@]}"; do
  source_dir="$SOURCE_ROOT/$package"
  echo "==> Validating $package"
  "$BLENDER_BIN" --background --command extension validate "$source_dir"

  echo "==> Building $package"
  "$BLENDER_BIN" --background --command extension build --source-dir "$source_dir" --output-dir "$OUTPUT_DIR"
done

echo "==> Generating static extension repository"
"$BLENDER_BIN" --background --command extension server-generate --repo-dir "$OUTPUT_DIR" --html

find "$SOURCE_ROOT" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$SOURCE_ROOT" -name '.DS_Store' -type f -delete

echo "==> Done"
echo "Repository index: $OUTPUT_DIR/index.json"
