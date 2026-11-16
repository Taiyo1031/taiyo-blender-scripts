import bpy


ID_COLLECTIONS = (
    ("OBJECT", "Object", "objects"),
    ("MESH", "Mesh", "meshes"),
    ("ARMATURE", "Armature", "armatures"),
    ("CURVE", "Curve", "curves"),
    ("CURVE", "MetaBall", "metaballs"),
    ("CURVE", "Lattice", "lattices"),
    ("CURVE", "GreasePencil", "grease_pencils"),
    ("CURVE", "GreasePencil", "grease_pencils_v3"),
    ("COLLECTION", "Collection", "collections"),
    ("MATERIAL", "Material", "materials"),
    ("IMAGE", "Image", "images"),
    ("NODEGROUP", "NodeGroup", "node_groups"),
    ("ACTION", "Action", "actions"),
    ("SCENE", "Scene", "scenes"),
    ("WORLD", "World", "worlds"),
    ("CAMERA", "Camera", "cameras"),
    ("LIGHT", "Light", "lights"),
    ("TEXT", "Text", "texts"),
    ("FONT", "Font", "fonts"),
    ("SOUND", "Sound", "sounds"),
    ("PARTICLE", "Particle", "particles"),
    ("TEXTURE", "Texture", "textures"),
    ("LIBRARY", "Library", "libraries"),
)
EXCLUDED_COLLECTIONS = {"brushes", "palettes", "workspaces", "screens", "window_managers"}


def id_key(idblock):
    library = getattr(idblock, "library", None)
    return f"{idblock.name} [lib:{library.name}]" if library else idblock.name


def iter_id_collections():
    known = {entry[2] for entry in ID_COLLECTIONS}
    for group, prefix, name in ID_COLLECTIONS:
        collection = getattr(bpy.data, name, None)
        if collection is not None:
            yield group, prefix, collection
    for prop in bpy.data.bl_rna.properties:
        if prop.type != "COLLECTION" or prop.identifier in known | EXCLUDED_COLLECTIONS:
            continue
        collection = getattr(bpy.data, prop.identifier, None)
        if collection is not None:
            yield "OTHER", None, collection


def datablock_node_id(datablock, prefix=None):
    if isinstance(datablock, bpy.types.Library):
        return f"Library:{datablock.filepath}"
    return f"{prefix or datablock.bl_rna.identifier}:{id_key(datablock)}"


def iter_node_id_index(index):
    for _group, prefix, collection in iter_id_collections():
        for block in collection:
            if isinstance(block, bpy.types.ID) and not block.is_embedded_data:
                index[datablock_node_id(block, prefix)] = block
            yield None


def build_node_id_index():
    index = {}
    for _ in iter_node_id_index(index):
        pass
    return index


def resolve_node_id(node_id, index=None):
    index = build_node_id_index() if index is None else index
    if node_id.startswith("Bone:"):
        # Object and bone names can themselves contain colons.
        for key, block in index.items():
            if key.startswith("Object:") and getattr(block, "type", None) == "ARMATURE":
                prefix = f"Bone:{id_key(block)}:"
                if node_id.startswith(prefix) and block.data.bones.get(node_id[len(prefix):]):
                    return block, node_id[len(prefix):]
        return None
    return index.get(node_id)
