import re


BLENDER_NUMERIC_SUFFIX_RE = re.compile(r"\.(\d{3})$")


def has_blender_numeric_suffix(name):
    return bool(BLENDER_NUMERIC_SUFFIX_RE.search(name or ""))


def remove_blender_numeric_suffix(name):
    return BLENDER_NUMERIC_SUFFIX_RE.sub("", name or "")


def blender_numeric_suffix_number(name):
    match = BLENDER_NUMERIC_SUFFIX_RE.search(name or "")
    if match is None:
        return None
    return int(match.group(1))


def remove_suffix_sort_key(name):
    target_name = remove_blender_numeric_suffix(name)
    suffix_number = blender_numeric_suffix_number(name)
    if suffix_number is None:
        suffix_number = 1000
    return (target_name.casefold(), suffix_number, (name or "").casefold(), name or "")


def unique_temporary_name(existing_names):
    base_name = "MapLinkToolsTemp"
    index = 1
    while True:
        name = f"{base_name}{index:06d}"
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
