"""Mirror collections: a copy of a collection path inside another tree (retired objects, FromHoudini).

Blender collection names are unique per file, so a mirror cannot reuse the original name. It is named
``<name> [<tag>]`` and remembers the name it mirrors in a custom property.
"""
import bpy

MIRROR_KEY = 'ub_mirror_of'
MIRROR_TAG_KEY = 'ub_mirror_tag'


def mirror_name(part, tag):
    return f'{part} [{tag}]'


def find_mirror_child(parent, part, tag):
    for child in parent.children:
        if child.get(MIRROR_KEY) == part and child.get(MIRROR_TAG_KEY) == tag:
            return child
    return None


def mirror_path(root, parts, tag, created=None):
    """The collection at `parts` below `root` (each level a mirror), creating missing levels.

    New collections are appended to `created` (when given) so a caller can roll them back.
    """
    node = root
    for part in parts:
        child = find_mirror_child(node, part, tag)
        if child is None:
            child = bpy.data.collections.new(mirror_name(part, tag))
            child[MIRROR_KEY] = part
            child[MIRROR_TAG_KEY] = tag
            node.children.link(child)
            if created is not None:
                created.append(child)
        node = child
    return node
