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
  "laid_collection_instance_linker"
  "map_link_tools"
  "modular_asset_renamer"
  "move_selected_to_own_collections"
  "object_preview_sequencer"
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

compatibility_archives=(
  "blend_reference_graph-0.1.4.zip"
  "collection_linked_mesh_replacer-1.0.0.zip"
  "collection_linked_mesh_replacer-1.0.1.zip"
  "collection_linked_mesh_replacer-1.0.2.zip"
  "collection_linked_mesh_replacer-1.0.3.zip"
  "collection_linked_mesh_replacer-1.0.4.zip"
  "collection_linked_mesh_replacer-1.0.5.zip"
  "collection_linked_mesh_replacer-1.0.6.zip"
  "collection_linked_mesh_replacer-1.0.7.zip"
  "collection_linked_mesh_replacer-1.0.8.zip"
  "laid_collection_instance_linker-1.0.0.zip"
  "laid_collection_instance_linker-1.0.1.zip"
  "modular_asset_renamer-1.0.0.zip"
  "modular_asset_renamer-1.0.1.zip"
  "modular_asset_renamer-1.0.2.zip"
  "modular_asset_renamer-1.0.3.zip"
  "modular_asset_renamer-1.0.4.zip"
  "modular_asset_renamer-1.0.5.zip"
  "modular_asset_renamer-1.0.6.zip"
  "modular_asset_renamer-1.0.7.zip"
  "move_selected_to_own_collections-1.3.0.zip"
  "move_selected_to_own_collections-1.4.0.zip"
  "object_preview_sequencer-1.0.0.zip"
  "object_preview_sequencer-1.0.1.zip"
  "unreal_bridge_tools-2.2.15.zip"
  "unreal_bridge_tools-2.2.16.zip"
  "unreal_bridge_tools-2.2.17.zip"
  "vertex_color_material_painter-1.0.0.zip"
  "vertex_color_material_painter-1.0.1.zip"
  "vertex_color_material_painter-1.0.2.zip"
  "vertex_color_material_painter-1.0.3.zip"
  "vertex_color_material_painter-1.0.4.zip"
  "vertex_color_material_painter-1.0.5.zip"
  "vertex_color_material_painter-1.0.6.zip"
  "vertex_color_material_painter-1.0.7.zip"
  "vertex_color_material_painter-1.0.8.zip"
  "vertex_color_material_painter-1.0.9.zip"
  "vertex_color_material_painter-1.0.10.zip"
)

if [[ ! -x "$BLENDER_BIN" ]]; then
  echo "Blender executable not found: $BLENDER_BIN" >&2
  echo "Set BLENDER_BIN=/path/to/blender and rerun." >&2
  exit 1
fi

mkdir -p "$OUTPUT_DIR"
compatibility_dir="$(mktemp -d "${TMPDIR:-/tmp}/taiyo-extension-compat.XXXXXX")"

restore_compatibility_archives() {
  if [[ ! -d "$compatibility_dir" ]]; then
    return
  fi
  for archive in "${compatibility_archives[@]}"; do
    if [[ -f "$compatibility_dir/$archive" ]]; then
      mv "$compatibility_dir/$archive" "$OUTPUT_DIR/$archive"
    fi
  done
  rmdir "$compatibility_dir"
}

trap restore_compatibility_archives EXIT
for archive in "${compatibility_archives[@]}"; do
  if [[ -f "$OUTPUT_DIR/$archive" ]]; then
    mv "$OUTPUT_DIR/$archive" "$compatibility_dir/$archive"
  fi
done

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

echo "==> Adding extension update timestamps"
"$BLENDER_BIN" --background --python "$ROOT_DIR/tools/add_extension_update_metadata.py" -- "$ROOT_DIR"

restore_compatibility_archives
trap - EXIT

find "$SOURCE_ROOT" -name '__pycache__' -type d -prune -exec rm -rf {} +
find "$SOURCE_ROOT" -name '.DS_Store' -type f -delete

echo "==> Done"
echo "Repository index: $OUTPUT_DIR/index.json"
