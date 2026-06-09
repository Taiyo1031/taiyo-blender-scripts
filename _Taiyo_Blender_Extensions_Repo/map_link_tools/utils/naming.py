import re


BLENDER_NUMERIC_SUFFIX_RE = re.compile(r"\.\d{3}$")


def has_blender_numeric_suffix(name):
    return bool(BLENDER_NUMERIC_SUFFIX_RE.search(name or ""))


def remove_blender_numeric_suffix(name):
    return BLENDER_NUMERIC_SUFFIX_RE.sub("", name or "")


def unique_temporary_name(existing_names):
    base_name = ".MapLinkTemp"
    index = 1
    while True:
        name = f"{base_name}.{index:03d}"
        if name not in existing_names:
            return name
        index += 1


def short_list(names, limit=6):
    names = [name for name in names if name]
    if not names:
        return ""
    shown = ", ".join(names[:limit])
    if len(names) > limit:
        shown += f", ... +{len(names) - limit}"
    return shown
